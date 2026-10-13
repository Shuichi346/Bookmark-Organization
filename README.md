<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_ja.md">日本語</a></th>
      <th style="text-align:center"><a href="README.md">English</a></th>
    </tr>
  </thead>
</table>

# Bookmark Organization

A local web application that organizes Chrome bookmarks with local AI models, OpenRouter, or Codex using your ChatGPT plan. Import an exported bookmark file, choose the folders to process, review suggested Japanese names and purpose-based folders, and download Chrome-compatible HTML.

The application preserves the original imported file and keeps duplicate URLs as separate bookmarks. Failed page retrieval never deletes a bookmark. Before export, it checks bookmark identities, counts, URL multiplicities, and unchanged content outside your selection.

## What you can do

- Organize all bookmarks, one folder, or several folders together.
- Analyze pages independently, name them by purpose, and group them by the task you would open them for. Embeddings order related items within those folders.
- Compare original and proposed names and locations, search or filter results, and save edits as new proposal versions.
- Pause, resume, cancel, and manually retry failed items, with progress saved across server restarts.
- Choose generation and embedding models independently through LM Studio, Ollama or OpenRouter, or use Codex for generation.
- Switch between English and Japanese interfaces. Generated names remain Japanese.

LM Studio and Ollama inference stays local. Choosing OpenRouter sends inputs to OpenRouter and its model providers and may incur usage charges. Choosing Codex sends analysis inputs to OpenAI and consumes your ChatGPT/Codex plan allowance. Retrieving bookmark content accesses the bookmarked websites. The application does not edit Chrome profiles directly or download models automatically.

## Requirements

- Python **3.13** and **uv**.
- Node.js **26.5 or later** and npm **12.0.1 or later** for building frontend assets.
- A local **LM Studio** or **Ollama** API server with the selected models installed, or an **OpenRouter** account and API key. The two roles can use different providers.
- For Codex content analysis: **Codex CLI**, available as `codex` on the server's PATH, signed in with **ChatGPT**. The integration was verified with CLI **0.160.1**; embeddings still require one of the other providers.

The project was developed and verified on Apple silicon macOS. The inference runtime handles model execution; the application has no CUDA dependencies. Normal operation uses one Python server, plus any selected local inference runtime.

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

Open **Settings** in the application. Start the local API server when using LM Studio or Ollama.

| Provider | Base URL |
| --- | --- |
| LM Studio | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` (fixed) |
| Codex (analysis only) | No endpoint; uses ChatGPT CLI sign-in |

For content analysis and embeddings separately, choose the provider and endpoint, click **Discover models / test connection**, choose a suggestion or type the exact model ID, and **Save**. Typing filters the suggestions; discovery refreshes candidates without overwriting your input. Use the model ID returned by discovery, which may differ from its filename. Model installation and loading are handled in the runtime.

The initial selections are:

| Role | Default API model ID | GGUF used in the recorded LM Studio verification |
| --- | --- | --- |
| Content analysis | `qwen3.5-9b-uncensored-hauhaucs-aggressive` | `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` from HauhauCS |
| Embeddings | `text-embedding-embeddinggemma-2` | `embeddinggemma-2-Q8_0.gguf` from unsloth |

You can select other models that support the required structured analysis or embedding role. Ollama names may differ from these defaults. LM Studio and Ollama endpoints must be loopback, and their cloud-backed entries are excluded. OpenRouter is an explicit selection with its official HTTPS endpoint; local failures never switch to cloud AI automatically. See the [LM Studio API documentation](https://lmstudio.ai/docs/developer/openai-compat) and [Ollama compatibility documentation](https://docs.ollama.com/api/openai-compatibility).

For OpenRouter, enter the API key in the password field before discovery or saving, then choose a suggestion or enter the exact model ID and save. Discovery checks the key and lists text models supporting structured outputs for analysis, or text embedding models for embeddings; it does not run inference. You can combine OpenRouter analysis with local embeddings, or use OpenRouter for both. Analysis sends the selected bookmark URL, original name and folder path, title, description and bounded page text; cloud embeddings send the page title and analysis text. Model/provider charges and data handling depend on your OpenRouter account and selection. See the [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) and [embeddings documentation](https://openrouter.ai/docs/api_reference/embeddings).

Keys entered in Settings are stored in `credentials.json` inside the data directory with owner-only permissions (0600). They are excluded from `settings.json`, job snapshots, API responses and rendered pages. A blank field retains the existing key; a replacement applies to new and resumed processing batches. `OPENROUTER_API_KEY` is a server-side fallback when no key has been saved. Never commit either source of credentials. Provider/model choices remain immutable for existing jobs. Only model-supported inference controls are sent to OpenRouter; its repetition penalty limit is 2, and some models require reasoning even when thinking is off. Authentication, credit and rate-limit errors are shown separately and require manual retry.

Inference defaults to **Use web app settings**, with **thinking off**. This mode lets you control thinking, temperature, and sampling; unchecked sampling controls send neutral disabling values. **Use runtime settings** leaves thinking, temperature, and sampling overrides to the runtime's API defaults. Neither mode changes saved runtime preferences. New jobs snapshot application settings; existing jobs retain their selections, while runtime-owned defaults can change separately.

For **Codex**, run `codex login` on the machine running the app and choose ChatGPT sign-in, then select **Codex (ChatGPT plan)** for content analysis and save. The model is fixed to `gpt-6-luna` with `model_reasoning_effort="low"`. API-key sign-in is rejected, and API-key environment variables are not passed to Codex. Discovery checks CLI login and the model catalog without inference; catalog presence does not establish actual model access. Analysis sends the selected URL, original name/folder path and bounded retrieved content to OpenAI. Each page uses a fresh ephemeral CLI session with isolated instructions and tools disabled. The app validates the returned JSON before saving it. Codex does not provide embeddings; keep that role independently configured. Sampling and the app's output-token limit do not apply to Codex; the model-response wait still applies. Cancelling or exceeding that wait terminates the local CLI process group. Plan-limit failures require manual retry. See the [Codex authentication](https://learn.chatgpt.com/docs/auth) and [non-interactive CLI](https://learn.chatgpt.com/docs/non-interactive-mode) documentation.

**Model response wait** defaults to **0 = unlimited**. Set a positive number of seconds to limit waiting. Pause waits for an in-flight request to return. Cancel interrupts the application's request wait and ends the job, even with an unlimited wait. Advanced settings also expose retrieval limits, context and output budgets, and the clustering threshold.

### Use the application

1. Export your Chrome bookmarks as UTF-8 HTML and import the file.
2. Select all bookmarks, one folder, or several folders. Descendants are included, and overlapping selections are deduplicated. Multiple folders form one processing region; choose a selected folder that is not inside another selected folder as the destination. All-bookmark mode creates a root folder named `整理済み`.
3. Start analysis and monitor progress. Closing the browser tab does not stop processing. **Pause** stops the next stage from starting, and **Resume** continues from saved progress. Interrupted jobs remain paused after a server restart until you resume them.
   **Cancel** ends a running or paused job and releases the project for a new analysis. Original bookmarks, job settings and saved results remain intact. Cancelled jobs cannot be resumed, retried or used to create a proposal. Cancelling disconnects application requests; an external model provider may continue work already accepted.
4. Review retrieval and analysis failures. Use **Retry failed** after fixing the cause. Retrieval failures retain original names in folders such as `404` or `アクセス制限`. Including analysis failures requires explicitly allowing `要確認` (Needs review).
5. Create a proposal, compare names and locations, edit names or allowed destination folders, and save. Each save creates a new version while the original import remains unchanged.
6. Export after integrity validation passes. You can also download the original imported file. Review exports in a separate Chrome profile: Chrome imports add bookmarks to the existing collection.

Start with a small file and check the suggestions before importing the result into Chrome. Category quality depends on page content and the selected model. Confidently classified single bookmarks retain their purpose folder; uncertain purposes use `あとで整理`, while permitted analysis failures use `要確認`. Selections exceeding the estimated 128 MiB clustering distance-memory budget must be processed in smaller folder groups.

### Naming and folder rules

New analyses use Japanese names in the form `specific purpose｜site, tool or resource name`. Service names follow the task, such as `文章を翻訳｜DeepL`. GitHub entries distinguish apps, CLI tools, libraries, samples and curated lists, adding a type or language only when useful: `動画をダウンロード｜yt-dlp［CLI］`. Individual documents and articles describe their specific content, for example `正規表現の書き方を確認｜Python re`, rather than naming the whole site.

Folders reflect the task for which you would look for the bookmark, bringing official sites, repositories and articles together. Suggested areas include AI, images and video, development, files and documents, research, macOS and everyday life; other specific purposes are allowed. Original names and folder paths help infer intent when several uses fit. The selected destination (or the `整理済み` wrapper) contains at most two newly generated folder levels. A subtype gets a folder only when it has at least three bookmarks and its parent also contains other purposes; smaller or redundant subtypes stay in the parent. No unused categories are created. Review the temporary `あとで整理` folder regularly. Names should not repeat the entire folder hierarchy.

The page includes an expandable guide. Existing jobs, including resumed and retried jobs, retain their snapshotted naming and grouping version; create a new analysis to apply these rules. Manual proposal edits remain available.

### Optional page rendering

For JavaScript-rendered pages, install Chromium and enable rendering in **Settings**:

```sh
uv run --locked playwright install chromium
```

Retrieval blocks private and reserved network destinations and validates redirects. Request starts are spaced at least 0.5 seconds apart across the worker, including rendered subresources and manual retries. Failed retrieval is not automatically retried, and `robots.txt` is not checked. Rendering uses the same restrictions and cannot bypass logins or CAPTCHA. Unsupported URL schemes remain in the bookmark collection without retrieval.

## Storage and language

The default `data/` directory stores the SQLite database, original imports, processing results, proposal versions, `settings.json`, and any saved `credentials.json`. Stop the server before backing up the directory. It is ignored by Git; exclude any custom data directory as well, and keep private content, credentials, and model binaries out of tracked files.

| Environment variable | Default |
| --- | --- |
| `BOOKMARK_DATA_DIR` | `data/` |
| `BOOKMARK_PORT` | `8765` |
| `OPENROUTER_API_KEY` | Unset; optional fallback for OpenRouter |

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

For a bounded actual Codex analysis check on two public-page text fixtures, using the fixed model and ChatGPT login:

```sh
uv run --locked python tests/smoke_local_models.py --settings data/settings.json --codex
```

This flag verifies Codex analysis only; it does not call embeddings, fetch live websites, export bookmarks, or change saved application settings.

Without `--codex`, the harness requires LM Studio, its `lms` CLI, and the two GGUF models listed above with matching IDs in the settings file. Recorded real-model evidence covers LM Studio and Codex analysis. Ollama's adapter is covered by fake-transport unit tests. OpenRouter request shapes, authentication failures, role discovery, mixed providers and credential isolation are covered with mock transports. Synthetic checks do not prove actual-model compatibility or authenticated OpenRouter inference.

See the [interface specification](docs/design/README.md) and [implementation plan and verification history](PLANS.md) for design details and recorded evidence.
