<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_ja.md">日本語</a></th>
      <th style="text-align:center"><a href="README.md">English</a></th>
    </tr>
  </thead>
</table>

# Bookmark Organization

Turn a Chrome bookmark export into descriptive names and useful folders with AI. Bookmark Organization runs as a local web app: import HTML, select what to organize, review the proposed changes, and export HTML for Chrome.

Use local models through **LM Studio** or **Ollama**, cloud models through **OpenRouter**, or **Codex with ChatGPT sign-in** for content analysis. Analysis and embedding providers are configured independently.

<img src="githubreadme/bookmark-import.png" alt="Bookmark Organization home screen with HTML import and English/Japanese language selection" width="480">

*Import a browser bookmark file to start a project.*

## What it does

- Organizes all bookmarks, a single folder, or several folders together.
- Reads each page independently to suggest a name and a task-based destination. Embeddings order related bookmarks within their chosen folders.
- Lets you set naming and folder instructions separately, including the language of generated names.
- Shows original and proposed names and locations, with search, status filters, and editable proposals.
- Saves progress and proposal revisions so you can pause, resume, and organize another folder later.
- Offers English and Japanese interfaces, including automatic browser-language selection.

The original HTML remains available for download. Duplicate URLs remain separate bookmarks, and failed retrieval never deletes an item. Every generated export must pass integrity checks for bookmark identities, counts, URL multiplicities, and content outside the selected scope.

## Requirements

- **Python 3.13** and **uv**.
- **Node.js 26.5+** and **npm 12.0.1+** to build the frontend.
- An analysis provider and an embedding provider, chosen from the table below. Local models must already be installed and available in their runtime.
- For Codex analysis, the **Codex CLI** on the server's `PATH`, signed in with **ChatGPT**.

Development and verification have been performed on Apple silicon macOS. Console startup uses Unix file locking; Windows support has not been established. The app does not download models or edit Chrome profiles directly.

## Quick start

From the repository directory, run:

```sh
uv sync --locked
npm ci
npm run build
uv run --locked bookmark-organization
```

Open the URL printed in the terminal, normally [http://127.0.0.1:8765](http://127.0.0.1:8765). With no explicit port, startup tries **8765–8769** in order. If the same data directory already has a running server, the command reports its URL instead of starting another worker.

Open **Settings**, configure both model roles, and save before starting an analysis. Frontend assets are served locally; rebuild with `npm run build` after changing frontend sources.

Use **Stop server** in the header or **Ctrl+C** in the terminal to stop the app. Interrupted jobs retain their saved progress and reopen paused. Run the startup command again to continue. Keep one server and one worker per data directory; do not remove `server.lock` while the app is running.

## Configure models

<img src="githubreadme/model-settings.png" alt="Settings with Codex gpt-6-luna for content analysis and LM Studio for embeddings" width="480">

*Example: Codex analyzes pages while a local LM Studio model supplies embeddings.*

| Provider | Content analysis | Embeddings | Connection |
| --- | --- | --- | --- |
| LM Studio | Yes | Yes | Local server, typically `http://localhost:1234/v1` |
| Ollama | Yes | Yes | Local server, typically `http://localhost:11434/v1` |
| OpenRouter | Yes | Yes | Fixed `https://openrouter.ai/api/v1`; API key required |
| Codex (ChatGPT plan) | Yes | No | Codex CLI with ChatGPT sign-in |

For LM Studio, Ollama, or OpenRouter:

1. Choose the provider for each role. Start the API server for a local runtime.
2. For OpenRouter, enter your API key in Settings before discovery or saving.
3. Click **Discover models / test connection**, then choose a suggestion or type the exact model ID.
4. **Save** the settings. Discovery refreshes suggestions without replacing a typed ID; it does not run inference.

The initial LM Studio IDs are `qwen3.5-9b-uncensored-hauhaucs-aggressive` for analysis and `text-embedding-embeddinggemma-2` for embeddings. Use the IDs exposed by your runtime, which can differ from filenames and between providers. Model installation and loading happen in the runtime.

Local endpoints must use loopback addresses. LM Studio and Ollama cloud entries are excluded, and local failures never switch to a cloud provider automatically.

### Codex with a ChatGPT plan

Run `codex login` on the machine hosting the app and use ChatGPT sign-in. Select **Codex (ChatGPT plan)** for content analysis and save. Configure embeddings separately through LM Studio, Ollama, or OpenRouter.

<img src="githubreadme/analysis-providers.png" alt="Content-analysis provider menu showing LM Studio, Ollama, OpenRouter, and Codex (ChatGPT plan)" width="480">

Codex uses the fixed model **`gpt-6-luna`** with **medium reasoning**. API-key sign-in is rejected. Each page gets a fresh ephemeral CLI session with isolated analysis instructions and tools disabled; the app validates its JSON response. The app's sampling controls and output-token setting do not apply to Codex, but the model-response wait does.

CLI discovery checks login and model catalog availability. Successful analysis is needed to establish actual model access. Recorded verification includes Codex CLI **0.162.1** with two independent `gpt-6-luna`/medium analyses; it does not establish compatibility with every CLI version.

### Inference controls

**Use web app settings** is the default, with thinking off. It applies the supported thinking, temperature, and sampling controls; unchecked supported samplers send neutral disabling values. **Use runtime settings** leaves these overrides to the runtime's API defaults. Neither option changes saved runtime preferences.

**Model response wait** defaults to **0 = unlimited**. Set a positive number of seconds to limit waiting. Pause waits for an active request to return; Cancel interrupts the app's request wait and makes the job terminal. External providers may continue work they have already accepted.

New jobs save their model settings and naming/folder rules. Changing Settings does not replace an existing job's saved provider and model choices.

## Organize and export

1. **Import.** Export your Chrome bookmarks as UTF-8 HTML and upload the file. Every upload creates a new project, even for identical files; earlier projects and results remain saved separately.
2. **Select.** Choose all bookmarks or one or more folders. Descendants are included, and overlapping selections do not process an item twice. For a folder selection, choose a selected folder outside the other selected folders as the destination. All-bookmark mode creates a root folder named `整理済み`.
3. **Set rules and analyze.** Under **Rules for this analysis**, choose Preset or Custom instructions independently for names and folders. Blank custom fields use the corresponding preset. Closing the browser tab does not stop processing.
4. **Review failures.** Retrieval failures keep the original names in folders such as `404` or `アクセス制限`. Fix the cause and use **Retry failed** when appropriate. Including analysis failures in a proposal requires explicitly allowing `要確認` (Needs review).
5. **Review and save a proposal.** Compare names and locations, make edits, and save. Each save creates a proposal revision while preserving the original import.
6. **Continue if needed.** Use **Organize another folder** to work from the latest saved result with new instructions. Unselected bookmarks retain their saved names and locations. Once a proposal is saved, reprocess its bookmarks through a new analysis rather than retrying that published job.
7. **Export.** After integrity validation passes, download **All bookmarks** or **Changed blocks only**, or download the unchanged original file.

**Changed blocks only** includes bookmarks targeted across all saved organization rounds, including retrieval and analysis failures, together with their current ancestor folders. It excludes unprocessed siblings and unrelated empty folders. Both export ranges require full-proposal integrity validation.

Start with a small selection and review the output before importing it into Chrome. Chrome imports add bookmarks to the existing collection; a separate profile is useful for reviewing an export. Large selections that exceed the app's estimated 128 MiB clustering distance-memory budget must be split into smaller folder groups.

**Pause / Resume** preserves a job for later continuation. **Cancel** ends a running or paused job while retaining imports, settings snapshots, and saved results. A cancelled job cannot resume, retry, or create a proposal; start a new analysis instead.

### Default naming and folder rules

The preset generates Japanese names in the form **`specific purpose｜proper name`**, for example:

| Page | Example name |
| --- | --- |
| Translation service | `文章を翻訳｜DeepL` |
| GitHub CLI tool | `動画をダウンロード｜yt-dlp［CLI］` |
| Specific documentation page | `正規表現の書き方を確認｜Python re` |

Folders reflect the task you would open the bookmark for, bringing repositories, official sites, and articles for the same task together. There are at most **two generated folder levels below the destination**. In the preset, a useful subtype gets its own folder only when it has at least three bookmarks and distinguishes it from other purposes in its parent. Uncertain purposes go to `あとで整理` for later review.

Custom instructions can replace either dimension: for example, request English names while retaining preset folders, or group into `JS libraries`, `Python`, and `Utilities`. Explicitly requested custom subfolders are retained even for small groups, within the two-level limit. Interface language does not change generation rules or translate saved names.

## Data and privacy

The app serves its interface on loopback and saves its working data locally. The default **`data/`** directory contains SQLite storage, original imports, fetched content and results, proposal revisions, settings, and any saved OpenRouter credentials. Stop the server before backing up this directory.

- **LM Studio / Ollama:** inference stays local. Retrieving page content still contacts the bookmarked websites.
- **OpenRouter:** selected analysis inputs include the URL, original name/folder, and bounded page content; cloud embeddings send the title and analysis text. Usage charges and data handling depend on the selected providers.
- **Codex:** selected analysis inputs go to OpenAI and consume your ChatGPT/Codex plan allowance.

OpenRouter keys entered in Settings are stored separately in `credentials.json` with owner-only permissions (`0600`). They are excluded from settings snapshots, API responses, and rendered pages, and are never forwarded to local runtimes. A blank key field retains the saved key. `OPENROUTER_API_KEY` is a fallback when no key is saved.

The default data directory is ignored by Git. Exclude custom data directories too, and keep original bookmarks, retrieved private content, credentials, and model binaries out of tracked files.

### Runtime configuration

| Environment variable | Default / behavior |
| --- | --- |
| `BOOKMARK_DATA_DIR` | `data/`, relative to the working directory |
| `BOOKMARK_PORT` | Unset: first available port in `8765–8769` |
| `OPENROUTER_API_KEY` | Optional server-side fallback key |

```sh
BOOKMARK_DATA_DIR=./my-bookmark-data BOOKMARK_PORT=8766 uv run --locked bookmark-organization
```

An explicit port uses only that port and fails if it is occupied. `BOOKMARK_PORT=0` lets the OS choose a port; open the printed URL.

### Page retrieval and optional rendering

Retrieval blocks private and reserved network destinations and checks every redirect. Request starts are spaced at least **0.5 seconds** apart across the worker, including redirects, rendered subresources, and manual retries. Failures are not automatically retried, and `robots.txt` is not checked. Unsupported URL schemes remain in the collection without retrieval.

For pages that need JavaScript rendering, install Chromium and enable rendering in Settings:

```sh
uv run --locked playwright install chromium
```

Rendering uses the same network restrictions and cannot bypass login requirements or CAPTCHA.

## Development and verification

The app uses **FastAPI, Jinja2, HTMX, TypeScript, and SQLite**.

| Path | Contents |
| --- | --- |
| [`src/bookmark_organization/`](src/bookmark_organization/) | Application, model adapters, persistence, and templates |
| [`frontend/`](frontend/) | Frontend sources; build with `npm run build` |
| [`tests/`](tests/) | Unit, browser workflow, and actual-model checks |
| [`docs/design/README.md`](docs/design/README.md) | Interface specification |
| [`NOTES.md`](NOTES.md) | Implementation rationale and verification limits |
| [`PLANS.md`](PLANS.md) | Design, acceptance criteria, and historical progress |

Generated files in `src/bookmark_organization/static/` are ignored by Git. Run checks from the repository directory:

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

The browser smoke test needs built assets and Playwright Chromium. It uses a real app server with fake inference and checks English/Japanese workflows at desktop and mobile widths. Synthetic tests do not prove real-model compatibility.

Actual-model checks use two public-text fixtures without fetching live pages or changing saved app settings:

```sh
# Fixed Codex analysis only; no embeddings or export.
uv run --locked python tests/smoke_local_models.py --settings data/settings.json --codex

# Custom rules with the selected providers, embeddings, and integrity-checked export.
uv run --locked python tests/smoke_local_models.py --settings data/settings.json --custom
```

Add `--analysis-only` to the custom check when testing generation alone. The default harness, without either mode, requires LM Studio, its `lms` CLI, and the recorded GGUF models: `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` and `embeddinggemma-2-Q8_0.gguf`, with matching API IDs in Settings. Consult [NOTES.md](NOTES.md) for the scope and limits of recorded actual-model evidence.
