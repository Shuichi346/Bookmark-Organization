import json
import sqlite3
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
