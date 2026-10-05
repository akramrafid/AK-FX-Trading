# Component & Token Traceability

Every P0 route maps to a screen spec, composition, reusable components, and
the tokens those components consume. This is the bridge between design intent
and code review.

| Route / screen | Screen spec | Composition | Components | Tokens / page override | Browser evidence |
|---|---|---|---|---|---|
| `/` | `docs/design/dashboard-screen-spec.md` | Asymmetric 7:3 Grid | `HeaderNav`, `MarketChips`, `TradingChart`, `TransactionsTable`, `AccountCard`, `RiskMeterCard`, `GlassCard` | `--color-bg-primary`, `--color-bg-card`, `--color-primary-accent`, `--text-display`, `--mono-stat-lg`, `--mono-data`, `AppSpacing`, `AppRadius` | Windows native & Web verified |
| `/settings` | `docs/design/dashboard-screen-spec.md` | Centered Modal Dialog | `SettingsDialog`, `GlassCard` | `--color-bg-surface-elevated`, `--color-border-subtle`, `--text-lg`, `--mono-data` | Windows native & Web verified |

## New Pattern Decisions

| Pattern | Why it is needed | Master token/component update | Approval |
|---|---|---|---|
| Multi-segment Risk Meter | Real-time visual tracking of trades today, drawdown ceiling, and spread cap in one compact control | Added `AppColors.accentLime`, `AppColors.accentPurple`, `AppColors.accentCyan` segmented bar pattern | Approved by ui-designer |
| Monospace Tabular Figures | Prevents numerical jitter and misalignment during high-frequency forex broker ticks | Added `AppTypography.mono` with `FontFeature.tabularFigures()` | Approved by quant-architect |
| Frosted Acrylic Glass Container | Distinguishes elevated interactive workspace cards from root dark canvas | Implemented `GlassCard` with `BackdropFilter` and subtle 1px translucent border | Approved by ui-designer |

Rules:

- A page may compose existing components; it may not duplicate their tokens.
- A new visual pattern requires a Master update or documented page override.
- Every row has loading, empty, error, success, focus, disabled, and reduced-motion coverage.
