import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from bookmark_organization.bookmarks import parse, sha, uid
from bookmark_organization.schemas import AppError, Settings


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.path = directory / "bookmarks.sqlite3"
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY, hash TEXT UNIQUE, original BLOB, tree TEXT,
              filename TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS folders (
              id TEXT PRIMARY KEY, project TEXT, snapshot TEXT);
            CREATE TABLE IF NOT EXISTS bookmarks (
              id TEXT PRIMARY KEY, project TEXT, snapshot TEXT);
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, project TEXT, token TEXT, state TEXT,
              snapshot TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(project, token));
            CREATE UNIQUE INDEX IF NOT EXISTS active_project ON jobs(project)
              WHERE state IN ('running','paused');
            CREATE TABLE IF NOT EXISTS job_items (
              job TEXT, bookmark TEXT, state TEXT, retrieval TEXT, analysis TEXT,
              embedding TEXT, error TEXT, PRIMARY KEY(job, bookmark));
            CREATE TABLE IF NOT EXISTS analyses (
              job TEXT, bookmark TEXT, value TEXT, PRIMARY KEY(job,bookmark));
            CREATE TABLE IF NOT EXISTS embeddings (
              job TEXT, bookmark TEXT, value TEXT, PRIMARY KEY(job,bookmark));
            CREATE TABLE IF NOT EXISTS proposal_versions (
              id TEXT PRIMARY KEY, job TEXT, version INTEGER, tree TEXT,
              allow_incomplete INTEGER, UNIQUE(job,version));
            CREATE TABLE IF NOT EXISTS proposal_items (
              proposal TEXT, bookmark TEXT, value TEXT,
              PRIMARY KEY(proposal,bookmark));
            """)
        settings = directory / "settings.json"
        if not settings.exists():
            settings.write_text(Settings().model_dump_json(indent=2))

    @contextmanager
    def connect(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def one(self, sql: str, args=()) -> dict:
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
        if row is None:
            raise AppError("not_found", 404)
        return dict(row)

    def rows(self, sql: str, args=()) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def settings(self) -> Settings:
        return Settings.model_validate_json(
            (self.directory / "settings.json").read_text()
        )

    def save_settings(self, settings: Settings):
        path = self.directory / "settings.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(settings.model_dump_json(indent=2))
        temp.replace(path)

    def openrouter_api_key(self) -> str:
        path = self.directory / "credentials.json"
        if path.exists():
            key = json.loads(path.read_text()).get("openrouter_api_key", "")
            if key:
                return key
        return os.environ.get("OPENROUTER_API_KEY", "").strip()

    def save_openrouter_api_key(self, key: str):
        if not key:
            return
        # mkstemp creates the file with mode 0600 before writing any secret.
        descriptor, name = tempfile.mkstemp(dir=self.directory, prefix=".credentials-")
        path = Path(name)
        try:
            with os.fdopen(descriptor, "w") as file:
                json.dump({"openrouter_api_key": key}, file)
            path.replace(self.directory / "credentials.json")
        finally:
            path.unlink(missing_ok=True)

    def public_settings(self) -> dict:
        return {
            **self.settings().model_dump(),
            "openrouter_key_configured": bool(self.openrouter_api_key()),
        }

    def import_html(self, raw: bytes, filename: str) -> str:
        tree = parse(raw)
        digest = sha(raw)
        with self.connect() as db:
            old = db.execute(
                "SELECT id FROM projects WHERE hash=?", (digest,)
            ).fetchone()
            if old:
                return old["id"]
            project = uid()
            db.execute(
                "INSERT INTO projects(id,hash,original,tree,filename) VALUES(?,?,?,?,?)",
                (project, digest, raw, json.dumps(tree), Path(filename).name),
            )
            for n in tree:
                table = "folders" if n["kind"] == "folder" else "bookmarks"
                db.execute(
                    f"INSERT INTO {table} VALUES(?,?,?)",
                    (n["id"], project, json.dumps(n)),
                )
        return project

    def tree(self, project: str) -> list[dict]:
        return json.loads(
            self.one("SELECT tree FROM projects WHERE id=?", (project,))["tree"]
        )

    def latest_proposal(self, project: str) -> str | None:
        rows = self.rows(
            "SELECT p.id FROM proposal_versions p JOIN jobs j ON j.id=p.job "
            "WHERE j.project=? ORDER BY p.rowid DESC LIMIT 1",
            (project,),
        )
        return rows[0]["id"] if rows else None

    def job_tree(self, project: str, snapshot: dict) -> list[dict]:
        # Legacy jobs predate continuation and always use the immutable import.
        return snapshot.get("base_tree", self.tree(project))

    def items(self, job: str) -> list[dict]:
        rows = self.rows("SELECT * FROM job_items WHERE job=? ORDER BY rowid", (job,))
        for row in rows:
            for key in ("retrieval", "analysis", "embedding"):
                row[key] = json.loads(row[key]) if row[key] else None
        return rows

    def save_item(self, job: str, bookmark: str, state: str, **values):
        with self.connect() as db:
            assignments = ["state=?"]
            args = [state]
            for key, value in values.items():
                if key not in {"retrieval", "analysis", "embedding", "error"}:
                    raise ValueError("invalid column")
                assignments.append(f"{key}=?")
                args.append(
                    json.dumps(value) if value is not None and key != "error" else value
                )
                if key in {"analysis", "embedding"} and value is not None:
                    table = "analyses" if key == "analysis" else "embeddings"
                    db.execute(
                        f"INSERT OR REPLACE INTO {table} VALUES(?,?,?)",
                        (job, bookmark, json.dumps(value)),
                    )
            db.execute(
                f"UPDATE job_items SET {','.join(assignments)} WHERE job=? AND bookmark=?",
                (*args, job, bookmark),
            )
