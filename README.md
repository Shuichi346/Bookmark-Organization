# Bookmark Organization

A local web application that reads Chrome bookmark HTML, analyzes individual pages with local models, proposes descriptive Japanese names and semantic folders, and exports Chrome-compatible HTML. Original bytes and immutable tree snapshots are retained in SQLite. Duplicate URLs stay separate bookmarks; inaccessible pages are retained in clearly named folders. Exports are blocked if IDs, counts, URL multiplicities or unselected content change unexpectedly.

## Setup

Use Python 3.13, uv, Node.js >=26.5 and npm >=12.0.1. The inference runtime runs separately on the same computer. Apple silicon execution uses LM Studio or Ollama; there are no CUDA dependencies.

```sh
uv sync --locked
npm ci
npm run build
uv run --locked bookmark-organization
```

Open http://127.0.0.1:8765. The server binds only to loopback. Stop with Ctrl+C. One server process manages the database and single worker; do not run multiple workers against the same data directory.

Optional JavaScript-rendered page retrieval requires Chromium:

```sh
uv run --locked playwright install chromium
```

Generated frontend assets are local and ignored by Git. Rebuild after changing frontend sources. No CDN is needed during operation. Configure portable `BOOKMARK_DATA_DIR` (default `data/`) and `BOOKMARK_PORT` (default `8765`) environment variables if needed. Runtime databases, settings and original files belong in the ignored data directory. Back up that directory to preserve work.

## Local models

Start the LM Studio local API server (default http://localhost:1234/v1), or Ollama (http://localhost:11434/v1). In **Settings**, independently choose a runtime, endpoint and model for content analysis and embeddings. **Discover models / test connection** lists installed local models; select one and **Save**. No model is hard-coded as the only permissible choice. The defaults are:

- Content: `qwen3.5-9b-uncensored-hauhaucs-aggressive`, mapped initially to HauhauCS's `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf`.
- Embeddings: `text-embedding-embeddinggemma-2`, mapped initially to unsloth's `embeddinggemma-2-Q8_0.gguf`.

Use the API identifier actually returned by your runtime, not a filename. Changing settings affects new jobs; existing jobs retain their endpoint/model/limit snapshot. Ollama names may differ. Import GGUFs into Ollama separately and discover the resulting local IDs. Cloud-backed Ollama entries are excluded; model endpoints must be loopback. There is no cloud AI fallback and no automatic model download.

[LM Studio compatibility](https://lmstudio.ai/docs/developer/openai-compat) and [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility) document the local API endpoints. Arbitrary selected models must support their selected role; structured-output errors and invalid vectors remain visible and retryable. Embedding inputs use `task: clustering | query: ` as documented by the [default model card](https://huggingface.co/unsloth/embeddinggemma-2-GGUF).

**Inference settings** defaults to **Use web app settings**, with **thinking off**. Select **Use runtime settings** to use the model defaults applied by that runtime's API, omitting temperature, thinking and sampling overrides. Settings confined to a separate LM Studio chat may not apply to API requests; configure the model's API inference defaults in the runtime. App mode sends the chosen thinking switch, temperature, Top K, Top P, Min P, repetition penalty and presence penalty. Unchecking a sampling control explicitly disables it with a neutral value instead of inheriting the runtime's enabled filter. These per-request settings do not change saved runtime preferences. Model/runtime support for thinking can vary; unsupported settings remain visible errors.

LM Studio uses its OpenAI-compatible chat endpoint (thinking off maps to `reasoning_effort: "none"`, on to `"high"`). Ollama uses native `/api/chat` with `think` and `options` so all listed samplers are supported; embeddings keep the OpenAI-compatible endpoint. Each chat call still contains only that URL's two fresh messages, no tools and no history. New jobs snapshot the app's selected settings; runtime-owned defaults can change outside the app and are not snapshotted.

**Model response wait** defaults to **0 = unlimited**. Set a positive number of seconds to limit response waiting. API connection/pool limits remain 10 seconds and write limits 30 seconds; bookmark retrieval has separate limits. Pause prevents starting another stage but waits for an in-flight model request to return; stop the server to interrupt an indefinitely stalled request, then resume its paused job after restart. The output budget defaults to 8192 tokens and includes thinking; increase it in Advanced settings for models that think extensively. A truncated answer is an analysis failure, not a complete result.

## Workflow

1. Export Chrome bookmarks as UTF-8 HTML and import the file.
2. Select all bookmarks, one folder, or several folders. Descendants are included and overlapping selections are deduplicated. Multiple folders form one region; choose one normalized selected folder as destination. All-bookmark mode creates a separate root folder named 整理済み.
3. Analyze the selected scope. Every page gets fresh independent messages. Pause prevents the next stage from starting; an in-flight bounded request may finish. Closing the tab does not stop the worker. After server restart, interrupted jobs are paused until **Resume**.
4. Review progress and retrieval/analysis failures. Retry failures when their cause is resolved. Failed retrieval never deletes a bookmark. Failed analysis can enter a proposal only after explicitly allowing **要確認 (Needs review)**.
5. Create a proposal, search/filter/page through comparisons, edit names or allowed destination folders and save. Each save creates a version; originals remain immutable.
6. Export HTML after the preservation gate passes. Keep the original download. Chrome imports add bookmarks: use a separate Chrome profile when reviewing an export.

The HTTP fetcher holds private/reserved destinations, pins connections to validated public IPs and checks redirects. Optional rendering runs in isolated contexts and routes subresources through the same restrictions. It cannot bypass logins or CAPTCHA. Unsupported schemes are preserved without retrieval.

Advanced settings expose retrieval limits, context/output budgets and cosine clustering threshold. Large selections exceeding the estimated 128 MiB distance budget are rejected with a folder-processing recommendation. Names and cluster suggestions depend on page content and the chosen model; isolated outliers remain in 要確認.

## Interface language

The initial mode is **Automatic**. The highest-priority usable browser language selects Japanese for `ja` tags and English for other languages; unavailable preferences fall back to Japanese. Manual **English / 日本語** choices persist in a browser cookie. Language changes preserve scope selection and saved processing, and do not translate original bookmark data or previously generated names.

Catalogs are `src/bookmark_organization/locales/en.json` and `ja.json`. Keep keys and interpolation parameters in sync; errors have stable API codes and localized presentation. Add locales by extending these catalogs and the supported-locale list.

## Verification

```sh
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked ty check src
npm run lint
npm run typecheck
npm run build
uv run --locked pytest -q tests/test_bookmarks.py tests/test_fetching.py tests/test_llm.py tests/test_jobs.py tests/test_organizing.py tests/test_i18n.py
uv run --locked python tests/smoke_app.py
uv run --locked python tests/smoke_local_models.py --settings data/settings.json
```

Focused tests use synthetic HTML, temporary databases and fake transports. The finite browser smoke starts a real server with test-only fake inference and checks the actual workflow, both locales, desktop/mobile layout and focusable controls. Real-model verification calls actual local models and never replaces them with fake output. Its settings file must identify the two plan-default models for that specific acceptance check.

See PLANS.md for acceptance status and docs/design/README.md for screen specification. No actual private bookmarks, fetched user content, credentials or model binaries should be committed. Publication and license selection are separate user decisions.
