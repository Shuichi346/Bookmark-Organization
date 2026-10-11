# Notes

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

