"""Finite deterministic browser acceptance; no interactive AI browser control."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from helpers import HTML
from playwright.async_api import async_playwright, expect

from bookmark_organization.bookmarks import parse, url_counts
from bookmark_organization.integrity import validate


async def verify():
    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, BOOKMARK_DATA_DIR=directory, PYTHONPATH="src:tests")
        log = tempfile.TemporaryFile()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "helpers:smoke_factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        browser = None
        try:
            async with httpx.AsyncClient(base_url=base) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read().decode()[-4000:])
                    try:
                        if (await client.get("/health")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError("server startup timeout")
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True)
                    for language, lang in [("en-US", "en"), ("ja-JP", "ja")]:
                        context = await browser.new_context(
                            locale=language, viewport={"width": 1440, "height": 900}
                        )
                        page = await context.new_page()
                        errors = []
                        console_messages = []
                        failed_assets = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on(
                            "console",
                            lambda message: (
                                console_messages.append((message.type, message.text))
                                if message.type in {"error", "warning"}
                                else None
                            ),
                        )
                        page.on(
                            "response",
                            lambda response: (
                                failed_assets.append(response.url)
                                if "/static/" in response.url
                                and response.status not in {200, 304}
                                else None
                            ),
                        )
                        await page.goto(base)
                        assert page.url == base + "/"
                        assert await page.title() == "Bookmark Organization"
                        await expect(page.locator("h1").last).to_be_visible()
                        assert await page.locator("vite-error-overlay").count() == 0
                        await expect(page.locator("html")).to_have_attribute(
                            "lang", lang
                        )
                        await expect(page.locator("#language")).to_have_value("auto")
                        rules = page.locator("#organization-rules")
                        await rules.locator("summary").click()
                        await expect(rules.locator("p").first).to_be_visible()
                        await expect(rules).to_contain_text("HTTPX［Python］")
                        for width, height in [(1440, 900), (390, 844)]:
                            await page.set_viewport_size(
                                {"width": width, "height": height}
                            )
                            assert await page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            )
                            if os.environ.get("BOOKMARK_QA_SCREENSHOTS"):
                                screenshot = (
                                    Path(os.environ["BOOKMARK_QA_SCREENSHOTS"])
                                    / f"rules-{lang}-{width}.png"
                                )
                                screenshot.parent.mkdir(parents=True, exist_ok=True)
                                await page.screenshot(path=str(screenshot))
                        await rules.locator("summary").click()
                        await page.set_viewport_size({"width": 1440, "height": 900})
                        # Exercise both inference sources and persist all controls.
                        await page.locator("#settings-toggle").click()
                        initial = await (
                            await context.request.get(base + "/api/settings")
                        ).json()
                        await expect(page.locator("#inference-source")).to_have_value(
                            initial["inference"]["source"]
                        )
                        temperature = page.locator(
                            'input[name="inference.temperature"]'
                        )
                        if initial["inference"]["source"] == "runtime":
                            await expect(temperature).to_be_disabled()
                        else:
                            await expect(temperature).to_be_enabled()
                        await page.locator("#inference-source").select_option("app")
                        await expect(temperature).to_be_enabled()
                        await temperature.fill("0.35")
                        await page.locator(
                            'select[name="inference.thinking"]'
                        ).select_option("off")
                        await page.locator('input[name="enable.top_p"]').uncheck()
                        await page.locator(
                            'input[name="enable.repeat_penalty"]'
                        ).check()
                        await page.locator(
                            'input[name="inference.repeat_penalty"]'
                        ).fill("1.2")
                        await page.locator(
                            'input[name="enable.presence_penalty"]'
                        ).check()
                        await page.locator(
                            'input[name="inference.presence_penalty"]'
                        ).fill("1.5")
                        await page.locator("#settings-form details").evaluate(
                            "e=>e.open=true"
                        )
                        await page.locator('input[name="api_timeout"]').fill("0")
                        async with page.expect_response(
                            lambda r: (
                                r.url.endswith("/api/settings")
                                and r.request.method == "PUT"
                            )
                        ) as saved:
                            await page.locator("#settings-form button.primary").click()
                        assert (await saved.value).status == 200
                        stored = await (
                            await context.request.get(base + "/api/settings")
                        ).json()
                        assert stored["inference"]["source"] == "app"
                        assert stored["inference"]["thinking"] is False
                        assert stored["inference"]["temperature"] == 0.35
                        assert stored["inference"]["top_p"] is None
                        assert stored["inference"]["repeat_penalty"] == 1.2
                        assert stored["inference"]["presence_penalty"] == 1.5
                        assert stored["api_timeout"] == 0
                        await page.reload()
                        await page.locator("#settings-toggle").click()
                        await expect(page.locator("#inference-source")).to_have_value(
                            "app"
                        )
                        await expect(temperature).to_have_value("0.35")
                        await expect(
                            page.locator('input[name="enable.top_p"]')
                        ).not_to_be_checked()

                        # Verify the cloud settings flow without a paid API call.
                        async def model_catalog(route):
                            payload = route.request.post_data_json
                            assert payload["generation"]["runtime"] == "openrouter"
                            assert payload["embedding"]["runtime"] == "lmstudio"
                            assert payload["openrouter_api_key"] == "synthetic-ui-key"
                            assert payload["generation"]["model"] == "test/direct-chat"
                            assert (
                                payload["embedding"]["model"] == "test/direct-embedding"
                            )
                            await route.fulfill(
                                json={
                                    "generation": ["test/chat"],
                                    "embedding": [initial["embedding"]["model"]],
                                }
                            )

                        await page.route("**/api/settings/probe", model_catalog)
                        await page.locator(
                            'select[name="generation.runtime"]'
                        ).select_option("openrouter")
                        await expect(
                            page.locator("#openrouter-settings")
                        ).to_be_visible()
                        await expect(
                            page.locator('input[name="generation.base_url"]')
                        ).to_have_value("https://openrouter.ai/api/v1")
                        await expect(
                            page.locator('input[name="generation.base_url"]')
                        ).to_have_attribute("readonly", "")
                        await page.locator("#openrouter-api-key").fill(
                            "synthetic-ui-key"
                        )
                        await page.locator('input[name="generation.model"]').fill(
                            "test/direct-chat"
                        )
                        await page.locator('input[name="embedding.model"]').fill(
                            "test/direct-embedding"
                        )
                        await page.locator("#probe").click()
                        await expect(
                            page.locator('input[name="embedding.model"]')
                        ).to_have_value("test/direct-embedding")
                        await expect(
                            page.locator("#generation-models option").last
                        ).to_have_attribute("value", "test/chat")
                        await expect(
                            page.locator('input[name="generation.model"]')
                        ).to_have_value("test/direct-chat")
                        async with page.expect_response(
                            lambda r: (
                                r.url.endswith("/api/settings")
                                and r.request.method == "PUT"
                            )
                        ) as saved:
                            await page.locator("#settings-form button.primary").click()
                        assert (await saved.value).status == 200
                        await expect(page.locator("#openrouter-api-key")).to_have_value(
                            ""
                        )
                        await page.reload()
                        await page.locator("#settings-toggle").click()
                        await expect(
                            page.locator('select[name="generation.runtime"]')
                        ).to_have_value("openrouter")
                        await expect(
                            page.locator('select[name="embedding.runtime"]')
                        ).to_have_value("lmstudio")
                        await expect(
                            page.locator('input[name="generation.model"]')
                        ).to_have_value("test/direct-chat")
                        await expect(
                            page.locator('input[name="embedding.model"]')
                        ).to_have_value("test/direct-embedding")
                        assert "synthetic-ui-key" not in await page.content()
                        response = await context.request.get(base + "/api/settings")
                        assert "synthetic-ui-key" not in await response.text()
                        assert await page.title() == "Bookmark Organization"
                        assert page.url == base + "/"
                        for width in [1440, 390]:
                            await page.set_viewport_size(
                                {"width": width, "height": 900}
                            )
                            assert await page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            )
                            for label in await page.locator(
                                "#inference-controls .check-label"
                            ).all():
                                checkbox = await label.locator("input").bounding_box()
                                bounds = await label.bounding_box()
                                assert checkbox and abs(checkbox["width"] - 16) < 1
                                assert bounds and bounds["height"] < 60
                            qa_directory = os.environ.get("BOOKMARK_QA_DIR")
                            if qa_directory:
                                image = (
                                    Path(qa_directory)
                                    / f"openrouter-{lang}-{width}.png"
                                )
                                image.parent.mkdir(parents=True, exist_ok=True)
                                await page.locator("#settings-panel").screenshot(
                                    path=str(image)
                                )
                        await page.set_viewport_size({"width": 1440, "height": 900})
                        await page.unroute("**/api/settings/probe", model_catalog)
                        await page.locator(
                            'select[name="generation.runtime"]'
                        ).select_option("lmstudio")
                        await page.locator('input[name="generation.model"]').fill(
                            initial["generation"]["model"]
                        )
                        await page.locator('input[name="embedding.model"]').fill(
                            initial["embedding"]["model"]
                        )
                        await expect(
                            page.locator("#openrouter-settings")
                        ).to_be_hidden()
                        await page.locator("#inference-source").select_option("runtime")
                        async with page.expect_response(
                            lambda r: (
                                r.url.endswith("/api/settings")
                                and r.request.method == "PUT"
                            )
                        ) as saved:
                            await page.locator("#settings-form button.primary").click()
                        assert (await saved.value).status == 200
                        await page.reload()
                        await page.locator("#settings-toggle").click()
                        await expect(page.locator("#inference-source")).to_have_value(
                            "runtime"
                        )
                        await expect(temperature).to_be_disabled()
                        await expect(temperature).to_have_value("0.35")
                        await page.locator("#settings-toggle").click()
                        await page.locator("#html-file").set_input_files(
                            {
                                "name": "synthetic.html",
                                "mimeType": "text/html",
                                "buffer": HTML,
                            }
                        )
                        await page.locator("#import-form button").click()
                        await page.wait_for_url("**/?project=*")
                        await page.locator(".folder-check").first.wait_for()
                        checks = page.locator(".folder-check")
                        tree = await page.locator("#tree-data").text_content()
                        nodes = json.loads(tree)
                        ids = [
                            n["id"]
                            for n in nodes
                            if n["kind"] == "folder" and n["name"] in {"A", "B"}
                        ]
                        for identifier in ids:
                            await page.locator(
                                f'.folder-check[value="{identifier}"]'
                            ).check()
                        assert await page.locator("#destination option").count() == 2
                        # Cancel running and paused jobs at both responsive widths.
                        for width, height in [(1440, 900), (390, 844)]:
                            await page.set_viewport_size(
                                {"width": width, "height": height}
                            )
                            for paused in [False, True]:
                                await page.locator("#scope-form button").click()
                                await page.wait_for_url("**&job=*")
                                cancelled_job = await page.locator(
                                    ".job"
                                ).get_attribute("data-job")
                                if paused:
                                    await page.locator(
                                        '[data-action="pause"]:enabled'
                                    ).click()
                                    await expect(
                                        page.locator(".job")
                                    ).to_have_attribute("data-state", "paused")
                                await page.locator(
                                    '[data-action="cancel"]:enabled'
                                ).click()
                                await expect(page.locator(".job")).to_have_attribute(
                                    "data-state", "cancelled"
                                )
                                await expect(page.locator(".job h2")).to_contain_text(
                                    "Cancelled" if lang == "en" else "キャンセル済み"
                                )
                                for action in [
                                    "pause",
                                    "resume",
                                    "retry-failed",
                                    "cancel",
                                ]:
                                    await expect(
                                        page.locator(f'[data-action="{action}"]')
                                    ).to_be_disabled()
                                await expect(
                                    page.locator('[data-action="proposal"]')
                                ).to_have_count(0)
                                assert await page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                                if paused and os.environ.get("BOOKMARK_QA_SCREENSHOTS"):
                                    screenshot = (
                                        Path(os.environ["BOOKMARK_QA_SCREENSHOTS"])
                                        / f"cancelled-{lang}-{width}.png"
                                    )
                                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                                    await page.locator(
                                        ".job"
                                    ).scroll_into_view_if_needed()
                                    await page.screenshot(path=str(screenshot))
                                await page.reload()
                                await expect(page.locator(".job")).to_have_attribute(
                                    "data-state", "cancelled"
                                )
                                assert (
                                    await (
                                        await context.request.get(
                                            base + "/api/jobs/" + cancelled_job
                                        )
                                    ).json()
                                )["state"] == "cancelled"
                        await page.set_viewport_size({"width": 1440, "height": 900})
                        await page.locator("#scope-form button").click()
                        await page.wait_for_url("**&job=*")
                        await page.locator('[data-action="pause"]:enabled').click()
                        await expect(page.locator(".job")).to_have_attribute(
                            "data-state", "paused"
                        )
                        await page.locator('[data-action="resume"]:enabled').click()
                        await expect(page.locator(".job")).to_have_attribute(
                            "data-state", "complete", timeout=20000
                        )
                        # Fragments use the same language catalog.
                        expected = (
                            "Processing finished"
                            if lang == "en"
                            else "処理が終了しました"
                        )
                        await expect(page.locator(".job h2")).to_contain_text(expected)
                        await page.locator('[data-action="proposal"]').click()
                        await page.wait_for_url("**&proposal=*")
                        await page.locator(".edit-name").first.wait_for()
                        names = await page.locator(".edit-name").evaluate_all(
                            "elements=>elements.map(e=>e.value)"
                        )
                        assert sum("｜" in name for name in names) == 3
                        await expect(
                            page.locator(".edit-parent").first
                        ).to_contain_text("開発・プログラミング")
                        await page.locator(".edit-name").first.fill(
                            "Edited 日本語 name"
                        )
                        prior = await page.locator("#proposal-section").get_attribute(
                            "data-proposal"
                        )
                        await page.locator(".save-item").first.click()
                        await page.wait_for_function(
                            "prior=>document.querySelector('#proposal-section').dataset.proposal!==prior",
                            arg=prior,
                        )
                        await expect(page.locator(".edit-name").first).to_have_value(
                            "Edited 日本語 name"
                        )
                        await page.locator("#search").fill("Edited")
                        await expect(
                            page.locator("#comparison tbody tr")
                        ).to_have_count(1)
                        await page.locator("#search").fill("")
                        await expect(
                            page.locator("#comparison tbody tr")
                        ).to_have_count(4)
                        proposal = await page.locator(
                            "#proposal-section"
                        ).get_attribute("data-proposal")
                        result = await (
                            await context.request.get(
                                base + "/api/proposals/" + proposal
                            )
                        ).json()
                        validate(result["original"], result["tree"], result["targets"])
                        async with page.expect_download() as download_info:
                            await page.locator("#export").click()
                        download = await download_info.value
                        path = await download.path()
                        assert url_counts(parse(Path(path).read_bytes())) == url_counts(
                            parse(HTML)
                        )
                        original_href = await page.locator(".small-link").get_attribute(
                            "href"
                        )
                        assert (
                            await (
                                await context.request.get(base + original_href)
                            ).body()
                            == HTML
                        )
                        # Palette/type/focus and localized responsive behavior are deterministic assertions.
                        for size in [
                            {"width": 1440, "height": 900},
                            {"width": 390, "height": 844},
                        ]:
                            await page.set_viewport_size(size)
                            widths = await page.evaluate("""() => ({
                              viewport: innerWidth, document: document.documentElement.scrollWidth,
                              outside: [...document.querySelectorAll('body *')].filter(e => {
                                const r=e.getBoundingClientRect();
                                return r.width>0 && r.right>innerWidth+1 && !e.closest('.table-scroll');
                              }).slice(0,12).map(e=>({
                                tag:e.tagName,id:e.id,cls:e.className,
                                width:e.getBoundingClientRect().width,
                                right:e.getBoundingClientRect().right
                              }))
                            })""")
                            assert widths["document"] <= widths["viewport"], widths
                            assert await page.locator("body").evaluate(
                                "e=>getComputedStyle(e).color==='rgb(24, 36, 51)'"
                            )
                            assert await page.locator("h1").first.evaluate(
                                "e=>getComputedStyle(e).fontSize==='28px'"
                            )
                            assert await page.locator("#export").evaluate(
                                "e=>e.tabIndex===0"
                            )
                            await page.locator("#export").focus()
                            assert await page.locator("#export").evaluate(
                                "e=>e===document.activeElement"
                            )
                        # Manual override survives reload without modifying proposal or job.
                        other = "ja" if lang == "en" else "en"
                        await page.locator("#language").select_option(other)
                        await expect(page.locator("html")).to_have_attribute(
                            "lang", other
                        )
                        await page.reload()
                        await expect(page.locator("#language")).to_have_value(other)
                        unchanged = await (
                            await context.request.get(
                                base + "/api/proposals/" + proposal
                            )
                        ).json()
                        assert unchanged["tree"] == result["tree"]
                        assert await page.locator(".folder-check:checked").count() == 2
                        # Invalid selection is presented from the current locale.
                        await page.locator("#scope-all").uncheck()
                        for check in await checks.all():
                            await check.uncheck()
                        await page.locator("#scope-form button").click()
                        await expect(page.locator("#alert")).to_be_visible()
                        assert (await page.locator("#alert").text_content()).strip()
                        assert errors == [], errors
                        unexpected_console = [
                            text
                            for _, text in console_messages
                            if not any(
                                f"status of {status}" in text
                                for status in [400, 404, 422]
                            )
                        ]
                        assert unexpected_console == [], unexpected_console
                        assert failed_assets == [], failed_assets
                        await context.close()
                    await browser.close()
                    browser = None
                # CSRF and Host/Origin restrictions remain effective on the real server.
                assert (
                    await client.post("/api/language", json={"preference": "en"})
                ).status_code == 403
                assert (
                    await client.get("/health", headers={"Host": "evil.example"})
                ).status_code == 400
        finally:
            if browser:
                await browser.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()
    print(
        "V3 passed: real-server workflow, cancel/restart, pause/resume, edits/export, locale persistence, layouts, focus and isolation."
    )


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(verify(), timeout=175))
