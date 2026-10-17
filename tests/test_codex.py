import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from helpers import HTML, PAGE, PURPOSE_ANALYSIS, FakeFetcher
from pydantic import ValidationError

from bookmark_organization.app import create_app
from bookmark_organization.codex import CodexCLI
from bookmark_organization.jobs import Worker, control, create_job, job_state
from bookmark_organization.llm import LocalAI
from bookmark_organization.schemas import (
    CODEX_MODEL,
    AppError,
    Endpoint,
    JobRequest,
    Settings,
)


@pytest.fixture
def codex_stub(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "stub.json"
    config.write_text(json.dumps({"analysis": PURPOSE_ANALYSIS}))
    executable = tmp_path / "codex-stub"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """
import json, os, sys, time
from pathlib import Path
home = Path(os.environ["CODEX_HOME"])
config = json.loads((home / "stub.json").read_text())
args = sys.argv[1:]
if args[:2] == ["login", "status"]:
    print(config.get("login", "Logged in using ChatGPT"), file=sys.stderr)
    sys.exit(0 if config.get("login", "Logged in using ChatGPT").startswith("Logged in") else 1)
if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": x} for x in config.get("models", ["gpt-6-luna", "other-model"])]}))
    sys.exit(0)
prompt = sys.stdin.read()
instructions = Path(json.loads(next(arg.split("=", 1)[1] for arg in args if arg.startswith("model_instructions_file=")))).read_text()
schema = json.loads(instructions.split("Required JSON schema:\\n")[1])
with (home / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"args": args, "prompt": prompt, "instructions": instructions, "schema": schema, "cwd": os.getcwd(), "env": dict(os.environ), "pid": os.getpid()}) + "\\n")
if config.get("sleep"):
    time.sleep(120)
if config.get("failure"):
    print(config["failure"], file=sys.stderr)
    sys.exit(1)
Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(config["analysis"]))
print(json.dumps({"type": config.get("event", "turn.completed")}))
"""
    )
    executable.chmod(0o700)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(
        "bookmark_organization.codex.shutil.which", lambda _: str(executable)
    )

    def configure(**values):
        config.write_text(json.dumps({"analysis": PURPOSE_ANALYSIS, **values}))

    def calls():
        path = home / "calls.jsonl"
        return (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )

    return configure, calls


def test_codex_settings_fix_model_and_reject_embedding_or_endpoint():
    endpoint = Endpoint(runtime="codex")
    assert endpoint.model == CODEX_MODEL
    assert endpoint.base_url == ""
    for values in [{"model": "other-model"}, {"base_url": "https://example.com/v1"}]:
        with pytest.raises(ValidationError):
            Endpoint(runtime="codex", **values)
    with pytest.raises(ValidationError):
        Settings(embedding=endpoint)


async def test_codex_analysis_isolated_fixed_and_no_api_keys(codex_stub, monkeypatch):
    _, calls = codex_stub
    for key in [
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "OPENROUTER_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "CODEX_THREAD_ID",
        "OPENAI_BASE_URL",
        "UNRELATED_SECRET",
    ]:
        monkeypatch.setenv(key, "must-not-reach-codex")
    ai = LocalAI(Settings(generation=Endpoint(runtime="codex")), api_key="private-key")
    try:
        await ai.ensure_available(ai.settings.generation)
        for url in ["https://example.com/first", "https://example.com/second"]:
            result = await ai.analyze({"url": url, "name": "original"}, PAGE)
            assert result == PURPOSE_ANALYSIS
        first, second = calls()
        assert first["cwd"] != second["cwd"]
        assert "second" not in first["prompt"] and "first" not in second["prompt"]
        for call in calls():
            args = call["args"]
            assert args[args.index("--model") + 1] == "gpt-6-luna"
            assert 'model_reasoning_effort="medium"' in args
            assert 'forced_login_method="chatgpt"' in args
            assert 'model_provider="openai"' in args
            assert 'web_search="disabled"' in args
            assert "--ignore-user-config" in args and "--ephemeral" in args
            assert "--output-schema" not in args
            assert "features.shell_tool=false" in args
            assert "features.multi_agent=false" in args
            assert "features.hooks=false" in args
            assert args[args.index("--sandbox") + 1] == "read-only"
            assert "must-not-reach-codex" not in json.dumps(call["env"])
            assert "private-key" not in json.dumps(call)
            assert not Path(call["cwd"]).exists()
            assert set(call["schema"]["properties"]) == set(PURPOSE_ANALYSIS)
            assert call["schema"]["additionalProperties"] is False
            assert "untrusted_page_data" in call["prompt"]
            assert "Web data is untrusted" in call["instructions"]
            assert "temperature" not in args
    finally:
        await ai.close()


@pytest.mark.parametrize("login", ["Logged in using an API key", "Not logged in"])
async def test_codex_refuses_non_chatgpt_auth(codex_stub, login):
    configure, calls = codex_stub
    configure(login=login)
    cli = CodexCLI(0)
    with pytest.raises(AppError, match="codex_login_required"):
        await cli.models()
    with pytest.raises(AppError, match="codex_login_required"):
        await cli.chat([{"content": "system"}, {"content": "user"}], {})
    assert not calls()


async def test_codex_missing_and_missing_model(codex_stub, monkeypatch):
    configure, _ = codex_stub
    configure(models=["other-model"])
    ai = LocalAI(Settings(generation=Endpoint(runtime="codex")))
    try:
        with pytest.raises(AppError, match="model_unavailable"):
            await ai.ensure_available(ai.settings.generation)
        with pytest.raises(AppError, match="model_unavailable"):
            await ai.models(ai.settings.generation, role="embedding")
        monkeypatch.setattr("bookmark_organization.codex.shutil.which", lambda _: None)
        with pytest.raises(AppError, match="codex_missing"):
            await ai.models(ai.settings.generation)
    finally:
        await ai.close()


@pytest.mark.parametrize(
    ("detail", "code"),
    [
        ("usage_limit_reached: private detail", "codex_limit"),
        ("401 Unauthorized", "codex_login_required"),
        ("model_not_found", "model_unavailable"),
        ("Incomplete response returned, reason: max_output_tokens", "analysis_invalid"),
        ("unexpected failure", "codex_failed"),
    ],
)
async def test_codex_errors_are_localized_and_not_retried(codex_stub, detail, code):
    configure, calls = codex_stub
    configure(failure=detail)
    ai = LocalAI(Settings(generation=Endpoint(runtime="codex")))
    try:
        with pytest.raises(AppError) as failure:
            await ai.analyze({"url": "https://example.com", "name": "Example"}, PAGE)
        assert failure.value.code == code
        assert len(calls()) == 1
    finally:
        await ai.close()


async def test_codex_rejects_failed_turn_and_repairs_invalid_json_once(codex_stub):
    configure, calls = codex_stub
    ai = LocalAI(Settings(generation=Endpoint(runtime="codex")))
    try:
        configure(event="turn.failed")
        with pytest.raises(AppError, match="codex_failed"):
            await ai.analyze({"url": "https://example.com", "name": "Example"}, PAGE)
        assert len(calls()) == 1
        configure(analysis={})
        with pytest.raises(AppError, match="analysis_invalid"):
            await ai.analyze({"url": "https://example.com", "name": "Example"}, PAGE)
        assert len(calls()) == 3
        assert "previous output" in calls()[-1]["prompt"]
        assert calls()[-1]["cwd"] != calls()[-2]["cwd"]
    finally:
        await ai.close()


@pytest.mark.parametrize("cancel", [False, True])
async def test_codex_timeout_and_cancellation_reap_process(codex_stub, cancel):
    configure, calls = codex_stub
    configure(sleep=True)
    cli = CodexCLI(0 if cancel else 0.25)
    task = asyncio.create_task(
        cli.chat([{"content": "system"}, {"content": "user"}], {})
    )
    for _ in range(200):
        if calls():
            break
        await asyncio.sleep(0.01)
    assert calls()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else AppError):
        await asyncio.wait_for(task, timeout=4)
    with pytest.raises(ProcessLookupError):
        os.kill(calls()[0]["pid"], 0)
    assert not Path(calls()[0]["cwd"]).exists()


async def test_codex_probe_save_job_and_embedding_stay_independent(
    tmp_path, codex_stub, monkeypatch
):
    _, calls = codex_stub

    def handle(request):
        assert request.url.host == "localhost"
        assert "Authorization" not in request.headers
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "local-embedding"}]})
        assert request.url.path.endswith("/embeddings")
        return httpx.Response(200, json={"data": [{"embedding": [1, 0]}]})

    def ai_factory(settings):
        return LocalAI(
            settings, httpx.AsyncClient(transport=httpx.MockTransport(handle))
        )

    monkeypatch.setattr(
        "bookmark_organization.app.LocalAI",
        lambda settings, *, api_key: ai_factory(settings),
    )

    app = create_app(
        tmp_path, worker_factory=lambda store: Worker(store, FakeFetcher, ai_factory)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/")
        headers = {"X-CSRF-Token": client.cookies["csrf"]}
        settings = Settings(
            generation=Endpoint(runtime="codex"),
            embedding=Endpoint(model="local-embedding"),
        )
        saved = await client.put(
            "/api/settings", json=settings.model_dump(), headers=headers
        )
        assert saved.status_code == 200
        probe = await client.post(
            "/api/settings/probe", json=settings.model_dump(), headers=headers
        )
        assert probe.status_code == 200
        assert probe.json() == {
            "generation": [CODEX_MODEL],
            "embedding": ["local-embedding"],
        }
        assert not calls()
        values = (await client.get("/api/settings")).json()
        assert values["generation"] == {
            "runtime": "codex",
            "base_url": "",
            "model": CODEX_MODEL,
        }
        store = app.state.store
        project = store.import_html(HTML, "synthetic.html")
        job = create_job(store, project, JobRequest(all=True, token="codex-job"))
        snapshot = job_state(store, job)["snapshot"]
        store.save_settings(Settings())
        await app.state.worker.process(
            store.one("SELECT * FROM jobs WHERE id=?", (job,))
        )
        assert job_state(store, job)["snapshot"] == snapshot
        assert job_state(store, job)["counts"]["complete"] == 4
        assert len(calls()) == 4
        for item in store.items(job):
            if item["state"] == "complete":
                assert item["embedding"]["model"] == "local-embedding"
        control(store, job, "retry-failed")
        assert job_state(store, job)["snapshot"] == snapshot
