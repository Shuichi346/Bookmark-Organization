<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_ja.md">日本語</a></th>
      <th style="text-align:center"><a href="README.md">English</a></th>
    </tr>
  </thead>
</table>

# Bookmark Organization

A local web application that organizes Chrome bookmarks with AI models running on your computer. Import an exported bookmark file, choose the folders to process, review suggested Japanese names and semantic groupings, and download Chrome-compatible HTML.

The application preserves the original imported file and keeps duplicate URLs as separate bookmarks. Failed page retrieval never deletes a bookmark. Before export, it checks bookmark identities, counts, URL multiplicities, and unchanged content outside your selection.

## What you can do

- Organize all bookmarks, one folder, or several folders together.
- Analyze pages independently and group related bookmarks using embeddings.
- Compare original and proposed names and locations, search or filter results, and save edits as new proposal versions.
- Pause, resume, and manually retry failed items, with progress saved across server restarts.
- Choose generation and embedding models independently through LM Studio or Ollama.
- Switch between English and Japanese interfaces. Generated names remain Japanese.

Inference stays local. Retrieving bookmark content still accesses the bookmarked websites. The application does not edit Chrome profiles directly or download models automatically.

## Requirements

- Python **3.13** and **uv**.
- Node.js **26.5 or later** and npm **12.0.1 or later** for building frontend assets.
- A local **LM Studio** or **Ollama** API server with a generation model and an embedding model installed.

The project was developed and verified on Apple silicon macOS. The inference runtime handles model execution; the application has no CUDA dependencies. Normal operation uses one Python server plus the inference runtime.

## Get started

From the repository directory:

```sh
uv sync --locked
npm ci
npm run build
uv run --locked bookmark-organization
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Stop the server with **Ctrl+C**. It listens only on loopback and manages one background worker; run only one server process per data directory.

Frontend assets are served locally without a CDN. Rebuild with `npm run build` after changing frontend sources.

### Connect your models

Start the local API server in your inference runtime, then open **Settings** in the application.

| Runtime | Typical base URL |
| --- | --- |
| LM Studio | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |

For content analysis and embeddings separately, choose the runtime and endpoint, click **Discover models / test connection**, select an installed model, and **Save**. Use the model ID returned by discovery, which may differ from its filename. Model installation and loading are handled in the runtime.

The initial selections are:

| Role | Default API model ID | GGUF used in the recorded LM Studio verification |
| --- | --- | --- |
| Content analysis | `qwen3.5-9b-uncensored-hauhaucs-aggressive` | `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` from HauhauCS |
| Embeddings | `text-embedding-embeddinggemma-2` | `embeddinggemma-2-Q8_0.gguf` from unsloth |

You can select other models that support the required structured analysis or embedding role. Ollama names may differ from these defaults. Model endpoints must be loopback, cloud-backed entries are excluded, and there is no cloud AI fallback. See the [LM Studio API documentation](https://lmstudio.ai/docs/developer/openai-compat) and [Ollama compatibility documentation](https://docs.ollama.com/api/openai-compatibility).

Inference defaults to **Use web app settings**, with **thinking off**. This mode lets you control thinking, temperature, and sampling; unchecked sampling controls send neutral disabling values. **Use runtime settings** leaves thinking, temperature, and sampling overrides to the runtime's API defaults. Neither mode changes saved runtime preferences. New jobs snapshot application settings; existing jobs retain their selections, while runtime-owned defaults can change separately.

**Model response wait** defaults to **0 = unlimited**. Set a positive number of seconds to limit waiting. Pause waits for an in-flight request to return; if an unlimited request stalls, stop and restart the server, then resume the paused job. Advanced settings also expose retrieval limits, context and output budgets, and the clustering threshold.

### Use the application

1. Export your Chrome bookmarks as UTF-8 HTML and import the file.
2. Select all bookmarks, one folder, or several folders. Descendants are included, and overlapping selections are deduplicated. Multiple folders form one processing region; choose a selected folder that is not inside another selected folder as the destination. All-bookmark mode creates a root folder named `整理済み`.
3. Start analysis and monitor progress. Closing the browser tab does not stop processing. **Pause** stops the next stage from starting, and **Resume** continues from saved progress. Interrupted jobs remain paused after a server restart until you resume them.
4. Review retrieval and analysis failures. Use **Retry failed** after fixing the cause. Retrieval failures retain original names in folders such as `404` or `アクセス制限`. Including analysis failures requires explicitly allowing `要確認` (Needs review).
5. Create a proposal, compare names and locations, edit names or allowed destination folders, and save. Each save creates a new version while the original import remains unchanged.
6. Export after integrity validation passes. You can also download the original imported file. Review exports in a separate Chrome profile: Chrome imports add bookmarks to the existing collection.

Start with a small file and check the suggestions before importing the result into Chrome. Category quality depends on page content and the selected model; isolated outliers are placed in `要確認`. Selections exceeding the estimated 128 MiB clustering distance-memory budget must be processed in smaller folder groups.

### Optional page rendering

For JavaScript-rendered pages, install Chromium and enable rendering in **Settings**:

```sh
uv run --locked playwright install chromium
```

Retrieval blocks private and reserved network destinations and validates redirects. Request starts are spaced at least 0.5 seconds apart across the worker, including rendered subresources and manual retries. Failed retrieval is not automatically retried, and `robots.txt` is not checked. Rendering uses the same restrictions and cannot bypass logins or CAPTCHA. Unsupported URL schemes remain in the bookmark collection without retrieval.

## Storage and language

The default `data/` directory stores the SQLite database, original imports, processing results, proposal versions, and `settings.json`. Stop the server before backing up the directory. It is ignored by Git; exclude any custom data directory as well, and keep private content, credentials, and model binaries out of tracked files.

| Environment variable | Default |
| --- | --- |
| `BOOKMARK_DATA_DIR` | `data/` |
| `BOOKMARK_PORT` | `8765` |

For example:

```sh
BOOKMARK_DATA_DIR=./my-bookmark-data BOOKMARK_PORT=8766 uv run --locked bookmark-organization
```

Interface language defaults to **Automatic**: the highest-priority usable browser preference selects Japanese for `ja` tags and English for other languages. Missing or unusable preferences fall back to Japanese. Manual **English / 日本語** choices persist in a browser cookie. Switching languages preserves scope selection and saved work, and does not translate original data or previously generated names.

## Development

The application uses FastAPI, Jinja2, HTMX, TypeScript, and SQLite. Python code is in [`src/bookmark_organization/`](src/bookmark_organization/), frontend sources in [`frontend/`](frontend/), and checks in [`tests/`](tests/). Generated assets in `src/bookmark_organization/static/` are ignored by Git.

Run the relevant checks from the repository directory:

```sh
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked ty check src
uv run --locked pytest -q
npm run lint
npm run typecheck
npm run build
uv run --locked python tests/smoke_app.py
```

Unit tests use synthetic HTML, temporary databases, and fake transports. The browser smoke test requires built assets and Playwright Chromium; it runs a real application server with fake inference and checks the workflow in both languages at desktop and mobile widths.

The separate actual-model acceptance test is:

```sh
uv run --locked python tests/smoke_local_models.py --settings data/settings.json
```

It specifically requires LM Studio, its `lms` CLI, and the two GGUF models listed above with matching IDs in the settings file. Recorded real-model evidence covers LM Studio; Ollama's adapter is covered by fake-transport unit tests. Synthetic checks do not prove actual-model compatibility.

See the [interface specification](docs/design/README.md) and [implementation plan and verification history](PLANS.md) for design details and recorded evidence.
