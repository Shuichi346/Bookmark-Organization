# Changelog

## 2026-10-13

### Changed

- Unified new Japanese suggestions as specific purpose｜proper name, with page-specific names for documents, articles, Q&A and products and optional GitHub type/language suffixes.
- Assigned folders by each page's intended task, keeping sites, repositories and articles together and using semantic groups for related-item ordering. Created only needed categories, with at most two levels below the destination and sparse or redundant subfolders merged into their parent.
- Preserved saved naming/grouping policies when resuming or retrying existing jobs.
- Limited model-generated analysis to the suggested name, summary, purpose and destination category, retaining summary and purpose for embeddings.

### Removed

- Removed unused page-type and tag generation from analysis prompts and structured-output schemas, and removed their display from comparison details.

### Added

- Added an expandable English/Japanese explanation of naming and folder rules.
- Added Codex as an opt-in content-analysis provider using ChatGPT CLI sign-in without API keys, fixed to `gpt-6-luna` with low reasoning and independently selected embeddings.
- Added localized Codex login, CLI, response-wait and usage-limit errors, isolated per-page processing and CLI termination on cancellation or timeout.

## 2026-10-12

### Added

- Added cancellation for running and paused jobs, interrupting in-flight application requests while retaining original bookmarks and saved results and allowing a new analysis in the same project.
- Added OpenRouter as an independently selectable generation and embedding provider through its OpenAI-compatible API, with role-specific model discovery and mixed local/cloud operation.
- Added masked API-key entry, separate owner-only credential storage, and localized authentication, credit and rate-limit errors.

### Changed

- Made generation and embedding model fields editable with filtered dropdown suggestions, retaining typed IDs when model catalogs are refreshed.

## 2026-10-11

### Fixed

- Fixed HTTPS bookmark retrieval by passing the TLS SNI hostname as a string instead of bytes.
- Fixed sampling controls in Settings by excluding checkboxes from full-width input styling.

### Changed

- Spaced outbound retrieval request starts at least 0.5 seconds apart across the worker, including concurrent pages, redirects, optional browser subresources and manual retry batches.
- Logged unexpected retrieval exceptions on the server to support diagnosis.

