import asyncio
import json
import sqlite3
from contextlib import suppress
from functools import partial

from bookmark_organization.bookmarks import uid
from bookmark_organization.db import Store
from bookmark_organization.fetching import Fetcher, RequestPacer
from bookmark_organization.llm import PROMPT_VERSION, LocalAI
from bookmark_organization.organizing import scope
from bookmark_organization.policy import CUSTOM_PROMPT_VERSION, LEGACY_PROMPT_VERSION
from bookmark_organization.schemas import (
    AppError,
    JobRequest,
    OrganizationRules,
    Settings,
)

TERMINAL = {"complete", "retrieval_failed", "analysis_failed"}


def create_job(store: Store, project: str, request: JobRequest) -> str:
    # Imported lazily because proposal inspection also exposes job progress.
    from bookmark_organization.proposals import get_proposal

    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute(
            "SELECT id FROM jobs WHERE project=? AND token=?", (project, request.token)
        ).fetchone()
        if old:
            return old["id"]
        latest = store.latest_proposal(project)
        if request.base_proposal and request.base_proposal != latest:
            raise AppError("stale_proposal", 409)
        base_proposal = request.base_proposal or latest
        baseline = get_proposal(store, base_proposal) if base_proposal else None
        if baseline and baseline["project"] != project:
            raise AppError("invalid_scope")
        tree = baseline["tree"] if baseline else store.tree(project)
        targets, folders, destination = scope(tree, request)
        if not targets:
            raise AppError("empty_scope")
        snapshot = {
            "targets": targets,
            "folders": folders,
            "destination": destination,
            "settings": store.settings().model_dump(),
            "prompt_version": (
                CUSTOM_PROMPT_VERSION
                if "custom" in (request.rules.naming_mode, request.rules.folder_mode)
                else PROMPT_VERSION
            ),
            "rules": request.rules.model_dump(),
            "base_proposal": base_proposal,
            "base_tree": tree,
            "cumulative_targets": list(
                dict.fromkeys(
                    (baseline["cumulative_targets"] if baseline else []) + targets
                )
            ),
        }
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
    row["has_proposal"] = bool(
        store.rows("SELECT id FROM proposal_versions WHERE job=? LIMIT 1", (job,))
    )
    nodes = {n["id"]: n for n in store.job_tree(row["project"], row["snapshot"])}
    for item in row["items"]:
        item["url"] = nodes[item["bookmark"]]["url"]
    counts = {s: sum(i["state"] == s for i in row["items"]) for s in TERMINAL}
    counts["total"] = len(row["items"])
    counts["remaining"] = counts["total"] - sum(counts[s] for s in TERMINAL)
    row["counts"] = counts
    return row


def control(store: Store, job: str, action: str):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
        if row is None:
            raise AppError("not_found", 404)
        state = row["state"]
        if action == "cancel" and state == "cancelled":
            return
        allowed = {
            "pause": {"running", "paused"},
            "resume": {"paused", "running"},
            "retry-failed": {"paused", "complete"},
            "cancel": {"running", "paused"},
        }
        if state not in allowed.get(action, set()):
            raise AppError("invalid_job_action", 409)
        if action in {"resume", "retry-failed"}:
            own_proposals = {
                p["id"]
                for p in db.execute(
                    "SELECT id FROM proposal_versions WHERE job=?", (job,)
                )
            }
            if action == "retry-failed" and own_proposals:
                raise AppError("job_already_proposed", 409)
            latest = store.latest_proposal(row["project"])
            base = json.loads(row["snapshot"]).get("base_proposal")
            if latest != base and latest not in own_proposals:
                raise AppError("stale_proposal", 409)
        if action == "pause":
            db.execute(
                "UPDATE jobs SET state='paused' WHERE id=? AND state='running'", (job,)
            )
        elif action == "cancel":
            db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job,))
            # Retain saved results and failures; only unfinished items are cancelled.
            db.execute(
                "UPDATE job_items SET state='cancelled' WHERE job=? "
                "AND state NOT IN ('complete','retrieval_failed','analysis_failed')",
                (job,),
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
    def __init__(self, store: Store, fetch_factory=None, ai_factory=None):
        self.store = store
        # Keep pacing state when a manual retry or a new job creates another client.
        self.fetch_factory = fetch_factory or partial(Fetcher, pacer=RequestPacer())
        self.ai_factory = ai_factory or (
            lambda settings: LocalAI(settings, api_key=store.openrouter_api_key())
        )
        self.stopping = False
        self.wake = asyncio.Event()
        self.active_job: str | None = None
        self.active_task: asyncio.Task | None = None
        self._shutdown_lock = asyncio.Lock()

    def cancel(self, job: str):
        # Cancel the batch task, not the worker loop, so later jobs can still run.
        if self.active_job == job and self.active_task and not self.active_task.done():
            if not self.active_task.cancelling():
                self.active_task.cancel()

    async def shutdown(self):
        async with self._shutdown_lock:
            self.stopping = True
            self.wake.set()
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET state='paused' WHERE state='running'")
            task = self.active_task
            if task:
                if not task.done() and not task.cancelling():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            # Cancellation interrupts waits without discarding completed stages.
            # Exclude terminal jobs, including those the user already cancelled.
            with self.store.connect() as db:
                db.execute(
                    "UPDATE job_items SET state='pending' "
                    "WHERE state IN ('fetching','analyzing','embedding') "
                    "AND job IN (SELECT id FROM jobs WHERE state='paused')"
                )

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
        if not self.running(identifier):
            return
        snapshot = json.loads(job["snapshot"])
        settings = Settings.model_validate(snapshot["settings"])
        fetcher = self.fetch_factory(settings)
        ai = self.ai_factory(settings)
        ai.prompt_version = snapshot.get("prompt_version", LEGACY_PROMPT_VERSION)
        ai.rules = OrganizationRules.model_validate(snapshot.get("rules", {}))
        tree = {n["id"]: n for n in self.store.job_tree(job["project"], snapshot)}
        try:
            # Validate each selected provider/model once for this processing batch.
            await ai.ensure_available(settings.generation)
            await ai.ensure_available(settings.embedding, role="embedding")
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
                            bookmark = dict(tree[bid])
                            path = []
                            parent = bookmark["parent"]
                            while parent != "root":
                                path.append(tree[parent]["name"])
                                parent = tree[parent]["parent"]
                            bookmark["original_folder_path"] = " / ".join(
                                reversed(path)
                            )
                            item["analysis"] = await ai.analyze(bookmark, page)
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
                        if self.stopping:
                            return
                        self.store.save_item(
                            identifier, bid, "analysis_failed", error=exc.code
                        )
            if self.running(identifier):
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE jobs SET state='complete' WHERE id=?", (identifier,)
                    )
        except AppError as exc:
            if self.stopping:
                return
            # A stopped model server is retryable and never a retrieval failure.
            for item in self.store.items(identifier):
                if item["state"] not in TERMINAL:
                    self.store.save_item(
                        identifier, item["bookmark"], "analysis_failed", error=exc.code
                    )
            with self.store.connect() as db:
                db.execute("UPDATE jobs SET state='complete' WHERE id=?", (identifier,))
        finally:
            try:
                await fetcher.close()
            finally:
                await ai.close()

    async def run(self):
        while not self.stopping:
            rows = self.store.rows(
                "SELECT * FROM jobs WHERE state='running' ORDER BY created LIMIT 1"
            )
            if rows:
                self.active_job = rows[0]["id"]
                self.active_task = asyncio.create_task(self.process(rows[0]))
                try:
                    await self.active_task
                except asyncio.CancelledError:
                    if (
                        self.stopping
                        or self.store.one(
                            "SELECT state FROM jobs WHERE id=?", (self.active_job,)
                        )["state"]
                        != "cancelled"
                    ):
                        raise
                except Exception:
                    if self.stopping:
                        return
                    if (
                        self.store.one(
                            "SELECT state FROM jobs WHERE id=?", (self.active_job,)
                        )["state"]
                        == "cancelled"
                    ):
                        continue
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
                finally:
                    self.active_job = None
                    self.active_task = None
            else:
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=1)
                except TimeoutError:
                    pass
