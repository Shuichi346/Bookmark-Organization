import asyncio

import pytest
from helpers import HTML, FakeAI, FakeFetcher, make_worker

from bookmark_organization.db import Store
from bookmark_organization.jobs import control, create_job, job_state
from bookmark_organization.schemas import AppError, JobRequest


async def test_pause_restart_resume_reuses_completed_stages(tmp_path):
    FakeFetcher.calls.clear()
    FakeAI.calls.clear()
    store = Store(tmp_path)
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
