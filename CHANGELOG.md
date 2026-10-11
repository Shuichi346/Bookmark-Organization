# Changelog

## Unreleased

### Fixed

- Fixed HTTPS bookmark retrieval by passing the TLS SNI hostname as a string instead of bytes.
- Fixed sampling controls in Settings by excluding checkboxes from full-width input styling.

### Changed

- Spaced outbound retrieval request starts at least 0.5 seconds apart across the worker, including concurrent pages, redirects, optional browser subresources and manual retry batches.
- Logged unexpected retrieval exceptions on the server to support diagnosis.

