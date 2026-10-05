# Screen Spec: Quant Trading Desk Dashboard

- **Status:** Approved
- **Owner:** ui-designer
- **Route:** `/`
- **Primary persona:** Quantitative Forex Trader / Algorithmic Desk Operator
- **User intent:** Monitor real-time MT4 EURUSD/USDCAD market data, inspect live technical chart with indicator overlays, manage open positions, and control live bridge execution.
- **Funnel stage:** core value
- **Primary success action:** Execute or pause live trading bridge with strict risk boundaries.
- **Design system:** `design-system/MASTER.md`
- **Page override:** none

## Visual Direction

- **Visual thesis:** High-density, calm institutional trading desk. Obsidian dark background with translucent acrylic surfaces and electric lime focal accents.
- **Signature moment:** Live tick-by-tick forming candle progression synchronized with dynamic 1:5 R:R take-profit bracket markers and real-time total equity ticker.
- **Avoid:** Generic cartoonish crypto charts, blinding pure white glare, low-contrast text, laggy animations, ambiguous rounding of price ticks.
- **Content hierarchy:**
  1. Primary Focal Point: Live Financial Chart Canvas and Total Account Equity.
  2. Secondary Controls: Currency Pair Selector Chips (EURUSDm, USDCADm), Primary Action CTA ("Start Live Trading").
  3. Tertiary Data: Active Positions & Historical Ledger Table, Multi-segment Risk Meter.
  4. Context & Meta: Header navigation bar, MT4 broker status, low-latency sync indicator.

## Anatomy

1. HeaderNav — Top persistent application navigation bar (`--color-bg-primary`, 40px nav pill targets, MT4 connection status badge).
2. MarketChips — Currency pair switcher cards (`--color-bg-card`, 44px+ hit target, active pair lime border glow).
3. TradingChart — Interactive multi-timeframe financial chart canvas (`--color-bg-card-dark`, customizable indicators, live bid badge).
4. TransactionsTable — Tabular order ledger (`--color-bg-card-light`, tabular monospace figures, status dots).
5. AccountCard — Total equity hero, per-trade risk budget, position sizing lots, and 50px high-contrast CTA button.
6. RiskMeterCard — Institutional risk guardrails, daily drawdown ceiling, spread watchdog, segmented progress bar.

## Content

- H1: QUANT TRADING DESK
- Supporting copy: Automated TrendWise algorithmic trading system with Exness MT4 bridge
- Primary CTA: Start Live Trading
- Secondary CTA: Emergency Kill-Switch
- Proof/trust: Live MT4 Terminal Sync, Exness Pro Account verification, 100% deterministic test coverage.
- Error/empty copy: "LOCAL API BRIDGE OFFLINE — Launch backend with scripts\run_app.bat or python -m api.server" / "No Active Open Positions"

## Responsive States

| Viewport | Layout | Visibility/order changes | Overflow behavior |
|---|---|---|---|
| 320–428 | Single Column Stacked | Nav items collapse into drawer, chart stacks above ledger | Vertical scroll with fixed sticky header |
| 768–1024 | Vertical Split | Chart flex 4, Ledger flex 3, Control rail placed below | Nested scrollable table and chart view |
| 1280–1920 | 7:3 Asymmetric Grid | Left panel (Chart & Table flex 7), Right rail (Account & Risk 360px) | Viewport bounded with internal table scrolling |

Also supports landscape orientation, 200% and 400% zoom without horizontal clipping, and high-contrast system modes.

## Interaction States

- Primary CTA (`Start Live Trading`): Default `#CDFF64` background with dark `#080C15` text; Hover elevates with `#CDFF64` shadow glow (blur 14); Active pressed scales down 0.98; Running state transitions to `#FF9500` ("PAUSE BRIDGE EXECUTION").
- Destructive Action (`Emergency Kill-Switch`): Default outlined crimson border `#FF3B30`; Hover illuminates background with 15% opacity; Triggered state transitions to green ("RESUME FROM EMERGENCY HALT").
- Instrument Selector Chips: Click switches active chart symbol without price scale distortion; Active state shows 1.5px `#CDFF64` border with subtle cyan icon container.
- Reduced Motion: Micro-interactions and tab transitions honor `prefers-reduced-motion` and collapse durations to 0ms.

## Accessibility

- Landmark and heading outline: `<header>` with single H1 (`QUANT TRADING DESK`), `<main>` containing chart section and ledger, `<aside>` containing risk rail.
- Focus order and focus restoration: Logical tab order from top navigation to pair chips, chart controls, execution buttons, and settings dialog.
- Labels, descriptions, error association: Screen-reader labels on all chart action icons (`Candles`, `Bars`, `SMA 20`, `EMA 50`, `VOL`, `CROSS`).
- Contrast pairs: Body text `#F9FAFB` on `#131B2E` (16.5:1), Secondary labels `#94A3B8` on `#131B2E` (5.6:1), Active CTA text `#080C15` on `#CDFF64` (13.8:1). All exceed WCAG AA standards.
- Keyboard alternative: Full keyboard shortcut support (Space/Enter activates buttons, Arrow keys navigate tabs, Esc closes settings).

## Instrumentation

- Events: `bridge_started`, `bridge_paused`, `emergency_halt_toggled`, `pair_switched`, `timeframe_changed`, `chart_type_changed`.
- Properties: `symbol`, `timeframe`, `equity`, `spread_pips`, `risk_pct`.
- Experiment exposure: none

## SEO (public routes only)

- Title / description: AK Forex Trading — Institutional Quant Trading Terminal
- Canonical / indexability: desktop application / internal client
- JSON-LD / OG image: internal desktop client
- Server-rendered content requirement: not applicable

## Acceptance Evidence

- [x] Approved against `design-system/MASTER.md`
- [x] Tested at 1600x1000 desktop view and 800x600 minimal view
- [x] Loading, empty, and live streaming states implemented cleanly
- [x] `python -m orchestrator.cli frontend-check --area design` passes
