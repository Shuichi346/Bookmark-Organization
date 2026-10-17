# Notes

## 2026-10-17

### Custom rules and continuous organization

`OrganizationRules` snapshots naming and folder prompts independently; `bookmark-custom-v1` replaces only the explicitly customized policy dimensions. The purpose preset keeps its schema and sparse-subfolder merging, while custom folder paths retain small subfolders. Page content remains untrusted and each request remains independent. Prompt and output bounds still apply.

The selectors now persist `naming_mode` and `folder_mode` independently, so inactive nonempty prompts cannot override their presets. Older shared `preset` values are normalized only when read, without changing immutable snapshots. Browser drafts retain disabled text and migrate older shared selections. Regression tests exercise all four mode combinations and legacy input.

The independent-selector follow-up passed 172 tests, Python static checks, frontend lint/typecheck/build and the English/Japanese Playwright workflow at desktop/mobile widths. Mixed selections, inactive drafts, reload restoration and explicit per-dimension job snapshots passed without overflow or unexpected browser errors. This changed selection/serialization only; it reused the actual-model policy evidence below without new inference calls.

Each new job snapshots the latest proposal tree and cumulative authorized bookmark IDs. `get_proposal` and proposal saves validate both the immediate base (protecting prior edits outside the current scope) and immutable import (protecting original folders, IDs, attributes and URL multiplicities). Writes are serialized and stale bases/edits are rejected. Published jobs require a new analysis instead of retry, and editing a previous result cannot strand a completed unpublished child. Saved moves also update the browser's scope tree before continuing. `tests/test_continuation.py` covers A → edit → restart → B → F with C untouched, generated-folder selection and conflicting writes.

Verified: 167 tests, Python static checks, frontend lint/typecheck/build, and the real-server Playwright workflow in both languages at 1440×900 and 390×844 passed. UI checks covered custom drafts after reload, preset switching, saved moves/counts, continuation snapshots, prior-edit preservation, project reopening and cumulative export, with no unexpected browser errors or overflow. Browser plugin was unavailable; screenshots from the existing Playwright workflow were inspected outside the repository. The existing HTMX eval build warning remained.

Actual selected-provider verification passed with Codex `gpt-6-luna`/low for two independent custom analyses and LM Studio `text-embedding-embeddinggemma-2` for normalized 768-dimensional vectors. Requested exact names `FastAPI`/`TypeScript` and paths `Python/Frameworks`/`JS libraries/Language` survived proposal generation and integrity-checked export. These were public-text fixtures, not live page retrieval or processing of user bookmarks. The initial full-model check stopped while LM Studio was unavailable; after startup, a test-only missing snapshot setting was corrected and the complete run passed. The custom check is available through `tests/smoke_local_models.py --settings data/settings.json --custom`; `--analysis-only` isolates generation.

## 2026-10-13

### Codex subscription analysis

`codex.py` ran the installed CLI with ChatGPT authentication only, fixed `gpt-6-luna`/`low`, an allowlisted environment without API keys, and an empty temporary working directory per request. It used isolated analysis instructions, ephemeral sessions, read-only execution and disabled command, browser, plugin, memory, hook and agent tools. Login was checked before discovery and each analysis, with `forced_login_method="chatgpt"` enforcing the execution path. Catalog presence was not an entitlement check. Embeddings retained their separate provider and immutable job snapshots. Response deadlines and worker cancellation terminated and reaped the CLI process group; raw subprocess diagnostics were not returned to the UI.

With CLI 0.160.1 and the current subscription route, `--output-schema` repeatedly produced incomplete responses with `max_output_tokens`. The final path specified the schema in analysis instructions and used the existing Pydantic validation and one same-page repair. Replacing the built-in coding instructions also avoided unrelated coding context. Do not reintroduce constrained CLI output without actual-model evidence. CLI transport recovery is internal to Codex; the application adds no retry loop for authentication, connection or quota failures.

Verified: 145 unit tests, Python static checks, frontend lint/typecheck/build, and the English/Japanese real-server Playwright workflow at 1440/390-pixel widths passed. The final `tests/smoke_local_models.py --codex` run completed two independent actual `gpt-6-luna`/`low` analyses with the four required fields and no tool actions. This flag used bounded public-page text fixtures and did not verify live retrieval, real embeddings or export. Synthetic coverage checked API-key rejection and environment isolation, schema validation, failure handling, process cancellation/timeouts, settings save/probe and snapshot preservation. The existing HTMX eval build warning remained; browser tests reported no unexpected console errors. Screenshots stayed outside the repository. Browser plugin was unavailable, so the existing Playwright workflow was used.

### Purpose-based naming and folder placement

Cluster-majority labels and singleton demotion could override a page's intended use. `organizing.py` therefore used each validated purpose path for placement and retained semantic clusters only for related-item ordering. The supplied taxonomy remained an example, allowing other specific purposes. A subfolder required three items and other items in the same top category; the destination/`整理済み` wrapper did not count toward the two generated classification levels.

`policy.py` separated `bookmark-ja-purpose-v2` from `bookmark-ja-v1`. The worker used the saved version for both analysis and embeddings, defaulting missing versions to legacy to avoid mixing cached and resumed results. The bookmark's own original folder path remained untrusted intent context. `PurposeAnalysis` enforced name/path structure, and proposal generation revalidated saved outputs. Manual edits remained flexible. Regression coverage in `tests/test_llm.py`, `tests/test_jobs.py` and `tests/test_organizing.py` protected policy isolation, sparse-folder handling and export preservation.

Verified: 131 unit tests, Python static checks and the English/Japanese Playwright workflow at desktop/mobile widths passed. Actual selected OpenRouter models passed analysis, embeddings and export on two synthetic documents. Local-model inference and live retrieval were not reverified. Detailed model IDs, samples and acceptance evidence remain in the 2026-10-13 purpose-policy amendment in `PLANS.md`.

### Downstream-only analysis output

Page type and tags were display-only outputs; neither contributed to folder placement nor embedding input. They were removed from the shared analysis schema and purpose prompt, with `bookmark-ja-purpose-v3` marking the reduced output. Summary and purpose remained because the embedding model consumed both for related-item ordering. The comparison details displayed those two fields with a localized summary label. The user explicitly waived historical output-format compatibility, so no old-schema generation adapter was introduced. Saved analysis data was not rewritten.

Verified: all 131 unit tests, ruff check/format, ty and the English/Japanese real-server browser workflow at desktop/mobile widths passed. Mock transports checked the four-field schemas for LM Studio, Ollama and OpenRouter and unchanged embedding input. The LM Studio-specific harness stopped before inference because the current selections were OpenRouter. Two synthetic fixtures using the selected `nvidia/nemotron-3-super-120b-a12b:free` generation and `nvidia/nemotron-3-embed-1b:free` embedding models returned exactly the four required fields, normalized 2048-dimensional embeddings and an integrity-validated export preserving all three URLs, including a synthetic 404. Frontend sources/assets were unchanged, so no rebuild was needed. The app was restarted after confirming no running or paused jobs; its health endpoint passed. No speed comparison or new local-model inference was performed.

## 2026-10-12

### Job cancellation

Running and paused jobs gained a terminal `cancelled` state and a localized Cancel control. The conflict message now offers resume, completion or cancellation. Cancellation retained original bytes, bookmark identities, immutable job snapshots and saved stage results, marked unfinished items as cancelled and released the active-project constraint. Resume, retry and proposal creation were rejected for cancelled jobs. The worker held a separate batch task so cancellation interrupted application request waits without terminating the worker loop. Repeated cancellation did not cancel cleanup again; retrieval and inference clients were both closed.

Verification passed: all 93 unit tests, ruff/format/ty, frontend lint/typecheck/build and the real-server Playwright smoke workflow. Blocking synthetic clients covered cancellation during model availability, retrieval, analysis and embeddings, subsequent jobs, CSRF and restart persistence. English/Japanese workflows at 1440/390 pixels exercised running/paused cancellation, reload and new analysis, with no overflow or unexpected console errors. External screenshots confirmed readable controls and terminal guidance. Browser plugin was unavailable, so the existing Playwright workflow was used. New test assertions initially failed on an ambiguous heading and an expected HTTP 400 validation log; both were corrected before the passing run. The existing HTMX eval build warning remained.

The production server was restarted at `127.0.0.1:8765`; saved jobs remained available without automatically resuming processing. Actual provider-side cancellation was not verified: disconnecting application requests cannot guarantee a provider stops work it already accepted. No user job was explicitly cancelled by validation.

### Editable model IDs

Both model fields gained direct text entry alongside a native suggestion dropdown. Typing filtered candidates case-insensitively, model discovery retained entered IDs even when absent from its results, and save/reload preserved generation and embedding values independently. Provider changes cleared the corresponding field and stale candidates. Processing-time availability and role checks were unchanged.

Frontend lint/typecheck/build, Python static checks, all 13 locale checks, the browser smoke workflow and focused browser QA passed. Playwright exercised typing, discovery, filtering, selecting a candidate and save/reload in English/Japanese at 1440/390 pixels without overflow or JavaScript/console errors. Initial native datalist keyboard selection could not be exercised in headless Chromium; the final implementation used a labeled select with explicit synchronization, which passed the selection check. Screenshots and focused QA stayed outside the repository. The running app served the new input/select markup without changing saved production settings.

### Explicit OpenRouter provider

The user requested OpenRouter through its OpenAI-compatible API, superseding the local-only restriction for that explicitly selected provider. LM Studio and Ollama remained on loopback with cloud-backed models excluded and no automatic cloud fallback. Generation and embeddings remained independently selectable. Discovery validated the key through `/key`, listed structured text models through `/models`, and listed text embeddings through `/embeddings/models`. The public embedding catalog returned HTTP 200 with the expected role metadata; this did not establish authenticated inference.

UI-entered credentials were stored separately in owner-only `credentials.json` (0600), with `OPENROUTER_API_KEY` as a fallback when no stored key existed. Blank submissions retained the key. Keys were excluded from settings responses, rendered HTML and immutable job snapshots; worker batches read the current credential on start/resume. OpenRouter payloads used model-supported controls, `repetition_penalty` and unified `reasoning`, with structured-output-capable provider routing. Cloud embeddings received plain input instead of the local EmbeddingGemma task prefix. Auth, credit and rate-limit errors were localized and did not trigger automatic request retries.

Verification passed: 88 unit tests, ruff, format, ty, frontend lint/typecheck/build, and the real-server browser smoke workflow. The first new browser run failed because a test-side response coroutine was not awaited; correcting that await allowed the workflow to pass. A focused Playwright run after the final password-field layout change passed in English/Japanese at 1440 and 390 pixels, with provider switching, mocked discovery, save/reload, key redaction, no overflow and no JavaScript/console errors. Screenshots used synthetic model IDs and stayed outside the repository. Browser plugin was not available, so the existing Playwright environment was used. Production startup on `127.0.0.1:8765` returned HTTP 200 for health and the page with the OpenRouter option.

Authenticated OpenRouter inference was not exercised because no key was configured. Actual local-model acceptance was not rerun because both configured LM Studio model API checks failed with ConnectError; previous actual-model evidence remained historical. The build retained its existing HTMX eval warning, while app configuration and CSP continued disabling evaluation.

## 2026-10-11

### HTTPS retrieval

The shared failure was reproduced in the installed HTTPX 0.28.1 / httpcore 1.0.9 asynchronous transport. The fetcher passed a bytes SNI hostname; AnyIO's hostname encoding raised `AttributeError` before HTTPS content could be retrieved. The broad exception handler converted that error to `extraction_failed`, obscuring the cause. Passing a string resolved the reproduced error, and unexpected exceptions were logged for future diagnosis.

The regression test now exercised the default HTTPX asynchronous transport with a synthetic network stream and the installed AnyIO hostname validation, rather than relying only on MockTransport's extension assertions. This test did not perform a real TLS handshake. Separate live checks successfully fetched and extracted IRBANK and Multpl; BLS returned HTTP 403 and was classified as `denied`.

### Request pacing

A shared `RequestPacer` used an asynchronous lock and monotonic time to enforce a minimum 0.5-second interval between request starts. The production worker retained it across Fetcher replacement, so manual retries and subsequent jobs did not reset the interval. Every redirect and optional browser resource request passed through the same paced retrieval method. Failed requests were not automatically retried, and robots.txt checks were not added, as requested by the user. The interval applied to bookmark retrieval, not local model API calls.

### Settings layout

The settings grid's full-width input rule had overridden the checkbox width. The checkbox consumed the row's available width and forced its adjacent label into vertical wrapping. Excluding checkbox inputs corrected the layout. Browser acceptance added checkbox-width and label-height assertions at desktop and mobile widths, since page-overflow checks alone had missed the defect.

### Verification and remaining limits

- All 55 unit tests passed. An existing job-snapshot test explicitly set its initial runtime/thinking settings instead of depending on outdated product defaults.
- Ruff, formatting, ty and the production frontend build passed. The existing HTMX build warning about bundled eval remained.
- The browser smoke workflow passed in English and Japanese, including settings persistence, import, pause/resume, proposal edits and export. Playwright screenshots at 1440 and 390 pixels confirmed the corrected settings layout; the console reported only a favicon 404.
- The local server was restarted and its health endpoint returned HTTP 200. Existing failed job results were retained for manual retry.

These checks did not establish successful retrieval of every user bookmark. Authentication, access rejection, dynamic content and timeouts can still prevent retrieval. The live checks used JavaScript rendering disabled; rendered-resource pacing followed the shared request path, but was not separately exercised against a live rendered site. Real-model acceptance was not rerun for these retrieval/CSS changes; prior model evidence remained in PLANS.md.

