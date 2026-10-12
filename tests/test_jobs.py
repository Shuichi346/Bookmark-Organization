import asyncio

import httpx
import pytest
from helpers import HTML, FakeAI, FakeFetcher, make_worker

from bookmark_organization.app import create_app
from bookmark_organization.db import Store
from bookmark_organization.jobs import Worker, control, create_job, job_state
from bookmark_organization.proposals import create_proposal
from bookmark_organization.schemas import AppError, JobRequest


async def test_pause_restart_resume_reuses_completed_stages(tmp_path):
    FakeFetcher.calls.clear()
    FakeAI.calls.clear()
    store = Store(tmp_path)
    initial = store.settings()
    initial.inference.source = "runtime"
    initial.inference.thinking = True
    store.save_settings(initial)
    project = store.import_html(HTML, "test.html")
    req = JobRequest(all=True, token="token-123")
    job = create_job(store, project, req)
    assert create_job(store, project, req) == job
    with pytest.raises(AppError):
        create_job(store, project, JobRequest(all=True, token="token-456"))
    worker = make_worker(store)
    task = asyncio.create_task(
        worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job,)))
    )
    for _ in range(100):
        if any(i["state"] == "embedding" for i in store.items(job)):
            break
        await asyncio.sleep(0.01)
    control(store, job, "pause")
    await task
    completed = [i["bookmark"] for i in store.items(job) if i["state"] == "complete"]
    assert completed
    restarted = make_worker(store)
    restarted.recover()
    assert job_state(store, job)["state"] == "paused"
    control(store, job, "resume")
    await restarted.process(store.one("SELECT * FROM jobs WHERE id=?", (job,)))
    assert job_state(store, job)["state"] == "complete"
    assert job_state(store, job)["counts"]["remaining"] == 0
    assert all(FakeAI.calls.count(bid) == 1 for bid in completed)
    assert len(FakeFetcher.calls) == 6
    assert len(store.items(job)) == 6
    # A settings change cannot affect an existing job snapshot.
    settings = store.settings()
    settings.generation.model = "new-user-model"
    settings.inference.source = "app"
    settings.inference.temperature = 0.33
    settings.inference.thinking = False
    settings.api_timeout = 3600
    store.save_settings(settings)
    assert (
        job_state(store, job)["snapshot"]["settings"]["generation"]["model"]
        != "new-user-model"
    )
    snapshot = job_state(store, job)["snapshot"]["settings"]
    assert snapshot["inference"]["source"] == "runtime"
    assert snapshot["inference"]["temperature"] == 0.7
    assert snapshot["inference"]["thinking"] is True
    assert snapshot["api_timeout"] == 0


async def test_recovery_pauses_external_access_and_retry_preserves_analysis(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "test.html")
    job = create_job(store, project, JobRequest(all=True, token="test-12345"))
    item = store.items(job)[0]
    store.save_item(
        job,
        item["bookmark"],
        "embedding",
        retrieval={"status": "ok"},
        analysis={"summary": "saved"},
    )
    worker = make_worker(store)
    worker.recover()
    assert job_state(store, job)["state"] == "paused"
    assert store.items(job)[0]["analysis"] == {"summary": "saved"}
    assert store.items(job)[0]["state"] == "pending"


@pytest.mark.parametrize(
    "stage", ["availability", "fetching", "analyzing", "embedding"]
)
async def test_cancel_interrupts_inflight_work_and_worker_accepts_next_job(
    tmp_path, stage
):
    store = Store(tmp_path)
    project = store.import_html(HTML, "test.html")
    job = create_job(store, project, JobRequest(all=True, token="cancel-inflight"))
    saved = store.items(job)[-1]
    store.save_item(job, saved["bookmark"], "complete", analysis={"summary": "saved"})
    snapshot = job_state(store, job)["snapshot"]
    tree = store.tree(project)
    entered = asyncio.Event()
    interrupted = asyncio.Event()
    closed = []
    block = True

    async def wait_at(current):
        if block and stage == current:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                interrupted.set()

    class BlockingFetcher(FakeFetcher):
        async def fetch(self, url):
            await wait_at("fetching")
            return await super().fetch(url)

        async def close(self):
            closed.append("fetcher")

    class BlockingAI(FakeAI):
        async def ensure_available(self, endpoint, *, role="generation"):
            await wait_at("availability")

        async def analyze(self, bookmark, page):
            await wait_at("analyzing")
            return await super().analyze(bookmark, page)

        async def embed(self, page, analysis):
            await wait_at("embedding")
            return await super().embed(page, analysis)

        async def close(self):
            closed.append("ai")

    app = create_app(
        tmp_path, worker_factory=lambda s: Worker(s, BlockingFetcher, BlockingAI)
    )
    worker = app.state.worker
    runner = asyncio.create_task(worker.run())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            await client.get("/")
            headers = {"X-CSRF-Token": client.cookies["csrf"]}
            assert (await client.post(f"/api/jobs/{job}/cancel")).status_code == 403
            response = await client.post(f"/api/jobs/{job}/cancel", headers=headers)
            assert response.status_code == 200
            # Repeated clicks cannot interrupt cleanup a second time.
            assert (
                await client.post(f"/api/jobs/{job}/cancel", headers=headers)
            ).status_code == 200
        await asyncio.wait_for(interrupted.wait(), timeout=1)
        for _ in range(100):
            if worker.active_task is None:
                break
            await asyncio.sleep(0.01)
        assert worker.active_task is None
        assert sorted(closed) == ["ai", "fetcher"]
        state = job_state(store, job)
        assert state["state"] == "cancelled"
        assert state["snapshot"] == snapshot
        assert store.tree(project) == tree
        assert (
            store.one("SELECT original FROM projects WHERE id=?", (project,))[
                "original"
            ]
            == HTML
        )
        assert next(i for i in state["items"] if i["bookmark"] == saved["bookmark"])[
            "analysis"
        ] == {"summary": "saved"}
        assert all(i["state"] in {"complete", "cancelled"} for i in state["items"])
        block = False
        next_job = create_job(
            store, project, JobRequest(all=True, token="after-cancel")
        )
        worker.wake.set()
        for _ in range(300):
            if job_state(store, next_job)["state"] == "complete":
                break
            await asyncio.sleep(0.01)
        assert job_state(store, next_job)["state"] == "complete"
        worker.recover()
        assert job_state(store, job) == state
    finally:
        worker.stopping = True
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await runner


def test_cancel_paused_job_preserves_results_and_is_terminal(tmp_path):
    store = Store(tmp_path)
    project = store.import_html(HTML, "test.html")
    job = create_job(store, project, JobRequest(all=True, token="paused-cancel"))
    item = store.items(job)[0]
    store.save_item(
        job,
        item["bookmark"],
        "pending",
        retrieval={"status": "ok"},
        analysis={"summary": "partial"},
    )
    control(store, job, "pause")
    control(store, job, "cancel")
    for action in ["pause", "resume", "retry-failed"]:
        with pytest.raises(AppError, match="invalid_job_action"):
            control(store, job, action)
    with pytest.raises(AppError, match="job_incomplete"):
        create_proposal(store, job, True)
    make_worker(store).recover()
    assert job_state(store, job)["state"] == "cancelled"
    assert store.items(job)[0]["analysis"] == {"summary": "partial"}
    next_job = create_job(store, project, JobRequest(all=True, token="new-analysis"))
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='complete' WHERE id=?", (next_job,))
    with pytest.raises(AppError, match="invalid_job_action"):
        control(store, next_job, "cancel")
