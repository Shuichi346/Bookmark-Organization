import json

import httpx
import pytest
from helpers import ANALYSIS, PAGE
from pydantic import ValidationError

from bookmark_organization.llm import EMBEDDING_PREFIX, LocalAI
from bookmark_organization.schemas import (
    AppError,
    Endpoint,
    InferenceSettings,
    Settings,
)


@pytest.mark.parametrize("runtime", ["lmstudio", "ollama"])
@pytest.mark.parametrize("source", ["runtime", "app"])
async def test_requests_are_independent_and_model_selection_is_not_fixed(
    runtime, source
):
    calls = []

    def handle(request):
        data = json.loads(request.content)
        calls.append(data)
        if "embeddings" in str(request.url):
            return httpx.Response(200, json={"data": [{"embedding": [3, 4]}]})
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "done_reason": "stop",
                    "message": {"content": json.dumps(ANALYSIS)},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(ANALYSIS)},
                    }
                ]
            },
        )

    settings = Settings(
        generation=Endpoint(runtime=runtime, model="user-selected-model"),
        embedding=Endpoint(model="another-local-embedding"),
        inference=InferenceSettings(source=source, thinking=False, temperature=0.35),
    )
    ai = LocalAI(settings, httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    for name in ("ALPHA_ONLY", "BETA_ONLY"):
        analysis = await ai.analyze(
            {"url": "https://example.com/" + name, "name": name}, PAGE
        )
        embedding = await ai.embed(PAGE, analysis)
        assert embedding["vector"] == [0.6, 0.8]
        assert embedding["model"] == "another-local-embedding"
    chats = [c for c in calls if "messages" in c]
    assert len(chats) == 2
    assert all(len(c["messages"]) == 2 for c in chats)
    assert "BETA_ONLY" not in json.dumps(chats[0])
    assert "ALPHA_ONLY" not in json.dumps(chats[1])
    assert chats[0]["model"] == "user-selected-model"
    if runtime == "ollama":
        assert chats[0]["format"]["additionalProperties"] is False
        assert chats[0]["stream"] is False
        assert ("think" in chats[0]) == (source == "app")
        if source == "app":
            assert chats[0]["think"] is False
        options = chats[0]["options"]
    else:
        assert chats[0]["response_format"]["type"] == "json_schema"
        assert ("reasoning_effort" in chats[0]) == (source == "app")
        if source == "app":
            assert chats[0]["reasoning_effort"] == "none"
        options = chats[0]
    if source == "runtime":
        assert not {
            "temperature",
            "top_k",
            "top_p",
            "min_p",
            "repeat_penalty",
            "presence_penalty",
        }.intersection(options)
    else:
        assert options["temperature"] == 0.35
        assert options["top_k"] == 20
        assert options["top_p"] == 0.95
        assert options["min_p"] == 0
        assert options["repeat_penalty"] == 1
        assert options["presence_penalty"] == 0
    assert calls[1]["input"].startswith(EMBEDDING_PREFIX)
    await ai.close()


@pytest.mark.parametrize("runtime", ["lmstudio", "ollama"])
async def test_app_samplers_and_thinking_are_explicit(runtime):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        message = {"content": json.dumps(ANALYSIS)}
        if runtime == "ollama":
            return httpx.Response(200, json={"done": True, "message": message})
        return httpx.Response(200, json={"choices": [{"message": message}]})

    settings = Settings(
        generation=Endpoint(runtime=runtime),
        inference=InferenceSettings(
            source="app",
            thinking=True,
            top_k=None,
            top_p=None,
            min_p=None,
            repeat_penalty=1.2,
            presence_penalty=1.5,
        ),
    )
    ai = LocalAI(settings, httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    await ai.analyze({"url": "https://example.com/only", "name": "Only"}, PAGE)
    call = calls[0]
    options = call["options"] if runtime == "ollama" else call
    assert options["top_k"] == 0
    assert options["top_p"] == 1
    assert options["min_p"] == 0
    assert options["repeat_penalty"] == 1.2
    assert options["presence_penalty"] == 1.5
    if runtime == "ollama":
        assert call["think"] is True
    else:
        assert call["reasoning_effort"] == "high"
    await ai.close()


@pytest.mark.parametrize("seconds,read", [(0, None), (3600, 3600)])
async def test_model_response_wait_has_no_default_deadline(seconds, read):
    ai = LocalAI(Settings(api_timeout=seconds))
    assert ai.client.timeout.read == read
    assert ai.client.timeout.connect == 10
    assert ai.client.timeout.pool == 10
    assert ai.client.timeout.write == 30
    await ai.close()


@pytest.mark.parametrize(
    "content,finish",
    [("garbage", "stop"), (json.dumps(ANALYSIS), "length"), ("{}", "stop")],
)
async def test_invalid_output_has_only_one_same_url_repair(content, finish):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": {"content": content}}]
            },
        )

    ai = LocalAI(Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    with pytest.raises(AppError) as error:
        await ai.analyze({"url": "https://example.com/only", "name": "Only"}, PAGE)
    assert error.value.code == "analysis_invalid"
    assert len(requests) == 2
    assert all("only" in r["messages"][1]["content"] for r in requests)
    await ai.close()


@pytest.mark.parametrize("vector", [[], [0, 0], ["bad"], [[1, 2]]])
async def test_bad_vectors(vector):
    ai = LocalAI(
        Settings(),
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"data": [{"embedding": vector}]})
            )
        ),
    )
    with pytest.raises(AppError):
        await ai.embed(PAGE, ANALYSIS)
    await ai.close()


async def test_ollama_cloud_models_are_excluded():
    ai = LocalAI(
        Settings(),
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": "local-model"},
                            {"name": "remote", "remote_host": "https://ollama.com"},
                            {"name": "x-cloud"},
                        ]
                    },
                )
            )
        ),
    )
    assert await ai.models(
        Endpoint(runtime="ollama", base_url="http://localhost:11434/v1")
    ) == ["local-model"]
    await ai.close()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/v1",
        "http://192.168.1.2/v1",
        "http://user:pass@localhost:1234/v1",
        "http://localhost:1234/other",
    ],
)
def test_endpoint_restriction(endpoint):
    with pytest.raises(ValidationError):
        Endpoint(base_url=endpoint)
