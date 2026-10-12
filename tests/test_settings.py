import json
import stat

import httpx
from helpers import HTML, FakeAI, FakeFetcher, make_worker

from bookmark_organization.app import create_app
from bookmark_organization.jobs import Worker, control, create_job, job_state
from bookmark_organization.llm import LocalAI
from bookmark_organization.schemas import Endpoint, JobRequest


async def test_worker_reads_rotated_credentials_outside_the_job_snapshot(
    tmp_path, monkeypatch
):
    app = create_app(tmp_path, worker_factory=make_worker)
    store = app.state.store
    settings = store.settings()
    settings.generation = Endpoint(runtime="openrouter", model="test/chat")
    store.save_settings(settings)
    store.save_openrouter_api_key("first-key")
    project = store.import_html(HTML, "synthetic.html")
    job = create_job(store, project, JobRequest(all=True, token="credential-job"))
    snapshot = job_state(store, job)["snapshot"]
    keys = []

    def ai_factory(values, *, api_key):
        keys.append(api_key)
        assert values.generation.model == "test/chat"
        return FakeAI(values)

    monkeypatch.setattr("bookmark_organization.jobs.LocalAI", ai_factory)
    worker = Worker(store, fetch_factory=FakeFetcher)
    await worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job,)))
    store.save_openrouter_api_key("second-key")
    control(store, job, "retry-failed")
    await worker.process(store.one("SELECT * FROM jobs WHERE id=?", (job,)))
    assert keys == ["first-key", "second-key"]
    assert job_state(store, job)["snapshot"] == snapshot


async def test_key_storage_redaction_and_snapshot_isolation(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app = create_app(tmp_path, worker_factory=make_worker)
    store = app.state.store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/")
        headers = {"X-CSRF-Token": client.cookies["csrf"]}
        values = (await client.get("/api/settings")).json()
        values["generation"] = {
            "runtime": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "openai/test-chat",
        }
        values["openrouter_api_key"] = "test-private-key"
        saved = await client.put("/api/settings", json=values, headers=headers)
        assert saved.status_code == 200
        assert saved.json()["openrouter_key_configured"] is True
        assert "test-private-key" not in saved.text
        assert "test-private-key" not in (await client.get("/api/settings")).text
        assert "test-private-key" not in (await client.get("/")).text
        assert "test-private-key" not in (tmp_path / "settings.json").read_text()
        assert store.openrouter_api_key() == "test-private-key"
        assert stat.S_IMODE((tmp_path / "credentials.json").stat().st_mode) == 0o600
        project = store.import_html(HTML, "synthetic.html")
        job = create_job(store, project, JobRequest(all=True, token="test-openrouter"))
        snapshot = job_state(store, job)["snapshot"]
        assert snapshot["settings"]["generation"]["runtime"] == "openrouter"
        assert "test-private-key" not in json.dumps(snapshot)
        assert "openrouter_api_key" not in json.dumps(snapshot)
        assert "test-private-key" not in (await client.get(f"/api/jobs/{job}")).text
        # Blank submissions retain the key; rotation changes no job settings.
        values["openrouter_api_key"] = ""
        assert (
            await client.put("/api/settings", json=values, headers=headers)
        ).status_code == 200
        assert store.openrouter_api_key() == "test-private-key"
        values["openrouter_api_key"] = "replacement-key"
        values["generation"]["model"] = "openai/new-chat"
        await client.put("/api/settings", json=values, headers=headers)
        assert store.openrouter_api_key() == "replacement-key"
        assert job_state(store, job)["snapshot"] == snapshot
        assert "test-private-key" not in (
            tmp_path / "bookmarks.sqlite3"
        ).read_bytes().decode(errors="ignore")
        values["openrouter_api_key"] = "bad\nkey"
        invalid = await client.put("/api/settings", json=values, headers=headers)
        assert invalid.status_code == 422
        assert invalid.json() == {"code": "validation_error"}


async def test_probe_uses_unsaved_or_stored_key_without_persisting_it(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-key")
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {}})
        embedding = request.url.path.endswith("/embeddings/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "test/embedding" if embedding else "test/chat",
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": [
                                "embeddings" if embedding else "text"
                            ],
                        },
                        "supported_parameters": ["structured_outputs"],
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "bookmark_organization.app.LocalAI",
        lambda settings, *, api_key: LocalAI(
            settings,
            httpx.AsyncClient(transport=httpx.MockTransport(handle)),
            api_key=api_key,
        ),
    )
    app = create_app(tmp_path, worker_factory=make_worker)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/")
        headers = {"X-CSRF-Token": client.cookies["csrf"]}
        values = (await client.get("/api/settings")).json()
        assert values["openrouter_key_configured"] is True
        for role in ["generation", "embedding"]:
            values[role] = {
                "runtime": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "model": "",
            }
        for key in ["unsaved-key", ""]:
            requests.clear()
            values["openrouter_api_key"] = key
            result = await client.post(
                "/api/settings/probe", json=values, headers=headers
            )
            assert result.status_code == 200
            assert result.json() == {
                "generation": ["test/chat"],
                "embedding": ["test/embedding"],
            }
            assert all(
                r.headers["authorization"] == f"Bearer {key or 'environment-key'}"
                for r in requests
            )
            assert not (tmp_path / "credentials.json").exists()
        assert app.state.store.settings().generation.runtime == "lmstudio"
