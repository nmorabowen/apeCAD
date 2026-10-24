# ADR 0038 — Programmatic WCAG/CVD token gates and deterministic still capture

**Status:** Accepted (2026-10-24)

Builds on [ADR 0031](0031-ape-design-system.md) (the APE design system tokens and CVD rules).

## Context

ADR 0031 established the token table in `static/css/app.css` and forbade red-vs-green state distinctions, but `tests/test_ui_tokens.py` only checked token presence and retired hex literals on `static/js/*.js`. It did not scan `static/section/*.js`, did not programmatically verify WCAG contrast ratios or color-vision-deficiency (CVD) perceptual separation across light/dark themes and canvas presets, and the 3-D viewport had no deterministic PNG still capture helper for visual inspection.

## Decision

1. **Expand token scanning to `static/section/*.js` (excluding `static/vendor/`).**
   - `tests/test_ui_tokens.py` scans both `static/js/*.js` and `static/section/*.js` for retired raw colours and unauthorized hex literals, while excluding vendored Three.js files under `static/vendor/`.
2. **Programmatic WCAG luminance contrast and Viénot CVD OKLab distance gates.**
   - `static/js/theme.js` exports pure colour-science helpers (`relativeLuminance`, `contrastRatio`, `simulateCvdHex`, `oklabDistance`) tested in `tests/js/theme.test.mjs`, and mirrored in `tests/test_ui_tokens.py`:
     - UI text (`--text`, `--muted`, `--accent-text`, `--signal-text`) against chrome surfaces (`--surface-0`, `--surface-1`, `--surface-2`) satisfies WCAG contrast $\ge 4.5:1$ in both light and dark themes.
     - Primary canvas strokes and semantic indicators (`--ink-edge`, `--pick`, `--snap`, `--ink-concrete`, `--ink-section-guide`, `--ink-rebar`) against every canvas background (`#ffffff`, `paper`, `mist`, `carbon`) satisfy contrast $\ge 2.2:1$.
     - Semantic pairs (`--pick` vs `--snap`, `--ink-rebar` vs `--ink-concrete`, `--accent` vs `--signal`) maintain OKLab perceptual distance $\ge 0.055$ under both normal vision and Viénot 1999 protanopia/deuteranopia simulation.
3. **Deterministic viewport still capture (`exportViewportPng`).**
   - `viewport.js` exports `exportViewportPng()` (and `app.js` binds `window.__apecadCaptureStill = exportViewportPng`) to force a synchronous render pass and return a PNG data URL of the 3-D canvas.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Manual-only contrast review | Regresses silently when a token or canvas preset is tweaked. |
| Headless browser in CI | Violates ADR 0022 (fast stdlib/pytest + node gates without browser binaries in CI). |

## Consequences

- `tests/js/theme.test.mjs` and `tests/test_ui_tokens.py` fail automatically if any theme or canvas preset violates WCAG contrast or protanopia/deuteranopia OKLab separation thresholds.
- `window.__apecadCaptureStill()` provides one-call PNG capture for interactive and automated visual verification.
