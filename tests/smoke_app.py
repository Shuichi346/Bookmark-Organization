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
                "-c",
                "from bookmark_organization.app import serve; "
                "from helpers import smoke_factory; "
                f"serve(smoke_factory(), port={port})",
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

                        # Codex is fixed subscription analysis, with local embeddings.
                        async def codex_catalog(route):
                            payload = route.request.post_data_json
                            assert payload["generation"] == {
                                "runtime": "codex",
                                "base_url": "",
                                "model": "gpt-6-luna",
                            }
                            assert payload["embedding"]["runtime"] == "lmstudio"
                            assert payload["openrouter_api_key"] == ""
                            await route.fulfill(
                                json={
                                    "generation": ["gpt-6-luna"],
                                    "embedding": [initial["embedding"]["model"]],
                                }
                            )

                        await page.route("**/api/settings/probe", codex_catalog)
                        await page.locator(
                            'select[name="generation.runtime"]'
                        ).select_option("codex")
                        await expect(page.locator("#codex-settings")).to_be_visible()
                        await expect(page.locator("#codex-settings")).to_contain_text(
                            "low"
                        )
                        await expect(
                            page.locator("#openrouter-settings")
                        ).to_be_hidden()
                        await expect(
                            page.locator('input[name="generation.model"]')
                        ).to_have_value("gpt-6-luna")
                        await expect(
                            page.locator('input[name="generation.model"]')
                        ).to_have_attribute("readonly", "")
                        await expect(
                            page.locator("#generation-endpoint-label")
                        ).to_be_hidden()
                        await expect(
                            page.locator("#generation-candidates-label")
                        ).to_be_hidden()
                        await expect(page.locator("#inference-settings")).to_be_hidden()
                        assert (
                            await page.locator(
                                'select[name="embedding.runtime"] option[value="codex"]'
                            ).count()
                            == 0
                        )
                        await page.locator("#probe").click()
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
                        await expect(
                            page.locator('select[name="generation.runtime"]')
                        ).to_have_value("codex")
                        await expect(
                            page.locator('input[name="generation.model"]')
                        ).to_have_value("gpt-6-luna")
                        stored = await (
                            await context.request.get(base + "/api/settings")
                        ).json()
                        assert stored["inference"]["temperature"] == 0.35
                        assert stored["embedding"]["model"] == "test/direct-embedding"
                        for width in [1440, 390]:
                            await page.set_viewport_size(
                                {"width": width, "height": 900}
                            )
                            assert await page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            )
                            if os.environ.get("BOOKMARK_QA_DIR"):
                                image = (
                                    Path(os.environ["BOOKMARK_QA_DIR"])
                                    / f"codex-{lang}-{width}.png"
                                )
                                image.parent.mkdir(parents=True, exist_ok=True)
                                await page.locator("#settings-panel").screenshot(
                                    path=str(image)
                                )
                        await page.set_viewport_size({"width": 1440, "height": 900})
                        await page.unroute("**/api/settings/probe", codex_catalog)
                        await page.locator(
                            'select[name="generation.runtime"]'
                        ).select_option("lmstudio")
                        await expect(page.locator("#codex-settings")).to_be_hidden()
                        await expect(
                            page.locator("#inference-settings")
                        ).to_be_visible()
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
                        details = page.locator("#comparison tbody details")
                        await expect(details).to_have_count(3)
                        await expect(details.first.locator("summary")).to_have_text(
                            "Analysis details" if lang == "en" else "分析の詳細"
                        )
                        await details.first.locator("summary").click()
                        await expect(details.first.locator("p").first).to_have_text(
                            "開発用ドキュメントです。"
                        )
                        await expect(details.first.locator("p").last).to_have_text(
                            "開発者が技術を学ぶための公式ドキュメント。"
                        )
                        prior_parent = await page.locator(
                            ".edit-parent"
                        ).first.input_value()
                        await page.locator(".edit-parent").first.select_option(ids[0])
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
                        # A saved move updates the in-memory scope tree immediately.
                        await page.locator("#continue-organizing").click()
                        await page.locator(
                            f'.folder-check[value="{prior_parent}"]'
                        ).check()
                        remaining_in_folder = sum(
                            n["kind"] == "bookmark" and n["parent"] == prior_parent
                            for n in result["tree"]
                        )
                        await expect(page.locator("#selected-count")).to_contain_text(
                            str(remaining_in_folder)
                        )
                        await page.locator(
                            f'.folder-check[value="{prior_parent}"]'
                        ).uncheck()
                        for identifier in ids:
                            await page.locator(
                                f'.folder-check[value="{identifier}"]'
                            ).check()
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
                        # Continue from the saved edit, changing rules for only one folder.
                        await page.locator("#continue-organizing").click()
                        await expect(page.locator("#scope-all")).not_to_be_checked()
                        assert await page.locator(".folder-check:checked").count() == 0
                        untouched_folder = next(
                            n["id"]
                            for n in nodes
                            if n["kind"] == "folder" and n["name"] == "Untouched"
                        )
                        await page.locator(
                            f'.folder-check[value="{untouched_folder}"]'
                        ).check()
                        await page.locator("#naming-mode").select_option("purpose")
                        await page.locator("#folder-mode").select_option("purpose")
                        await expect(page.locator("#naming-prompt")).to_be_disabled()
                        await page.locator("#naming-mode").select_option("custom")
                        await expect(page.locator("#naming-prompt")).to_be_enabled()
                        await expect(page.locator("#folder-prompt")).to_be_disabled()
                        await page.locator("#folder-mode").select_option("custom")
                        naming_rule = "サービス名を先頭にして英語で短く命名する"
                        folder_rule = (
                            "JSライブラリ関係、Python、ユーティリティ系で分ける"
                        )
                        await page.locator("#naming-prompt").fill(naming_rule)
                        await page.locator("#folder-prompt").fill(folder_rule)
                        # Each selector keeps its draft while inactive, across reload.
                        await page.locator("#naming-mode").select_option("purpose")
                        await expect(page.locator("#naming-prompt")).to_be_disabled()
                        await expect(page.locator("#folder-prompt")).to_be_enabled()
                        await page.reload()
                        await expect(page.locator("#naming-mode")).to_have_value(
                            "purpose"
                        )
                        await expect(page.locator("#folder-mode")).to_have_value(
                            "custom"
                        )
                        await expect(page.locator("#naming-prompt")).to_be_disabled()
                        await expect(page.locator("#folder-prompt")).to_be_enabled()
                        await page.locator("#naming-mode").select_option("custom")
                        await page.locator("#folder-mode").select_option("purpose")
                        await expect(page.locator("#folder-prompt")).to_be_disabled()
                        await expect(page.locator("#naming-prompt")).to_be_enabled()
                        await page.reload()
                        await expect(page.locator("#naming-mode")).to_have_value(
                            "custom"
                        )
                        await expect(page.locator("#folder-mode")).to_have_value(
                            "purpose"
                        )
                        await page.locator("#folder-mode").select_option("custom")
                        await expect(page.locator("#naming-prompt")).to_have_value(
                            naming_rule
                        )
                        await expect(page.locator("#folder-prompt")).to_have_value(
                            folder_rule
                        )
                        for width, height in [(1440, 900), (390, 844)]:
                            await page.set_viewport_size(
                                {"width": width, "height": height}
                            )
                            await page.locator(
                                "#rule-editor"
                            ).scroll_into_view_if_needed()
                            assert await page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            )
                            if os.environ.get("BOOKMARK_QA_SCREENSHOTS"):
                                image = (
                                    Path(os.environ["BOOKMARK_QA_SCREENSHOTS"])
                                    / f"custom-rules-{lang}-{width}.png"
                                )
                                image.parent.mkdir(parents=True, exist_ok=True)
                                await page.screenshot(path=str(image))
                        await page.locator("#scope-form button").click()
                        await page.wait_for_url("**&job=*")
                        await expect(page.locator(".job")).to_have_attribute(
                            "data-state", "complete", timeout=20000
                        )
                        next_job = await page.locator(".job").get_attribute("data-job")
                        state = await (
                            await context.request.get(base + "/api/jobs/" + next_job)
                        ).json()
                        assert state["snapshot"]["base_proposal"] == proposal
                        assert state["snapshot"]["rules"] == {
                            "naming_mode": "custom",
                            "folder_mode": "custom",
                            "naming_prompt": naming_rule,
                            "folder_prompt": folder_rule,
                        }
                        assert len(state["snapshot"]["targets"]) == 1
                        await page.locator('[data-action="proposal"]').click()
                        await page.wait_for_url("**&proposal=*")
                        await page.locator(".edit-name").first.wait_for()
                        next_proposal = await page.locator(
                            "#proposal-section"
                        ).get_attribute("data-proposal")
                        continued = await (
                            await context.request.get(
                                base + "/api/proposals/" + next_proposal
                            )
                        ).json()
                        old_nodes = {n["id"]: n for n in result["tree"]}
                        for n in continued["tree"]:
                            if (
                                n["id"] in old_nodes
                                and n["id"] not in state["snapshot"]["targets"]
                            ):
                                assert n == old_nodes[n["id"]]
                        async with page.expect_download() as continued_download:
                            await page.locator("#export").click()
                        download = await continued_download.value
                        assert url_counts(
                            parse(Path(await download.path()).read_bytes())
                        ) == url_counts(parse(HTML))
                        await page.goto(base + "/?project=" + state["project"])
                        await expect(
                            page.locator("#proposal-section")
                        ).to_have_attribute("data-proposal", next_proposal)
                        await expect(page.locator("#folder-prompt")).to_have_value(
                            folder_rule
                        )
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


async def verify_shutdown():
    from bookmark_organization.db import Store

    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, BOOKMARK_DATA_DIR=directory, PYTHONPATH="src:tests")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            for language, width, height in [("en-US", 1440, 900), ("ja-JP", 390, 844)]:
                with tempfile.TemporaryFile() as log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            "from bookmark_organization.app import serve; "
                            "from helpers import shutdown_smoke_factory; "
                            f"serve(shutdown_smoke_factory(), port={port})",
                        ],
                        env=env,
                        stdout=log,
                        stderr=log,
                    )
                    context = None
                    try:
                        async with httpx.AsyncClient(base_url=base) as client:
                            for _ in range(100):
                                try:
                                    if (await client.get("/health")).status_code == 200:
                                        break
                                except httpx.HTTPError:
                                    pass
                                await asyncio.sleep(0.1)
                            else:
                                raise AssertionError(
                                    "shutdown test server startup timeout"
                                )
                        context = await browser.new_context(
                            locale=language, viewport={"width": width, "height": height}
                        )
                        page = await context.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        await page.goto(base)
                        assert page.url == base + "/"
                        assert await page.title() == "Bookmark Organization"
                        await expect(page.locator("#shutdown-server")).to_be_enabled()
                        if language == "en-US":
                            await page.locator("#html-file").set_input_files(
                                {
                                    "name": "shutdown.html",
                                    "mimeType": "text/html",
                                    "buffer": HTML,
                                }
                            )
                            await page.locator("#import-form button").click()
                            await page.wait_for_url("**/?project=*")
                            await page.locator("#scope-form button").click()
                            await page.wait_for_url("**&job=*")
                        else:
                            await expect(page.locator(".job")).to_have_attribute(
                                "data-state", "paused"
                            )
                            await page.locator('[data-action="resume"]:enabled').click()
                        job = await page.locator(".job").get_attribute("data-job")
                        for _ in range(100):
                            state = await (
                                await context.request.get(base + "/api/jobs/" + job)
                            ).json()
                            if any(i["state"] == "analyzing" for i in state["items"]):
                                break
                            await asyncio.sleep(0.05)
                        else:
                            raise AssertionError("synthetic analysis did not start")
                        assert await page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                        if os.environ.get("BOOKMARK_QA_SCREENSHOTS"):
                            image = (
                                Path(os.environ["BOOKMARK_QA_SCREENSHOTS"])
                                / f"shutdown-button-{width}.png"
                            )
                            image.parent.mkdir(parents=True, exist_ok=True)
                            await page.locator(
                                "#shutdown-server"
                            ).scroll_into_view_if_needed()
                            await page.screenshot(path=str(image))
                        await page.locator("#shutdown-server").click()
                        await expect(page.locator("#shutdown-status")).to_be_visible()
                        await expect(page.locator("#shutdown-status h1")).to_have_text(
                            "Server stopped"
                            if language == "en-US"
                            else "サーバーを停止しました"
                        )
                        await expect(page.locator(".workspace")).to_have_count(0)
                        assert await page.locator("vite-error-overlay").count() == 0
                        assert await page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                        if os.environ.get("BOOKMARK_QA_SCREENSHOTS"):
                            await page.screenshot(
                                path=str(
                                    Path(os.environ["BOOKMARK_QA_SCREENSHOTS"])
                                    / f"shutdown-stopped-{width}.png"
                                )
                            )
                        for _ in range(100):
                            if process.poll() is not None:
                                break
                            await asyncio.sleep(0.05)
                        assert process.poll() == 0
                        saved = Store(Path(directory))
                        row = saved.one(
                            "SELECT state,snapshot FROM jobs WHERE id=?", (job,)
                        )
                        assert row["state"] == "paused"
                        assert json.loads(row["snapshot"]) == state["snapshot"]
                        assert all(i["state"] == "pending" for i in saved.items(job))
                        assert any(i["retrieval"] for i in saved.items(job))
                        assert errors == [], errors
                        async with httpx.AsyncClient() as client:
                            try:
                                await client.get(base + "/health")
                            except httpx.ConnectError:
                                pass
                            else:
                                raise AssertionError("server still accepts connections")
                    finally:
                        if context:
                            await context.close()
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=5)
            await browser.close()
    print(
        "Shutdown UI passed: active job paused, port closed, process exited, restart/resume preserved progress in English/Japanese at desktop/mobile widths."
    )


async def run_checks():
    await verify()
    await verify_shutdown()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(run_checks(), timeout=225))
