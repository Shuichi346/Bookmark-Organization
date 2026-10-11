import socket

import httpx
import pytest

from bookmark_organization.fetching import Fetcher, public_address
from bookmark_organization.schemas import AppError, Settings


@pytest.fixture
def public_dns(monkeypatch):
    async def addresses(self, host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", addresses)


@pytest.mark.parametrize(
    "status,expected",
    [
        (200, "ok"),
        (404, "not_found"),
        (403, "denied"),
        (401, "denied"),
        (500, "http_error"),
    ],
)
async def test_retrieval_states_and_pinned_connection(public_dns, status, expected):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status,
            headers={"content-type": "text/html"},
            text="<html><title>Title</title><meta name='description' content='Description'><article><p>"
            + "Useful documentation for developers. " * 20
            + "</p></article></html>",
        )

    fetcher = Fetcher(
        Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    result = await fetcher.fetch("https://example.com/page")
    assert result["status"] == expected
    assert requests[0].url.host == "93.184.215.14"
    assert requests[0].headers["host"] == "example.com"
    assert requests[0].extensions["sni_hostname"] == b"example.com"
    await fetcher.close()


async def test_private_mixed_dns_and_redirect_block(monkeypatch):
    async def addresses(self, host, port, **kwargs):
        values = ["127.0.0.1"] if host == "localhost" else ["93.184.215.14"]
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, port))
            for value in values
        ]

    monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", addresses)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://localhost/private"})

    fetcher = Fetcher(
        Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    assert (await fetcher.fetch("https://example.com"))["status"] == "restricted"
    assert len(calls) == 1
    with pytest.raises(AppError):
        await public_address("http://localhost/")
    assert (await fetcher.fetch("mailto:hello@example.com"))["status"] == "unsupported"
    await fetcher.close()


async def test_timeout_empty_content_limit_and_rendering_fallback(
    public_dns, monkeypatch
):
    def timeout(request):
        raise httpx.ReadTimeout("timeout")

    f = Fetcher(Settings(), httpx.AsyncClient(transport=httpx.MockTransport(timeout)))
    assert (await f.fetch("https://example.com"))["status"] == "timeout"
    await f.close()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text="<html></html>", headers={"content-type": "text/html"}
            )
        )
    )
    f = Fetcher(Settings(rendering=True), client)
    rendered = []

    async def render(url):
        rendered.append(url)
        return "Rendered JavaScript developer documentation. " * 10

    monkeypatch.setattr(f, "rendered", render)
    assert (await f.fetch("https://example.com"))["status"] == "ok"
    assert rendered
    await f.close()
    f = Fetcher(
        Settings(max_bytes=1024),
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=b"x" * 2048, headers={"content-type": "text/html"}
                )
            )
        ),
    )
    assert (await f.fetch("https://example.com"))["status"] == "extraction_failed"
    await f.close()
