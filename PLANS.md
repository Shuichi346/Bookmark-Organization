# Bookmark Organization — Requirements and Implementation Plan

## Progress Status

This section is the sole authoritative progress checklist. The current request covers reading the referenced conversation, organizing requirements, and saving an implementation plan. Do not begin implementation yet. The implementation items below specify the work to perform when implementation is requested later.

- [x] P1 Read the referenced conversation and distinguish requirements from technical suggestions
- [x] P2 Inspect the repository, local tools, and relevant official documentation
- [x] P3 Save the implementation plan and reconcile requirements, dependencies, and acceptance conditions
- [ ] I1 Define the screen designs and design tokens
- [ ] I2 Prepare the Python/Node.js environments and startup/build entry points
- [ ] I3 Implement HTML import/export, original-file preservation, and SQLite persistence
- [ ] I4 Implement page retrieval and retrieval-failure classification
- [ ] I5 Implement independent local LLM analysis and embeddings
- [ ] I6 Implement persistent jobs with pause and resume
- [ ] I7 Implement semantic organization within the selected scope, proposals, and loss detection
- [ ] I8 Complete the English/Japanese interface, automatic language selection, and entire workflow
- [ ] V1 Run static validation and build the frontend
- [ ] V2 Run targeted tests for preservation, retrieval, LLM isolation, and resumption
- [ ] V3 Run automated smoke checks against the actual server and interface
- [ ] V4 Verify analysis, embeddings, and HTML export with the specified real models

Current: Planning complete — The current requested scope is complete. I1–I8 and V1–V4 have not started.
Next: Begin I1 when the user requests implementation.

During execution, save this section after obtaining completion evidence for each implementation item or verification unit. Do not check an item without implementation or verification evidence. Show the full checklist at the start, phase boundaries, and completion; otherwise show only changed lines and Current/Next. Follow the user's preference for shorter reporting when applicable.

## Outcome and Requirements

Import bookmark HTML exported from Chrome, use local AI to understand the actual destination pages, organize bookmarks into descriptive names and folders, and return HTML that Chrome can import. Provide an English/Japanese interface with automatic language selection and run locally on a Mac mini M4 with 24 GB of memory. Prepare the source for the user's planned public GitHub repository.

Source: the ChatGPT conversation titled “ブックマーク整理アプリ案” (conversation ID: `6ac31a87-88c4-83ee-8b5c-e47153ab0801`). All five available turns were reviewed on 2026-10-11. The requirements combine its consolidated description, the user's subsequent clarification about context isolation, and the later model selections. Distinguish the previous assistant's technical suggestions from technology choices explicitly made by the user. In this conversation, the user explicitly confirmed both Ollama and LM Studio, automatic English/Japanese interface selection with a manual override, and an intention to publish the source on GitHub.

| ID | Required behavior and preservation condition | Implementation / evidence |
| --- | --- | --- |
| R1 | Read the original folder tree, names, URLs, and total count, and preserve the original file | I3, V2, V3 |
| R2 | Allow all bookmarks, one folder, or any combination of folders to be selected. Include descendants and prevent duplicate processing from overlapping selections | I7, I8, V2, V3 |
| R3 | Organize using page content, descriptions, purpose, type, and technologies. For GitHub, understand the repository's purpose | I4, I5, V2, V4 |
| R4 | One URL equals one independent LLM request. Never carry conversation history from a previous URL | I5, I6, V2, V4 |
| R5 | Store suggested names, summaries, types, candidate categories, tags, retrieval status, and analysis status in the application | I3, I5, I6, V2 |
| R6 | Classify, move bookmarks, and create folders using content and semantic similarity, without being restricted to existing categories | I5, I7, V2, V4 |
| R7 | Treat multiple selected folders as one organization region. Preserve unselected bookmark names, URLs, and placement, and unselected folder structure | I7, V2, V3 |
| R8 | Never automatically delete bookmarks because of a 404 or inaccessible URL. Retain them in dedicated folders such as 404 | I4, I7, V2, V4 |
| R9 | Before export, verify counts, individual IDs, URL multisets, and the invariance of out-of-scope data. Block export on any mismatch | I3, I7, V2, V3 |
| R10 | Use the two specified GGUF models locally. Support both Ollama and LM Studio, with connection settings and model selection | I5, I8, V2, V4 |
| R11 | Export Chrome-compatible HTML and allow the original data and organization results to be reviewed | I3, I7, I8, V2, V3, V4 |
| R12 | Default interface language mode to Automatic. Display Japanese for a Japanese browser preference and English for other languages. Offer persistent manual English/Japanese overrides | I1, I2, I8, V1, V2, V3 |
| R13 | Prepare reusable source for a public GitHub repository: English setup documentation, separate translation catalogs, portable configuration, and no private bookmark data or credentials in tracked artifacts | I2, I8, V1 |

Use the following models as the initial selections. An API model ID is not necessarily the same as a GGUF filename. Persist the model ID obtained from the API.

- Content understanding, suggested names, categories, and tags: `Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf` from `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive`.
- Semantic comparison and organization assistance: `embeddinggemma-2-Q8_0.gguf` from `unsloth/embeddinggemma-2-GGUF`.

Additional operating qualities adopted for implementation: per-URL state persistence, pause/resume, progress reporting, original-data invariance, visible errors, input and LLM-output validation, keyboard operation, and support for narrow screens. These are design choices adopted from the earlier technical suggestions, not evidence that the user has already verified them on the actual machine.

Outside the current scope: source implementation, dependency installation, model downloads or loading, retrieval or organization of actual bookmarks, and writes to Chrome. Also outside the later product implementation: cloud LLMs, accounts or synchronization services, Chrome extensions, direct Chrome-profile editing, automatic removal of duplicate URLs, and macOS distribution packages. Provide dynamic-page retrieval as a supporting feature, without bypassing login or CAPTCHA.

## Current System Evidence and Selected Stack

At the initial inspection on 2026-10-11, the repository contained only `.git` and `.gitattributes`. There were no existing sources, tests, plans, dependency manifests, or project AGENTS.md files. The working tree had no changes. The applicable instructions are the user instructions and skills supplied in this conversation.

Verified tools: Python 3.13.15, uv 0.12.23, Node.js 26.10.0, and npm 12.2.0. The ruff and ty commands are available. Check their versions and the LLM-runtime versions when implementation starts. Model locations, loading status, and API availability have not been checked.

Build one local web application using Python 3.13 + uv, FastAPI + Jinja2, HTML/CSS + HTMX + small TypeScript modules, and SQLite. Adopt the lightweight stack suggested in the referenced conversation. Use Node.js only to build and validate static assets with Vite; normal operation requires a single Python server. Prefer this Python-centered design over the Build Web Apps default of React. The framework names are implementation choices in this plan, not user-mandated requirements. Ollama and LM Studio, however, are explicitly selected by the user; neither another inference runtime nor a cloud provider replaces them.

Candidate dependencies: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `beautifulsoup4`, `html5lib`, `httpx`, `trafilatura`, `openai`, `pydantic`, `numpy`, `scikit-learn`, and `playwright`. Use `pytest` for tests. Frontend dependencies are `htmx.org`, `vite`, `typescript`, and `oxlint`. Resolve compatible, maintained releases during implementation and record them in `uv.lock` and `package-lock.json`. Do not invent precise version pins before researching them.

Set `.python-version` to 3.13 and `requires-python` to `>=3.13,<3.14`. Use a project-local `.venv` without modifying system Python. Use ES modules in `package.json`, with `engines.node: ">=26.5"`, `engines.npm: ">=12.0.1"`, and `engine-strict=true` in `.npmrc`. Use `uv sync` and `npm install` for initial resolution; subsequently use `uv sync --locked` / `uv run --locked` and `npm ci`. Ignore `.venv/`, `__pycache__/`, `node_modules/`, generated assets, actual user data, `.DS_Store`, and `Thumbs.db`.

Run natively on Apple silicon. Delegate GPU execution to the external local runtime, and do not add CUDA paths to the application. This plan creates a web application, so architecture inspection of an .app bundle is inapplicable. If macOS packaging is later added, extend the plan with arm64-only distribution and inspection of bundled native components.

### Official Documentation Reviewed

- [LM Studio OpenAI-compatible API](https://lmstudio.ai/docs/developer/openai-compat): Use `/v1/models`, `/v1/chat/completions`, and `/v1/embeddings`, specifying the base URL and actual model ID.
- [Ollama OpenAI-compatible API](https://docs.ollama.com/api/openai-compatibility): Use the local `http://localhost:11434/v1/` endpoint. Compatibility is partial; do not assume identical optional parameters across both runtimes. Exclude cloud models from selection.
- [Specified EmbeddingGemma model card](https://huggingface.co/unsloth/embeddinggemma-2-GGUF): Use `task: clustering | query: {content}` consistently for organization inputs and normalize vectors. Verify the GGUF/runtime combination on the actual machine.
- [Specified Qwen model card](https://huggingface.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive): The specified Q6_K distribution was confirmed. File size does not guarantee RAM requirements; verify model and context settings in V4.
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) and [Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/): Manage clients and the worker through lifespan. Persistent-job resumption must not depend solely on temporary tasks executed after a response.
- [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/): Serve Jinja2 templates and local static assets.
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/) and [resource limits](https://www.python-httpx.org/advanced/resource-limits/): Set explicit connection, read, pool, and other limits.
- [uv project layout](https://docs.astral.sh/uv/concepts/projects/layout/): Manage the manifest, lockfile, and project environment together.
- [HTMX documentation](https://htmx.org/docs/): Use HTML partial updates and progress polling. Bundle the library locally without a CDN dependency.
- [Vite backend integration](https://vite.dev/guide/backend-integration.html): Supply asset references to Jinja2 through the build manifest.
- [Browser language preferences](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/languages) and [Accept-Language](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept-Language): Browser preferences are available through language tags and weighted request headers. They can differ from the operating system's language, so do not claim direct OS-language detection.
- [HTML lang attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/lang): Set the document language to the resolved interface locale.

## Architecture and Design

### Data Model and Storage

All paths and identifiers below are proposed new locations. Use `src/bookmark_organization/` for the Python package, `frontend/` for static asset sources, and `tests/` for targeted tests.

Store projects, folders, bookmarks, analyses, embeddings, jobs, job_items, proposal_versions, and proposal_items in SQLite. Folders and bookmarks have UUIDs; bookmarks with identical URLs remain separate records with separate IDs. For each project, preserve the original HTML bytes and SHA-256, original folder IDs, parent relationships, order and attributes, and original bookmark names, URLs, order and attributes as immutable data. Store the final retrieval URL separately without rewriting the original URL.

Use `data/` as the default local user-data directory. Exclude databases and originals from Git. Snapshot target IDs, selected folder IDs, destination, model IDs, prompt version, and retrieval settings when creating a job, so later API-setting changes do not affect a running job. Do not copy credentials into job history or logs.

Parse Netscape Bookmarks HTML using H3/A/DL hierarchy and ordering. Support unclosed tags, but return an import error instead of silently dropping bookmarks that cannot be interpreted. Preserve empty folders, distinct folders with the same name, root-level bookmarks, Unicode, quotation marks, HTML special characters, and duplicate URLs. Invalid URL syntax or non-HTTP links must not cause import rejection; preserve them as items that cannot be retrieved.

Export UTF-8 Chrome-compatible HTML. Escape names, URLs, and attributes. Reparse generated HTML using the same parser and verify that its count, URL multiset, and tree match the intended result. Perform internal ID checks against the proposal immediately before export; do not assume Chrome preserves internal IDs. Provide a separate download of the original file.

### Interface Localization and Public Repository Readiness

The initial language setting is `auto`, with supported manual values `en` and `ja`. In Automatic mode, use the browser's highest-priority usable language preference: a `ja` language tag, including regional variants such as `ja-JP`, selects Japanese; any other language selects English. Use Japanese when no usable preference is available. This preserves the specified Japanese fallback without making Japanese the initial language mode. The setting UI offers Automatic, English, and Japanese, with language names recognizable in their own languages.

For server-rendered pages and HTMX fragments, resolve the locale from a validated manual preference cookie first, otherwise from `Accept-Language`. Honor quality values, ignore entries with quality zero and wildcard-only preferences, and normalize language tags. Treat invalid manual values as Automatic. Persist the preference per browser rather than changing a server-wide language for every user. Use a first-party cookie accessible to server rendering, with appropriate SameSite and path settings; no account is required. Automatic mode follows browser preferences on the next request. Browser `navigator.languages` may provide supporting client information, but do not overwrite an explicit manual choice or produce inconsistent first-page and fragment languages.

Proposed locations: `src/bookmark_organization/i18n.py`, `src/bookmark_organization/locales/en.json`, and `src/bookmark_organization/locales/ja.json`. Use stable message keys and matching interpolation parameters in both catalogs. Keep user-facing text out of service logic and templates except through translation helpers. Cover navigation, buttons, forms, validation errors, job statuses, empty states, dialogs, accessibility labels, and client-side messages. Return stable machine-readable API error codes and status values, and localize presentation separately. Do not display raw exception text as a translated error message. Serve the necessary client messages locally from the same catalogs instead of maintaining a divergent frontend dictionary. Use English as the canonical catalog and fallback for a missing translation key; development checks reject missing keys or mismatched placeholders.

Set `<html lang>` to the resolved locale and keep HTMX fragments consistent with it. Format interface dates and numbers for that locale, retain keyboard access, and support English labels without clipping or breaking narrow-screen layouts. Changing interface language must preserve selection, job progress, and unsaved edits where practical; do not restart jobs. Keep the plan, source comments, and primary README in English.

Interface localization does not translate imported bookmark data or rewrite saved proposals. The existing Japanese default for LLM-generated names and actual generated folder names remains unchanged by this interface-only request. Display generated names as data, even in an English interface. Labels explaining those names are localized. Do not implicitly change job prompts or saved classification results when the interface language changes.

For the planned public repository, document installation, build/start/check commands, both local runtimes, model selection, and language behavior in English. Avoid machine-specific absolute paths in product configuration. Use synthetic test fixtures; exclude real HTML, databases, fetched content, credentials, and model binaries from tracked files. Keep translation additions possible by extending catalogs and the explicit supported-locale list. Publication and license selection remain separate actions; the user's intention to publish does not itself authorize a push or a license choice.

### Selection Scope and Folder Placement

The processing scope is the set of descendant bookmarks under the selected folders. Normalize overlapping parent/child selections to the selected ancestor. All-bookmark processing includes root-level bookmarks. For one selected folder, create organized categories beneath that folder.

For multiple folders, classify all selected bookmarks together and let the user select one of the selected folders as the organization destination. Default to the first selected folder in original HTML order and show the destination before starting. Bookmarks may move from other selected folders into that destination, but no new categories may be created in unselected regions. Do not automatically delete selected folders or folders that become empty. For all-bookmark processing, default to a new root-level region named “整理済み” (Organized). Distinguish name collisions by ID and generate non-conflicting names.

Preserve unselected parent/sibling structures and out-of-scope bookmark names, URLs, parent IDs, attributes, and relative ordering. A shift in displayed positions caused solely by moving selected bookmarks is not a structural change. Do not rename, move, or delete out-of-scope folders during export.

### Page Retrieval

Use HTTPX in `fetching.py`. Initial limits: 45 seconds overall per item, 10 seconds for connection, 20 seconds for reads, a 5 MiB maximum response body, five redirects, and two concurrent retrievals. Run only one LLM request at a time. Allow explicit changes to these settings.

Extract title, meta description, and main text. Only when normal HTML lacks usable text, use the enabled Playwright fallback to extract text after JavaScript rendering. The browser may be reused, but isolate pages/contexts for each URL. Allow an additional overall limit of 30 seconds. Do not use credentials or the user's actual browser profile.

Distinguish HTTP 404, 403/401, timeouts, connection failures, other HTTP errors, content-extraction failures, unsupported schemes, and restricted destinations. Do not classify a 403 as a 404. Without page content, do not perform LLM analysis that implies the content was read. Preserve original names and URLs for failed items and retain them in dedicated folders. Treat LLM/API unavailability separately from page disappearance, leaving items unanalyzed and retryable.

Default bookmark-originated requests to public HTTP(S) addresses. Hold localhost, private, link-local, and reserved addresses without fetching them. Check redirect destinations as well. Prevent DNS re-resolution between validation and connection from reaching internal addresses; apply the same policy to Playwright subresources. Allow explicitly configured loopback model APIs through a separate client. A permission feature for local or intranet bookmarks is outside the required scope.

### Local Models and Organization

Use an OpenAI-compatible client in `llm.py`. Allow separate base URLs and model IDs for generation and embeddings. Default LM Studio to `http://localhost:1234/v1` and Ollama to `http://localhost:11434/v1`. Restrict endpoints to loopback and provide no fallback to external AI services. Confirm in the actual Ollama configuration that cloud-backed models are not used.

Construct fresh system + user messages for every request and include information about only that URL. Never reuse session IDs or previous response IDs, and never send another URL's analysis or conversation history. Keeping the same model loaded in memory is allowed. Delimit web content as untrusted input data, and do not enable tool calls or arbitrary instruction execution.

Validate summary, type, purpose, suggested name, candidate categories, and tags with Pydantic. Default to descriptive Japanese names while retaining product and library proper names. Fit inputs within the configured context budget and set an output limit. Save invalid JSON, truncated responses, and API failures as analysis failures for that URL; do not repair them using history from another URL. Allow at most one automatic response-repair request, restricted to the same URL. Do not use unlimited SDK retries.

Combine title, purpose, summary, and candidate categories for embeddings. Use the specified model's clustering prefix and validate dimensions, finite values, and nonzero norm. Store prompt version, model ID, dimensions, and content hash. Do not mix vectors from different models or dimensions.

Use cosine distance between normalized vectors in `organizing.py`. The initial algorithm is agglomerative clustering with average linkage and distance threshold 0.25. This is an adjustable implementation default, not a universally correct classification threshold. Plan initially for approximately 5000 items and estimate distance-array memory within 128 MiB. If the budget is exceeded, stop with an explanation and suggest folder-based processing; never delete items or silently narrow the scope.

Name clusters by aggregating candidate categories from individual URL analyses. Do not send all URLs into a new LLM conversation to name clusters. Keep weakly matched items in “要確認” (Needs review), and do not merge similar URLs into a single bookmark. The LLM produces suggestions; Python manages placement, names, and preservation checks.

### Jobs, APIs, and Interface

Manage a single worker and shared HTTP clients through FastAPI lifespan. Persist states in SQLite and commit each item's results separately. Use `pending → fetching → analyzing → embedding → complete` as the normal progression, with explicit retrieval failures, analysis failures, and paused states. On restart, return interrupted items to pending and reuse successful stages. Do not automatically resume external access merely because the application starts; wait for the user's resume action. The pause button prevents the next stage from starting, and in-flight operations must finish within finite timeouts.

Prevent competing jobs for the same project. Use database uniqueness and an idempotency token to prevent duplicate job creation. Display total, successful, retrieval-failed, analysis-failed, and remaining counts. Jobs continue within the server when the browser closes; persist pause/resume state in the database.

Proposed primary APIs: `GET /health`, `POST /api/projects/import`, `GET /api/projects/{id}/tree`, `GET/PUT /api/settings`, `POST /api/settings/probe`, `POST /api/projects/{id}/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/pause`, `POST /api/jobs/{id}/resume`, `POST /api/jobs/{id}/retry-failed`, `POST /api/jobs/{id}/proposal`, `GET /api/proposals/{id}`, `PATCH /api/proposals/{id}/items/{bookmark_id}`, `GET /api/proposals/{id}/export`, and `GET /api/projects/{id}/original`. Return HTML partial updates from `/ui/...` routes using the same service layer; do not duplicate integrity logic.

Arrange the interface around HTML import, tree-based scope selection, model connection settings, processing progress, before/after comparison, and export. Provide search, status filters, and pagination for the change list, comparing original/suggested names, original/new locations, and retrieval status. Saving edits to suggested names or placement updates the proposal version and requires revalidation at export. Keep implementation details in advanced settings for APIs, models, and retrieval limits rather than scattering them through the normal workflow.

Enable export only after integrity checks pass. For LLM connection failures, incomplete analysis, or integrity mismatches, show the cause and a resume or correction action. Allow export that preserves failed-analysis items under Needs review only through an explicit user action displaying that state. Never label incomplete analysis as successfully analyzed in full.

Bind the server to 127.0.0.1, restrict allowed Host/Origin values, protect mutation forms against CSRF, and consistently escape HTML and attributes. Do not log credentials embedded in URLs. Never insert raw page content or original HTML into the interface as executable HTML.

## Implementation Sequence

| ID | Outcome and proposed location | Required action | Dependencies | Acceptance evidence |
| --- | --- | --- | --- | --- |
| I1 | Screen specifications, tokens, and state inventory under `docs/design/` | Use Build Web Apps and Image Gen to design primary screens covering scope selection, progress, comparison, settings, errors, and narrow screens. Record English/Japanese copy, the Automatic/English/Japanese selector, colors, typography, spacing, and table/tree/form rules. Avoid invented processing results and decorative statistics | None | Screen specifications map operations for R1–R12, identify required states and components, and accommodate both languages |
| I2 | `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `.npmrc`, `.python-version`, `.gitignore`, `frontend/`, and `src/bookmark_organization/app.py` | Prepare the specified runtimes and lockfiles. Connect the Vite manifest, static serving, and `bookmark-organization` startup command. Define localization catalogs and helpers. Document necessary startup/check commands in English and exclude private runtime data from tracked artifacts | I1 | Imports, builds, and `/health` work in the locked environment; catalog structure and portable configuration support R12/R13; consolidate evidence in V1/V3 |
| I3 | `db.py`, `schemas.py`, and `bookmarks.py` | Implement the schema, original-file storage, parser, and exporter. Save the entire import transactionally; leave no partial project on failure | I2 | V2 covers difficult HTML, same-name folders, duplicate URLs, original hashes, and export reparsing |
| I4 | `fetching.py` | Implement HTTP retrieval, rendering fallback, text extraction, limits, retrieval states, and public-URL restrictions | I3 | V2 covers success, 404, denial, timeout, missing text, redirects, private addresses, and rendering fallback |
| I5 | `llm.py` and settings schemas | Implement independent per-URL chat, JSON validation, model selection and probes, embeddings, and vector validation | I3, I4 | Recorded fake API requests in V2 prove isolation and abnormal-response handling; V4 covers the real specified models |
| I6 | `jobs.py` | Implement the persistent worker, progress, pause/resume, reuse of successful stages, and duplicate-start prevention | I3, I4, I5 | V2 proves that interruption, restart, and resume do not reprocess successful URLs and preserve all target items |
| I7 | `organizing.py`, `integrity.py`, and proposal APIs | Implement selection scope, semantic organization, exception folders, comparison proposals, edits, ID/URL/out-of-scope checks, and the export gate | I5, I6 | V2 covers all/single/multiple/overlapping selections, multiple bookmarks sharing a URL, out-of-scope invariance, and export rejection after deliberate loss or duplication |
| I8 | `templates/`, `frontend/`, `app.py`, `i18n.py`, `locales/`, and `README.md` | Implement all operations from I1 and connect states, validation errors, connection failures, resume, and export. Complete English/Japanese catalogs, Automatic detection, persistent manual overrides, and consistent fragment/client localization. Serve assets locally and finish English public-repository documentation | I1–I7 | V3 covers core operations, both locales, manual overrides, and DOM/layout/keyboard paths at 1440×900 and 390×844; V1 inspects documentation and tracked artifacts for R13; V4 covers a complete real-model workflow |

These stages define construction order, not an MVP that reduces final scope. Completing HTML import/export does not complete implementation while semantic organization, partial processing, or specified-model verification remains unfinished.

## Bounded Automated Verification

Treat this list as the sufficient required verification scope. This is currently a plan only; none of the following checks has run. Because no project commands existed, all commands and test paths below are proposals to create during implementation. Apply a subprocess timeout or equivalent to each command. Do not use watch mode. Capture logs in a temporary location and report only concise success summaries or necessary failure excerpts.

| Unit | Command / evidence | Prerequisites / time limit | Pass conditions |
| --- | --- | --- | --- |
| V1 | `uv run --locked ruff check src tests`, `uv run --locked ruff format --check src tests`, `uv run --locked ty check src`, `npm run lint`, `npm run typecheck`, `npm run build`; inspect README/configuration and `git ls-files` against the runtime-data exclusions | I2–I8 and lockfiles; 120 seconds per command, 60 seconds for artifact inspection | Lint, formatting, and type checks pass. Build generates the manifest and JS/CSS, and Jinja can reference them. English setup instructions cover both runtimes and language settings; tracked artifacts contain no real bookmark data, credentials, model binaries, or machine-specific product paths |
| V2 | `uv run --locked pytest -q tests/test_bookmarks.py tests/test_fetching.py tests/test_llm.py tests/test_jobs.py tests/test_organizing.py tests/test_i18n.py` | I3–I8; fake transports and temporary databases only; 180 seconds total | All critical conditions described above pass. Prove that preservation checks do not overlook loss of duplicate-URL bookmarks by considering only a URL set. Verify `ja-JP`, `en-US`, an unsupported language, missing/invalid headers, quality ordering, quality-zero exclusion, manual override precedence, invalid preferences, catalog key/placeholder parity, and no mutation of bookmark data from UI-language changes |
| V3 | `uv run --locked python tests/smoke_app.py` | Built assets and installed Playwright Chromium; 180 seconds total | Start actual uvicorn with a temporary database, fixtures, and fake AI. Complete import → multiple-folder selection → start → completion → proposal edits → download → reparse. Verify pause/resume entry points, localized error presentation, and out-of-scope invariance. Use deterministic English/Japanese browser contexts to check Automatic mode, manual override persistence after reload, document language, and HTMX/client consistency. Assert no JS exceptions, successful static asset responses, no whole-page overflow beyond the viewport in either locale, and reachable/focusable primary controls. Stop the server and browser in finally |
| V4 | `uv run --locked python tests/smoke_local_models.py --settings data/settings.json` | Both specified GGUF models loadable in the actual runtime and APIs available; 120 seconds per API call and 600 seconds total | Use two public fixture pages and a 404 fixture to produce independent structured analyses, finite equal-dimension embeddings, a similarity-based proposal, and same-count HTML preserving original URLs. Record actual runtime versions, API model IDs, and their GGUF mappings. Fake output cannot substitute for success |

If V4 uses a localhost fixture server, permit only those fixtures through a test-specific transport without weakening the product's public-URL restriction. Call the actual local AI APIs. Record the two V4 requests and assert that neither includes the other URL's information. Do not fix expected category answers to ambiguous model prose. Use structure, input isolation, numerical validity, and preservation as pass conditions, and retain readable samples of generated content.

Each individual V1 command and each of V2, V3, and V4 allows at most three executions: one initial run and two reruns after focused repairs. Count across interruptions and edits. Invalidate evidence after relevant changes and rerun only affected units within the remaining budget. Do not reset a failed unit's budget by renaming it, switching tools, or subdividing it. Stop verification once the required checks pass; optional polish does not justify expanding the checks.

Follow the explicitly invoked implementation-planner, execute-implementation-plan, and environment-preparation skills: do not use CUA, AI-driven screen observation, interactive clicking, typing, or browser navigation for verification. Finite, previously written Playwright scripts may run as automated tests. The Build Web Apps rules for interactive browser checks and AI screenshot comparison do not override this explicit verification restriction. Convert specified copy, colors, text sizes, and spacing into automated DOM/CSS assertions. Do not claim unperformed image-based 10/10 fidelity verification.

If the same unresolved defect remains after the allotted attempts and diagnosis is uncertain, stop retrying. Record the diagnostic, attempted repairs, cumulative execution count, and known reasoning effort in this plan. Stop earlier if the same failure recurs without a new diagnosis. Recommend that the user raise reasoning effort by one level and request continuation; name the current/next levels only when known, and do not change settings yourself. Allow a new round of at most three executions only after the user confirms an increase and requests resumption; retain cumulative history. For known external causes such as a stopped service, missing model, or permission, identify the concrete prerequisite to resolve instead. Continue independent authorized work.

## Recommended Operation Checks (After Completion)

These are recommendations after implementation and required automated verification are complete. They are outside the required checklist and implementation completion gates. Do not report them as human checks performed by the agent.

- Import a small sample of the user's own HTML and confirm that the folder tree and total count match the original.
- Select two folders and organize them. In the comparison screen, check whether suggested names convey their purpose and unselected content remains unchanged.
- Pause processing and resume it, confirming that it continues from the saved progress.
- Leave language mode on Automatic and check that a Japanese browser preference shows Japanese while other languages show English. Select English or Japanese manually, reload, and confirm that the chosen language persists without changing bookmark data.
- Import exported HTML into a separate Chrome profile and inspect hierarchy, text, and URLs. When importing into an existing profile, account for duplicates caused by addition and retain the original HTML.

After implementation, the executor must include a short “Recommended operation checks (after completion)” list in the final response with concrete actions and expected results. Do not ask the user to substitute for automated testing during production or make user operation a completion prerequisite. Do not conceal unresolved automated checks with these recommendations. Declare implementation complete and set Current to Complete and Next to None only when all I/V items have current evidence.

## Permission Boundaries and Resumption

The current stopping point is P3. Environment inspection is complete; do not install dependencies or create product sources. When implementation is requested, read the full plan, Git status, applicable AGENTS.md instructions, and files needed for the next item, then proceed from I1. Across conversations, reconcile checklist state with actual artifacts and do not repeat completed stages.

Later implementation centers on local edits and automated verification. This plan alone does not authorize commits, pushes, publication/deployment, writes to Chrome, file deletion, or model downloads. When needed, check existing user authorization and tool permissions. If authorization is missing, prepare the specific targets, size, and impact before asking.

Documentation alone does not establish real-model compatibility. If V4 lacks a prerequisite, leave it incomplete and identify the verified need for a runtime update, model installation, or API startup. Never silently substitute another model for a specified one.

Preserve data using the original file and immutable import snapshots. Version proposals and apply updates transactionally. Do not destructively overwrite originals or existing proposals. Validate exports in memory or a temporary file and expose only successful results for download. After interruption of import, job creation, or proposal generation, inspect existing hashes, job tokens, and versions before resuming to prevent duplicate creation.
