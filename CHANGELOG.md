# Changelog

## 0.3.1 — 2026-09-11

- Center circular and oval lettering by visible glyph bounds, with independent
  English/Chinese tracking and protected gaps between upper and lower arcs.
- Match font collection weights during measurement and rendering; outline
  decorative florets so they remain visible without renderer font fallback.
- Fit Chinese labels around center stars and inside ellipse boundaries; center
  complete bilingual and legal-representative name/caption blocks.
- Correct curved bilingual seal clearances and office-stamp line fitting.
- Expand all signature layouts for tall cropped scans, rebalance frames with
  hidden references, and prevent long labels from becoming microscopic.
- Add rendered-pixel regressions for alignment, containment, missing glyphs,
  clipping, spacing controls, and signature size preservation.

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
