import asyncio

from bookmark_organization.app import create_app
from bookmark_organization.jobs import Worker
from bookmark_organization.policy import LEGACY_PROMPT_VERSION, PROMPT_VERSION

HTML = b"""<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>
<DT><H3 ADD_DATE="12">A</H3><DL><p>
<DT><A HREF="https://example.com/alpha" ADD_DATE="13">Alpha &amp; One</A>
<DT><H3>Nested</H3><DL><DT><A HREF="https://example.com/beta">Beta</A></DL>
</DL><DT><H3>B</H3><DL><DT><A HREF="https://example.com/alpha">Duplicate</A>
<DT><A HREF="https://example.com/missing">Missing</A></DL>
<DT><H3>Untouched</H3><DL><DT><A HREF="https://example.com/keep">Keep</A></DL>
<DT><H3>Empty</H3><DL></DL><DT><A HREF="mailto:test@example.com">Mail</A></DL>"""

ANALYSIS = {
    "suggested_name": "Example ドキュメント",
    "summary": "開発用ドキュメントです。",
    "purpose": "開発者が技術を学ぶための公式ドキュメント。",
    "candidate_categories": ["開発"],
}
PURPOSE_ANALYSIS = {
    **ANALYSIS,
    "suggested_name": "開発機能を調べる｜Example Docs",
    "candidate_categories": ["開発・プログラミング/ドキュメント・技術資料"],
}
PAGE = {
    "status": "ok",
    "title": "Example",
    "description": "Developer documentation",
    "text": "Developer documentation for a programming library and web framework. " * 8,
}


class FakeFetcher:
    calls: list[str] = []

    def __init__(self, settings):
        pass

    async def fetch(self, url):
        self.calls.append(url)
        await asyncio.sleep(0.08)
        if "missing" in url:
            return {"status": "not_found", "http_status": 404}
        if url.startswith("mailto:"):
            return {"status": "unsupported"}
        return dict(PAGE, final_url=url)

    async def close(self):
        pass


class FakeAI:
    calls: list[str] = []

    def __init__(self, settings):
        self.settings = settings
        self.prompt_version = PROMPT_VERSION

    async def ensure_available(self, endpoint, *, role="generation"):
        pass

    async def analyze(self, bookmark, page):
        self.calls.append(bookmark["id"])
        await asyncio.sleep(0.08)
        return dict(
            ANALYSIS
            if self.prompt_version == LEGACY_PROMPT_VERSION
            else PURPOSE_ANALYSIS
        )

    async def embed(self, page, analysis):
        await asyncio.sleep(0.08)
        return {
            "model": self.settings.embedding.model,
            "dimensions": 3,
            "content_hash": "synthetic",
            "prompt_version": self.prompt_version,
            "vector": [1.0, 0.0, 0.0],
        }

    async def close(self):
        pass


def make_worker(store):
    return Worker(store, FakeFetcher, FakeAI)


def smoke_factory():
    return create_app(worker_factory=make_worker)


def shutdown_smoke_factory():
    class WaitingAI(FakeAI):
        async def analyze(self, bookmark, page):
            await asyncio.Event().wait()
            return await super().analyze(bookmark, page)

    return create_app(
        worker_factory=lambda store: Worker(store, FakeFetcher, WaitingAI)
    )
