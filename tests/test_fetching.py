import asyncio
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
    assert requests[0].extensions["sni_hostname"] == "example.com"
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


async def test_https_sni_through_real_async_transport(public_dns, monkeypatch):
    from anyio._core._sockets import idna2008_resolve
    from httpcore._backends.anyio import AnyIOBackend
    from httpcore._backends.base import AsyncNetworkStream

    html = (
        "<html><title>Documentation</title><article><p>"
        + "Useful developer documentation. " * 20
        + "</p></article></html>"
    ).encode()
    handshakes = []
    requests = []
    connections = []

    class Socket(AsyncNetworkStream):
        def __init__(self):
            self.reply = (
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n"
                + f"Content-Length: {len(html)}\r\n\r\n".encode()
                + html
            )

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            # Exercise the installed AnyIO hostname validation that rejected bytes.
            handshakes.append(idna2008_resolve(server_hostname))
            return self

        async def read(self, max_bytes, timeout=None):
            reply, self.reply = self.reply, b""
            return reply

        async def write(self, buffer, timeout=None):
            requests.append(buffer)

        async def aclose(self):
            pass

    async def connect_tcp(self, host, port, **kwargs):
        connections.append((host, port))
        return Socket()

    monkeypatch.setattr(AnyIOBackend, "connect_tcp", connect_tcp)
    fetcher = Fetcher(Settings())
    try:
        result = await fetcher.fetch("https://example.com/page")
        assert result["status"] == "ok"
        assert handshakes == [b"example.com"]
        assert connections == [("93.184.215.14", 443)]
        assert b"Host: example.com\r\n" in b"".join(requests)
    finally:
        await fetcher.close()


async def test_concurrent_requests_and_redirects_are_spaced(public_dns):
    starts = []

    def handle(request):
        starts.append(asyncio.get_running_loop().time())
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "/target"})
        return httpx.Response(200, text="body", headers={"content-type": "text/html"})

    fetcher = Fetcher(
        Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    try:
        results = await asyncio.gather(
            fetcher.response("https://example.com/redirect"),
            fetcher.response("https://another.example/page"),
        )
        assert all(result[0] == 200 for result in results)
        assert len(starts) == 3
        assert all(b - a >= 0.5 for a, b in zip(starts, starts[1:]))
    finally:
        await fetcher.close()


async def test_failed_requests_and_new_clients_share_pacing(public_dns, tmp_path):
    from bookmark_organization.db import Store
    from bookmark_organization.jobs import Worker

    starts = []
    worker = Worker(Store(tmp_path))

    def handle(request):
        starts.append(asyncio.get_running_loop().time())
        raise httpx.ConnectError("unreachable")

    for _ in range(2):
        fetcher = worker.fetch_factory(Settings())
        await fetcher.client.aclose()
        fetcher.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        try:
            assert (await fetcher.fetch("https://example.com"))["status"] == (
                "connection_failed"
            )
        finally:
            await fetcher.close()
    assert len(starts) == 2
    assert starts[1] - starts[0] >= 0.5
