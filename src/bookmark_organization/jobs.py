import asyncio
import json
import sqlite3

from bookmark_organization.bookmarks import uid
from bookmark_organization.db import Store
from bookmark_organization.fetching import Fetcher
from bookmark_organization.llm import PROMPT_VERSION, LocalAI
from bookmark_organization.organizing import scope
from bookmark_organization.schemas import AppError, JobRequest, Settings

TERMINAL = {"complete", "retrieval_failed", "analysis_failed"}


def create_job(store: Store, project: str, request: JobRequest) -> str:
    tree = store.tree(project)
    targets, folders, destination = scope(tree, request)
    if not targets:
        raise AppError("empty_scope")
    snapshot = {
        "targets": targets,
        "folders": folders,
        "destination": destination,
        "settings": store.settings().model_dump(),
        "prompt_version": PROMPT_VERSION,
    }
    with store.connect() as db:
        old = db.execute(
            "SELECT id FROM jobs WHERE project=? AND token=?", (project, request.token)
        ).fetchone()
        if old:
            return old["id"]
        identifier = uid()
        try:
            db.execute(
                "INSERT INTO jobs(id,project,token,state,snapshot) VALUES(?,?,?,?,?)",
                (identifier, project, request.token, "running", json.dumps(snapshot)),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError("job_conflict", 409) from exc
        db.executemany(
            "INSERT INTO job_items(job,bookmark,state) VALUES(?,?,'pending')",
            [(identifier, target) for target in targets],
        )
    return identifier


def job_state(store: Store, job: str) -> dict:
    row = store.one("SELECT * FROM jobs WHERE id=?", (job,))
    row["snapshot"] = json.loads(row["snapshot"])
    row["items"] = store.items(job)
    nodes = {n["id"]: n for n in store.tree(row["project"])}
    for item in row["items"]:
        item["url"] = nodes[item["bookmark"]]["url"]
    counts = {s: sum(i["state"] == s for i in row["items"]) for s in TERMINAL}
    counts["total"] = len(row["items"])
    counts["remaining"] = counts["total"] - sum(counts[s] for s in TERMINAL)
    row["counts"] = counts
    return row


def control(store: Store, job: str, action: str):
    store.one("SELECT id FROM jobs WHERE id=?", (job,))
    with store.connect() as db:
        if action == "pause":
            db.execute(
                "UPDATE jobs SET state='paused' WHERE id=? AND state='running'", (job,)
            )
        else:
            if action == "retry-failed":
                db.execute(
                    "UPDATE job_items SET state='pending',error=NULL,"
                    "retrieval=CASE WHEN state='retrieval_failed' THEN NULL ELSE retrieval END "
                    "WHERE job=? AND state IN ('retrieval_failed','analysis_failed')",
                    (job,),
                )
            try:
                db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
            except sqlite3.IntegrityError as exc:
                raise AppError("job_conflict", 409) from exc


class Worker:
    def __init__(self, store: Store, fetch_factory=Fetcher, ai_factory=LocalAI):
        self.store = store
        self.fetch_factory = fetch_factory
        self.ai_factory = ai_factory
        self.stopping = False
        self.wake = asyncio.Event()

    def recover(self):
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET state='paused' WHERE state='running'")
            db.execute(
                "UPDATE job_items SET state='pending' "
                "WHERE state IN ('fetching','analyzing','embedding')"
            )

    def running(self, job: str) -> bool:
        return (
            not self.stopping
            and self.store.one("SELECT state FROM jobs WHERE id=?", (job,))["state"]
            == "running"
        )

    async def process(self, job: dict):
        identifier = job["id"]
        snapshot = json.loads(job["snapshot"])
        settings = Settings.model_validate(snapshot["settings"])
        fetcher = self.fetch_factory(settings)
        ai = self.ai_factory(settings)
        tree = {n["id"]: n for n in self.store.tree(job["project"])}
        try:
            # Validate actual local model availability once for this processing batch.
            await ai.ensure_local(settings.generation)
            await ai.ensure_local(settings.embedding)
            pending = [
                i for i in self.store.items(identifier) if i["state"] not in TERMINAL
            ]
            for start in range(0, len(pending), settings.retrieval_concurrency):
                if not self.running(identifier):
                    return
                batch = pending[start : start + settings.retrieval_concurrency]

                async def retrieve(item):
                    if not item["retrieval"]:
                        self.store.save_item(identifier, item["bookmark"], "fetching")
                        item["retrieval"] = await fetcher.fetch(
                            tree[item["bookmark"]]["url"]
                        )
                        self.store.save_item(
                            identifier,
                            item["bookmark"],
                            "pending",
                            retrieval=item["retrieval"],
                        )

                await asyncio.gather(*(retrieve(item) for item in batch))
                for item in batch:
                    if not self.running(identifier):
                        return
                    bid = item["bookmark"]
                    page = item["retrieval"]
                    if page["status"] != "ok":
                        self.store.save_item(identifier, bid, "retrieval_failed")
                        continue
                    try:
                        if not item["analysis"]:
                            self.store.save_item(identifier, bid, "analyzing")
                            item["analysis"] = await ai.analyze(tree[bid], page)
                            self.store.save_item(
                                identifier, bid, "pending", analysis=item["analysis"]
                            )
                        if not self.running(identifier):
                            return
                        if not item["embedding"]:
                            self.store.save_item(identifier, bid, "embedding")
                            item["embedding"] = await ai.embed(page, item["analysis"])
                            self.store.save_item(
                                identifier, bid, "pending", embedding=item["embedding"]
                            )
                        self.store.save_item(identifier, bid, "complete", error=None)
                    except AppError as exc:
                        self.store.save_item(
                            identifier, bid, "analysis_failed", error=exc.code
                        )
            if self.running(identifier):
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE jobs SET state='complete' WHERE id=?", (identifier,)
                    )
        except AppError as exc:
            # A stopped model server is retryable and never a retrieval failure.
            for item in self.store.items(identifier):
                if item["state"] not in TERMINAL:
                    self.store.save_item(
                        identifier, item["bookmark"], "analysis_failed", error=exc.code
                    )
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET state='complete' WHERE id=?", (identifier,))
        finally:
            await fetcher.close()
            await ai.close()

    async def run(self):
        while not self.stopping:
            rows = self.store.rows(
                "SELECT * FROM jobs WHERE state='running' ORDER BY created LIMIT 1"
            )
            if rows:
                try:
                    await self.process(rows[0])
                except Exception:
                    with self.store.connect() as db:
                        db.execute(
                            "UPDATE jobs SET state='paused' WHERE id=?",
                            (rows[0]["id"],),
                        )
                    for item in self.store.items(rows[0]["id"]):
                        if item["state"] not in TERMINAL:
                            self.store.save_item(
                                rows[0]["id"],
                                item["bookmark"],
                                "pending",
                                error="worker_error",
                            )
            else:
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=1)
                except TimeoutError:
                    pass
