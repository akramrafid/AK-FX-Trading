# Design System — MASTER (AK Forex Trading Quant Terminal)

> Generated in Phase 3. Frontend, desktop, and mobile consume these tokens only.
> Do not invent colors, type, or spacing in implementation.

## Brand

- Personality: Disciplined, institutional, high-precision, transparent, calm under volatility.
- Voice: Quantitative, direct, authoritative without hype, mathematically exact.
- Anti-patterns: Casino-style gamification, flashing sirens, ambiguous terminology, cluttered widgets without hierarchy.

## Art Direction

- Chosen direction: High-contrast Dark Quant Terminal with Frosted Obsidian Surfaces.
- Visual thesis: The clarity of a Bloomberg/TrendWise terminal combined with modern Apple-grade fluid typography and restrained electric signals.
- Signature element: Electric Lime (`#CDFF64`) primary action accent contrasted against deep void canvas (`#080C15`) and frosted acrylic glass cards.
- Composition rule: Asymmetric 7:3 split workspace. Left area prioritizes the live charting canvas and execution ledger; right rail houses account equity and risk guardrails.
- Image and illustration treatment: High-precision SVG vectors, crisp iconography, and mathematical candlestick rendering. No generic photographic placeholders or decorative clutter.
- Surfaces rule: Surface depth expressed through luminance elevation (`#080C15` canvas → `#0D1424` sub-canvas → `#131B2E` cards → `#1A243D` hover/modal states) with subtle 1px frosted translucent borders (`rgba(255,255,255,0.08)` to `rgba(255,255,255,0.18)`).

## Design Principles

1. **Hierarchy before decoration**: The primary user action (Start Live Trading / Pause) and critical financial numbers (Equity, PnL, Chart Candle) are prominent and perceptible within 3 seconds.
2. **One strong visual idea per surface**: Depth through dark mode elevation and frosted acrylic glass; emphasis through singular electric accents, never color chaos.
3. **Confidence through clarity**: Price levels, lot sizing, spread, drawdowns, and stop-loss/take-profit brackets are rendered in tabular monospace font with zero ambiguous rounding.
4. **Fitts's Law ergonomics**: Interactive controls exceed touch and pointer acquisition standards (min 44px for primary execution CTAs, min 36-40px for compact desktop controls). Destructive actions (Emergency Halt) are isolated with protective confirmation styling.
5. **Accessible by construction**: WCAG 2.2 AA compliant contrast (≥ 4.5:1 for body and data text, ≥ 3:1 for borders and UI component boundaries). Reduced motion and tabular numbers supported universally.

## Color System

### Global Palette & Semantic Alias Tokens

| Token | Light Value | Dark Value | Contrast vs Surface | Semantic Role / Usage |
|---|---|---|---|---|
| `--color-bg-primary` | `#F8FAFC` | `#080C15` | Baseline Canvas | Deep void root workspace background |
| `--color-bg-secondary` | `#F1F5F9` | `#0D1424` | 1.15:1 vs Canvas | Sub-workspace, header container, and side rails |
| `--color-bg-card` | `#FFFFFF` | `#131B2E` | 1.4:1 vs Canvas | Level 1 surface: trading chart, tables, cards |
| `--color-bg-card-light` | `#F8FAFC` | `#1A243D` | 1.8:1 vs Canvas | Level 2 surface: hovered cards, active pills, table headers |
| `--color-bg-surface-elevated`| `#FFFFFF` | `#223050` | 2.3:1 vs Canvas | Level 3 surface: modal dialogs, popovers, tooltips |
| `--color-text-primary` | `#0F172A` | `#F9FAFB` | 16.5:1 vs Card | High-contrast body, titles, financial metrics |
| `--color-text-secondary` | `#475569` | `#94A3B8` | 5.6:1 vs Card (AA Pass)| Subtitles, field labels, metadata |
| `--color-text-muted` | `#94A3B8` | `#64748B` | 3.5:1 vs Card | Inactive labels, table column headers, unit tags |
| `--color-primary-accent` | `#059669` | `#CDFF64` | 13.8:1 vs Canvas | Primary CTA ("Start Live Trading"), active pair glow |
| `--color-accent-cyan` | `#0284C7` | `#00F0FF` | 11.2:1 vs Canvas | Auxiliary metrics, ATR dynamic sizing, data badges |
| `--color-bullish-profit` | `#16A34A` | `#00E676` | 10.4:1 vs Card | Positive PnL, Buy candles, winning stats, online indicator |
| `--color-bearish-loss` | `#DC2626` | `#FF3B30` | 5.2:1 vs Card | Negative PnL, Sell candles, risk warnings, kill-switch |
| `--color-warning-amber` | `#D97706` | `#FF9500` | 7.8:1 vs Card | Spread caution, margin warnings, paused state |
| `--color-accent-purple` | `#7C3AED` | `#A855F7` | 6.1:1 vs Card | R:R bracket ratio badges, secondary metrics |
| `--color-border-subtle` | `#E2E8F0` | `rgba(255,255,255,0.12)`| ≥ 3:1 Boundary | Frosted card outlines and divider rules |
| `--color-border-active` | `#059669` | `#CDFF64` | ≥ 4.5:1 Boundary | Focused inputs, selected pairs, active navigation |

*Rule: Never convey market state by color alone. Always accompany color with textual direction (`BUY` / `SELL`, `+` / `-`, `PROFIT` / `LOSS`, status pill).*

## Typography

Primary UI Font: `Segoe UI`, `Inter`, `-apple-system`, `sans-serif`
Financial & Data Monospace Font: `Consolas`, `JetBrains Mono`, `monospace` with `fontFeatures: [FontFeature.tabularFigures()]`

| Token | Size | Line Height | Weight | Letter Spacing | Usage |
|---|---|---|---|---|---|
| `--text-display` | 44px | 1.15 | 800 (Bold) | -1.2px | Large Account Balance / Equity Headline |
| `--text-xl` | 32px | 1.20 | 700 (Bold) | -0.8px | Modal Title, Key Stats |
| `--text-lg` | 24px | 1.25 | 700 (Bold) | -0.4px | Section Headers, Secondary Balances |
| `--text-md` | 16px | 1.40 | 600 (Semi) | 0.0px | Card Titles, Primary Button Labels |
| `--text-base` | 14px | 1.50 | 500 (Med) | 0.0px | Standard Body Text, Navigation Items |
| `--text-sm` | 12px | 1.45 | 500 (Med) | 0.1px | Sub-captions, Secondary Field Labels |
| `--text-xs` | 10px | 1.40 | 700 (Bold) | 0.8px | Uppercase Metadata Badges, Table Headers |
| `--mono-stat-lg` | 34px | 1.10 | 800 (Bold) | -1.0px | Real-time Equity with Tabular Alignment |
| `--mono-stat-md` | 20px | 1.20 | 700 (Bold) | -0.5px | Risk Budget, Position Sizing Lots |
| `--mono-data` | 12px | 1.35 | 600 (Semi) | -0.2px | Bid/Ask Ticker, Entry Price, SL/TP Levels |

One `<h1>` per view. Monospace figures always use fixed-width tabular numbers to prevent horizontal layout jitter when ticks arrive.

## Spacing & Radii

Scale (4px base unit): `2xs: 2 / xs: 4 / sm: 8 / md: 12 / lg: 16 / xl: 24 / 2xl: 32 / 3xl: 48 / 4xl: 64`. No magic numbers.

- **Content Inset**: 16px to 24px internal card padding.
- **Stack Gaps**: 8px between closely related fields, 16px between distinct card blocks, 24px between workspace sections.
- **Inline Gaps**: 6px to 8px between icons and text, 12px between market chips.
- **Corner Radii**:
  - `sm: 6px` — Tags, badges, small indicator pills.
  - `md: 8px` — Inner containers, button controls, input fields.
  - `lg: 12px` — Interactive market chips, metric panels.
  - `xl: 16px` — Primary workspace cards, charting canvas container.
  - `2xl: 20px` — Dialog windows, top-level containers.
  - `pill: 999px` — Navigation tab pills, status dots, mode toggles.
- **Elevation**:
  - `Level 0`: Flat `#080C15` background.
  - `Level 1`: Subtle shadow `rgba(0,0,0,0.35)` with 16px blur + 1px subtle border on cards.
  - `Level 2`: Hover elevation with 24px blur and slight accent border illumination.
  - `Level 3`: Accent glow for primary CTA: `BoxShadow(color: rgba(205,255,100,0.4), blurRadius: 14)`.

## Iconography & Assets

- Icon family: Material Rounded & Outlined icons. Consistent stroke weight (2.0) and optical centering.
- Icon sizes:
  - Micro / Inline: 14px - 16px
  - Standard / Button: 18px - 20px
  - Featured / CTA: 22px - 24px
- Meaningful icons always have associated text or `Semantics` accessible labels.
- Zero non-functional emojis in production UI.

## Motion & Interaction

- Micro-interactions (hover, active press): `150ms` using `easeOutCubic`.
- Panel reveals and tab switches: `250ms` using `easeInOutCubic`.
- Route / Page transitions: `400ms` using `cubic-bezier(0.2, 0.0, 0.0, 1.0)`.
- Respect `prefers-reduced-motion`: When reduced motion is preferred, transitions degrade instantly (`0ms`).

## Fitts's Law Ergonomic Rules

1. **Primary Action ("Start Live Trading")**: Sized at height 50px with prominent width and high-luminance lime accent, positioned in direct line of sight within the right control stack.
2. **Critical Destructive Action ("Emergency Kill-Switch")**: Explicitly separated from standard actions with distinctive outlined border styling, requiring deliberate cursor targeting to prevent accidental triggering.
3. **Instrument Selector Chips**: Minimum 44px clickable height with 12px internal padding and clear focus/selection states.
4. **Navigation Tabs**: Minimum 40px hit height with generous touch target bounds.

## Breakpoints

- Mobile Compact: 375px – 428px (Single column stacked layout)
- Tablet / Small Laptop: 768px – 1024px (Vertical split workspace)
- Desktop Terminal: 1280px – 1920px (7:3 asymmetric dual-column grid)
- Minimum Touch Target: ≥ 44×44px on touch platforms; ≥ 36×36px with optical padding on desktop pointer platforms.
