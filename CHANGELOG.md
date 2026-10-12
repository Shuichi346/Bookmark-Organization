# Changelog

## Unreleased

### Added

- Added cancellation for running and paused jobs, interrupting in-flight application requests while retaining original bookmarks and saved results and allowing a new analysis in the same project.
- Added OpenRouter as an independently selectable generation and embedding provider through its OpenAI-compatible API, with role-specific model discovery and mixed local/cloud operation.
- Added masked API-key entry, separate owner-only credential storage, and localized authentication, credit and rate-limit errors.

### Fixed

- Fixed HTTPS bookmark retrieval by passing the TLS SNI hostname as a string instead of bytes.
- Fixed sampling controls in Settings by excluding checkboxes from full-width input styling.

### Changed

- Made generation and embedding model fields editable with filtered dropdown suggestions, retaining typed IDs when model catalogs are refreshed.

- Spaced outbound retrieval request starts at least 0.5 seconds apart across the worker, including concurrent pages, redirects, optional browser subresources and manual retry batches.
- Logged unexpected retrieval exceptions on the server to support diagnosis.

