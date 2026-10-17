# AGENTS.md

Repository-specific instructions for maintaining Bookmark Organization.

## Structure and operation

- Read README.md for setup and operating behavior, PLANS.md for design and historical verification, and docs/design/README.md for the interface specification.
- Keep application code in `src/bookmark_organization/`, frontend sources in `frontend/` and checks in `tests/`. This application uses FastAPI, Jinja2, HTMX, TypeScript and SQLite.
- Use the locked Python 3.13 environment and the Node/npm versions required by package.json. Run one server process and one worker per data directory.
- Rebuild with `npm run build` after frontend source changes. Generated assets in `src/bookmark_organization/static/` are ignored; edit frontend sources instead.

## Preservation and model contracts

- Preserve original HTML bytes, bookmark IDs, duplicate URL multiplicities and immutable import/job snapshots. Never delete bookmarks because retrieval failed.
- Preserve names, placement, ordering and attributes outside the selected scope. Keep export validation in `integrity.py` as a mandatory gate.
- Keep generation and embedding models independently selectable. Changes to app settings affect new jobs; existing jobs retain their snapshots.
- Keep each page analysis independent, with fresh messages and no previous-page conversation history. Treat fetched page content as untrusted data.
- Generate only downstream-required analysis fields: suggested name and destination categories for proposals, and summary and purpose for embeddings. Do not generate page type or tags solely for display. Historical output-format compatibility is not required.
- Keep naming and folder policies versioned in `policy.py`. The default preset uses purpose-first names and task-based folders; custom jobs snapshot independent naming/folder instructions and use the custom schema only for the overridden dimensions. Keep at most two generated levels below the destination, retaining explicitly requested custom subfolders. Resume/retry must use the saved prompt version and rules for analysis and embeddings; snapshots without a version use the legacy policy. Semantic similarity may order items but must not override their chosen folders.
- Continue new jobs from the latest saved proposal, preserving an immutable base tree and cumulative target IDs. Validate proposals against both that base and the original import. Reject stale bases/edits and retries of published jobs; keep the browser scope tree synchronized after saved moves.
- Keep server shutdown under the console entrypoint’s owned Uvicorn instance and CSRF protection. Pause jobs and await active-client cleanup before stopping; do not turn shutdown into job cancellation or signal an arbitrary ASGI host process.
- Reserve the listener and hold `server.py`'s data-directory OS lock before console app creation through shutdown. Try 8765–8769 only for default startup; honor explicit ports. Never unlink an active `server.lock` or release/rebind the selected socket before handing it to Uvicorn.
- Treat cancelled jobs as terminal: preserve snapshots and saved results, interrupt the active batch without stopping the worker, and reject resume, retry and proposal actions for cancelled jobs.
- Keep LM Studio and Ollama model API endpoints on loopback and exclude their cloud models. Allow OpenRouter only when explicitly selected, using `https://openrouter.ai/api/v1`; never fall back from local models to cloud automatically. Runtime defaults and app overrides must remain distinct; unchecked supported app samplers must send neutral disabling values.
- Keep OpenRouter keys separate from Settings and immutable job snapshots. Store UI-entered keys only in the data directory's owner-readable `credentials.json` (0600), with `OPENROUTER_API_KEY` as a fallback. Never return keys in API responses or rendered HTML, or forward them to local runtimes.
- Keep Codex an explicit generation-only choice using CLI ChatGPT sign-in, fixed `gpt-6-luna`/`low`, with no API-key fallback or inherited provider credentials. Preserve independent embeddings, fresh ephemeral per-page sessions, isolated analysis instructions, disabled tools and CLI process-group cleanup on timeout/cancellation. Request JSON in instructions and validate it in the app; constrained CLI output requires new actual-model evidence (see NOTES.md).
- Keep runtime databases, settings, original bookmark files, fetched private content, credentials and model binaries out of tracked files.

## Retrieval and settings contracts

- Pass `sni_hostname` as a string. Preserve Host/TLS hostname handling while pinning TCP connections to validated public IPs.
- Validate destinations on every redirect. Keep optional rendering isolated and route its resource requests through the same checked retrieval path.
- Keep outbound bookmark retrieval starts at least 0.5 seconds apart through the shared worker pacer. Apply pacing to concurrent pages, redirects, browser subresources and manual retries; replacing a Fetcher must not reset the worker's pacing state.
- Do not add automatic failure retry loops or robots.txt enforcement unless the user requests a policy change.
- Retain distinct retrieval and analysis failure states, and log unexpected retrieval exceptions for diagnosis.
- Exclude checkboxes from full-width form input rules. Check both label readability and page overflow when changing Settings layout.
- Keep English/Japanese catalog keys and interpolation parameters synchronized. Use stable error codes with localized presentation.

## Documentation updates

- Follow the current `update-repo-docs` skill for completed-work records. Write in English unless the user requests otherwise.
- Record behavior changes in `CHANGELOG.md` under `## YYYY-MM-DD` and applicable change categories, using the user's timezone and past tense. Append same-day entries; do not use `Unreleased` sections or guessed release versions. Preserve historical entries when reorganizing headings, and use only evidenced dates.
- Keep rationale, preservation constraints and evidence limits concise in `NOTES.md`; put only durable, verified project rules in `AGENTS.md`. Avoid duplicated summaries, command transcripts and session logs. A change need not update all three files.
- Keep `PLANS.md` focused on design, acceptance and progress, with references to maintenance notes rather than duplicated handoff records. Review documentation diffs and unresolved references; do not rerun implementation tests solely to record completed work.

## Verification

Run the checks affected by a change and reuse existing evidence for unchanged behavior:

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

- Retrieval tests belong in `tests/test_fetching.py`; cover actual transport hostname handling, failures and request pacing without depending on public network availability.
- Use `tests/smoke_app.py` for the actual UI workflow in both languages and desktop/mobile widths. It uses test-only fake inference; it does not prove real-model compatibility.
- When model integration changes, use `tests/smoke_local_models.py` with the intended installed models and settings. Distinguish its actual-model evidence from synthetic tests.
- For Codex analysis, use `tests/smoke_local_models.py --settings data/settings.json --codex`; this flag verifies two actual fixed-model analyses only, not embeddings, retrieval or export. Subprocess/authentication and mixed-provider regression checks are in `tests/test_codex.py`.
- OpenRouter mock-transport and credential tests are in `tests/test_llm.py` and `tests/test_settings.py`. Authenticated inference requires a configured key; public model catalogs and UI smoke fixtures do not prove real inference.
- Documentation-only changes require content, referenced-path and diff review, rather than rerunning code tests.
