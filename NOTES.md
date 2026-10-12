# Notes

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

