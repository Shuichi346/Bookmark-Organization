"""Actual local-model acceptance on two public-page fixtures and one 404 fixture."""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import numpy as np

from bookmark_organization.bookmarks import export, parse, url_counts
from bookmark_organization.db import Store
from bookmark_organization.jobs import create_job, job_state
from bookmark_organization.llm import LocalAI
from bookmark_organization.organizing import propose
from bookmark_organization.schemas import InferenceSettings, JobRequest, Settings

FIXTURES = [
    (
        "https://fastapi.tiangolo.com/",
        "FastAPI",
        "FastAPI is a modern, fast web framework for building APIs with Python based "
        "on standard Python type hints. It provides automatic OpenAPI documentation, "
        "request validation with Pydantic and asynchronous request handling. "
        "Developers use it to build HTTP API services.",
    ),
    (
        "https://www.typescriptlang.org/docs/",
        "TypeScript Documentation",
        "TypeScript is JavaScript with syntax for types. It is a strongly typed "
        "programming language that builds on JavaScript, giving better tooling at any "
        "scale. This handbook teaches types, interfaces, narrowing and generic "
        "functions to JavaScript developers.",
    ),
]


async def verify(settings_path: Path):
    settings = Settings.model_validate_json(settings_path.read_text())
    metadata = json.loads(subprocess.check_output(["lms", "ls", "--json"], timeout=20))
    generation = next(m for m in metadata if m["modelKey"] == settings.generation.model)
    embedding = next(m for m in metadata if m["modelKey"] == settings.embedding.model)
    assert generation["path"].endswith(
        "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf"
    )
    assert embedding["path"].endswith("embeddinggemma-2-Q8_0.gguf")
    assert settings.generation.runtime == settings.embedding.runtime == "lmstudio"
    calls = []
    # The product may wait indefinitely; acceptance always has a finite deadline.
    client = httpx.AsyncClient(
        trust_env=False, timeout=httpx.Timeout(connect=10, read=550, write=30, pool=10)
    )

    async def record(request):
        if request.url.path.endswith("/chat/completions"):
            calls.append(json.loads(request.content))

    client.event_hooks["request"] = [record]
    ai = LocalAI(settings, client)
    try:
        await ai.ensure_available(settings.generation)
        await ai.ensure_available(settings.embedding, role="embedding")
        nodes = parse(
            b'<DL><H3>Sample</H3><DL><A HREF="https://fastapi.tiangolo.com/">FastAPI</A>'
            b'<A HREF="https://www.typescriptlang.org/docs/">TypeScript</A>'
            b'<A HREF="https://example.com/synthetic-404">Missing</A></DL></DL>'
        )
        bookmarks = [n for n in nodes if n["kind"] == "bookmark"]
        items = []
        samples = []
        for index, (bookmark, (url, title, text)) in enumerate(
            zip(bookmarks, FIXTURES)
        ):
            settings.inference = InferenceSettings(
                source="runtime" if index == 0 else "app", thinking=False
            )
            assert bookmark["url"] == url
            page = {"status": "ok", "title": title, "description": title, "text": text}
            analysis = await ai.analyze(bookmark, page)
            vector = await ai.embed(page, analysis)
            assert np.isfinite(vector["vector"]).all()
            items.append(
                {
                    "bookmark": bookmark["id"],
                    "state": "complete",
                    "analysis": analysis,
                    "embedding": vector,
                    "retrieval": page,
                }
            )
            samples.append(
                {
                    "url": url,
                    "inference_source": settings.inference.source,
                    "analysis": analysis,
                    "dimensions": vector["dimensions"],
                }
            )
        items.append(
            {
                "bookmark": bookmarks[2]["id"],
                "state": "retrieval_failed",
                "retrieval": {"status": "not_found", "http_status": 404},
            }
        )
        assert (
            items[0]["embedding"]["dimensions"] == items[1]["embedding"]["dimensions"]
        )
        # The 404 is deliberately synthetic; no unrelated website URL is probed.
        for call in calls:
            assert len(call["messages"]) == 2
            text = call["messages"][1]["content"]
            assert not (FIXTURES[0][0] in text and FIXTURES[1][0] in text)
        assert 2 <= len(calls) <= 4
        assert "temperature" not in calls[0]
        assert "reasoning_effort" not in calls[0]
        assert calls[-1]["temperature"] == 0.7
        assert calls[-1]["reasoning_effort"] == "none"
        assert calls[-1]["top_k"] == 20
        assert calls[-1]["top_p"] == 0.95
        assert calls[-1]["min_p"] == 0
        assert calls[-1]["repeat_penalty"] == 1
        assert calls[-1]["presence_penalty"] == 0
        with TemporaryDirectory() as directory:
            store = Store(Path(directory))
            store.save_settings(settings)
            project = store.import_html(export(nodes), "synthetic.html")
            actual = store.tree(project)
            job = create_job(
                store, project, JobRequest(all=True, token="real-model-test")
            )
            snapshot = job_state(store, job)["snapshot"]
            # Imported UUIDs differ after HTML serialization; map by original URL.
            mapping = {n["url"]: n["id"] for n in actual if n["kind"] == "bookmark"}
            for item, bookmark in zip(items, bookmarks):
                item["bookmark"] = mapping[bookmark["url"]]
            proposal = propose(actual, snapshot, items, False)
            output = export(proposal)
            assert url_counts(parse(output)) == url_counts(actual)
        print(
            json.dumps(
                {
                    "result": "V4 passed",
                    "runtime_cli": subprocess.check_output(
                        ["lms", "--version"], timeout=10
                    )
                    .decode()
                    .strip(),
                    "generation": generation["path"],
                    "generation_api_id": settings.generation.model,
                    "embedding": embedding["path"],
                    "embedding_api_id": settings.embedding.model,
                    "independent_requests": len(calls),
                    "samples": samples,
                    "export_count": len(bookmarks),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await ai.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(verify(args.settings), timeout=1190))
