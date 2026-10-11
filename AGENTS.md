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
- Keep model API endpoints on loopback and retain the local-only model policy. Runtime defaults and app overrides must remain distinct; unchecked app samplers must send neutral disabling values.
- Keep runtime databases, settings, original bookmark files, fetched private content, credentials and model binaries out of tracked files.

## Retrieval and settings contracts

- Pass `sni_hostname` as a string. Preserve Host/TLS hostname handling while pinning TCP connections to validated public IPs.
- Validate destinations on every redirect. Keep optional rendering isolated and route its resource requests through the same checked retrieval path.
- Keep outbound bookmark retrieval starts at least 0.5 seconds apart through the shared worker pacer. Apply pacing to concurrent pages, redirects, browser subresources and manual retries; replacing a Fetcher must not reset the worker's pacing state.
- Do not add automatic failure retry loops or robots.txt enforcement unless the user requests a policy change.
- Retain distinct retrieval and analysis failure states, and log unexpected retrieval exceptions for diagnosis.
- Exclude checkboxes from full-width form input rules. Check both label readability and page overflow when changing Settings layout.
- Keep English/Japanese catalog keys and interpolation parameters synchronized. Use stable error codes with localized presentation.

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
- Documentation-only changes require content, referenced-path and diff review, rather than rerunning code tests.
