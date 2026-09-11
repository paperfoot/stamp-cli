# Changelog

## 0.3.0 — 2026-09-11

- Added the concise `stamp sign` workflow with classic, clean, and
  signature-only layouts, a visible-reference toggle, measured text fitting,
  and safer image cleanup.
- Added consistent physical SVG sizing, 300 DPI PNG export, shared backgrounds,
  seeded wear, protected and atomic output writes, and `--open`.
- Added the offline HTML style gallery, catalog search, file inspection, and
  separately recorded SHA-256 verification.
- Made JSON errors and semantic exit codes consistent, and tightened generated
  style schemas to reject unknown parameters and invalid types.
- Kept introspection offline, improved TTC font-face reporting and caching, and
  updated the supported rendering dependencies.
- Removed source image paths and metadata from PNG output; signature references
  remain content fingerprints rather than identity or signing certificates.

- Replaced legacy Hong Kong and personal seal renderers with measured layouts, fixed physical proportions, transparent paper, and explicit preset overrides.
