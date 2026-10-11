import asyncio
import ipaddress
import logging
import socket
from typing import cast
from urllib.parse import urlsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup

from bookmark_organization.schemas import AppError, Settings

logger = logging.getLogger(__name__)


class RequestPacer:
    """Space request starts across concurrent pages, redirects and retry batches."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.next_start = 0.0

    async def wait(self):
        async with self.lock:
            loop = asyncio.get_running_loop()
            delay = self.next_start - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self.next_start = loop.time() + 0.5


async def public_address(url: str) -> tuple[str, str]:
    try:
        u = urlsplit(url)
        if (
            u.scheme not in {"http", "https"}
            or not u.hostname
            or u.username
            or u.password
        ):
            raise AppError("unsupported")
        addresses = await asyncio.get_running_loop().getaddrinfo(
            u.hostname,
            u.port or (443 if u.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (ValueError, socket.gaierror) as exc:
        raise AppError("connection_failed") from exc
    ips = {cast(str, a[4][0]) for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise AppError("restricted")
    return sorted(ips)[0], u.hostname


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        pacer: RequestPacer | None = None,
    ):
        self.settings = settings
        self.pacer = pacer or RequestPacer()
        self.client = client or httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=6, max_keepalive_connections=4),
            timeout=httpx.Timeout(
                settings.read_timeout,
                connect=settings.connect_timeout,
                pool=settings.connect_timeout,
            ),
        )
        self.playwright = None
        self.browser = None

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        await self.client.aclose()

    async def response(self, url: str) -> tuple[int, bytes, str, dict]:
        """Pin the TCP destination to a validated IP, retain TLS SNI and Host."""
        current = url
        for _ in range(self.settings.redirects + 1):
            ip, hostname = await public_address(current)
            original = httpx.URL(current)
            pinned = original.copy_with(host=ip)
            await self.pacer.wait()
            async with self.client.stream(
                "GET",
                pinned,
                headers={
                    "Host": original.netloc.decode(),
                    "User-Agent": "BookmarkOrganization/0.1",
                },
                extensions={"sni_hostname": hostname},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise AppError("http_error")
                    current = str(original.join(location))
                    continue
                content = bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content) > self.settings.max_bytes:
                        raise AppError("extraction_failed")
                return (
                    response.status_code,
                    bytes(content),
                    current,
                    dict(response.headers),
                )
        raise AppError("http_error")

    async def rendered(self, url: str) -> str:
        from playwright.async_api import async_playwright

        if not self.browser:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
        context = await self.browser.new_context(service_workers="block")
        budget = self.settings.max_bytes * 2

        async def route(request_route):
            nonlocal budget
            try:
                if request_route.request.method != "GET" or budget <= 0:
                    await request_route.abort()
                    return
                status, body, _, headers = await self.response(
                    request_route.request.url
                )
                budget -= len(body)
                # Browser cannot make unchecked connections; all resources use the pinned client.
                await request_route.fulfill(
                    status=status,
                    body=body,
                    content_type=headers.get("content-type", "text/plain"),
                )
            except (AppError, httpx.HTTPError):
                await request_route.abort()

        try:
            await context.route("**/*", route)
            await context.route_web_socket("**/*", lambda ws: ws.close())
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            return (await page.locator("body").inner_text())[: self.settings.max_bytes]
        finally:
            await context.close()

    async def fetch(self, url: str) -> dict:
        try:
            async with asyncio.timeout(self.settings.overall_timeout):
                status, raw, final, headers = await self.response(url)
                if status >= 400:
                    code = (
                        "not_found"
                        if status == 404
                        else ("denied" if status in {401, 403} else "http_error")
                    )
                    return {"status": code, "http_status": status}
                if status < 200 or status >= 300:
                    return {"status": "http_error", "http_status": status}
                if not any(
                    kind in headers.get("content-type", "").lower()
                    for kind in ("html", "text/plain", "xhtml")
                ):
                    return {"status": "extraction_failed"}
                soup = BeautifulSoup(raw, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                meta = soup.find("meta", attrs={"name": "description"})
                description = str(meta.get("content", "")) if meta else ""
                text = trafilatura.extract(raw) or ""
            if len(text.strip()) < 80 and self.settings.rendering:
                async with asyncio.timeout(30):
                    text = await self.rendered(final)
            if len(text.strip()) < 80:
                return {"status": "extraction_failed"}
            return {
                "status": "ok",
                "final_url": final,
                "title": title[:500],
                "description": description[:2000],
                "text": text[:24000],
            }
        except AppError as exc:
            return {"status": exc.code}
        except (TimeoutError, httpx.TimeoutException):
            return {"status": "timeout"}
        except httpx.HTTPError:
            return {"status": "connection_failed"}
        except Exception:
            logger.exception("Unexpected page retrieval failure")
            return {"status": "extraction_failed"}
