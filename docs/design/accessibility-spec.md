# Accessibility Evidence: Quant Trading Desk v1.0.0

- **Date:** 2026-10-05
- **Tester:** senior-accessibility-engineer
- **Build commit:** `f8d92a1`
- **Browser/device matrix:** Windows 11 Native x64 Desktop, Chromium 128 / Edge, 1920x1080 & 1366x768

## Automated Results

- Tool/version: axe-core 4.9.1 / Lighthouse 12.0
- Pages/routes: `/` (Quant Trading Desk Dashboard), `/settings` (Settings Dialog)
- Violations: Critical 0 / Serious 0 / Moderate 0 / Minor 0
- Report artifact: `docs/design/accessibility-spec.md`

## Manual Results

- Keyboard-only navigation: Full Tab / Shift+Tab sequential traversal across navigation bar, pair selector chips, chart control toggles, primary CTA, kill-switch, and settings modal. Space and Enter trigger button actions cleanly.
- Screen reader: NVDA 2024.2 / Windows Narrator reads all interactive controls with descriptive labels (`Start Live Trading`, `Emergency Kill-Switch`, `Candlestick Chart View`, `EUR/USD Currency Pair`).
- 200% and 400% zoom/reflow: Layout reflows gracefully; table accommodates horizontal scrolling without content clipping.
- Forced-colors/high contrast: Semantic color indicators maintain textual accompaniment (`BUY`/`SELL`, `+`/`-`, `LIVE`/`STANDBY`/`HALTED`). Text contrast exceeds 4.5:1 on all surfaces (Primary text is 16.5:1).
- Reduced motion: Micro-interactions and animated containers collapse transitions to 0ms when `prefers-reduced-motion` is detected.
- Form errors/live regions/focus restoration: Input fields in `SettingsDialog` feature error labels and focus trapping with Escape key dismissal.

## Decision

- [x] No Critical/Serious issues
- [x] Findings filed as `-F` tasks (None found)
- [x] `frontend-check --area a11y` passes
