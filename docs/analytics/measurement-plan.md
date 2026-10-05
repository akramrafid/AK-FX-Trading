# Product Measurement Plan

## North-Star Outcome

- **North-star metric:** Profitable trading days with zero risk guardrail breaches.
- **Activation definition:** Successful bidirectional file synchronization between MT4 terminal and Python bridge within 1 second.
- **Revenue event:** Execution of winning TrendWise setup achieving 1:5 R:R target.
- **Retention window:** 30-day continuous algorithmic execution without manual drawdown intervention.
- **Guardrails:** Max daily loss (3.0%), Max daily trades (3 or unlimited in institutional mode), Max spread (2.5 pips).

## Funnel

| Stage | User intent | Event | Owner | Primary metric | Guardrail |
|---|---|---|---|---|---|
| Acquisition | Operator boots system | `app_launched` | devops | Startup success rate | Latency < 2s |
| Activation | Bridge connects to MT4 | `bridge_connected` | backend-architect | Heartbeat ping < 100ms | Zero file lock collision |
| Core value | Signal detected & trade opened | `trade_executed` | quant-analyst | R:R ratio ≥ 5.0 | Spread ≤ 2.5 pips |
| Retention | Risk guardrails protect capital | `daily_rollover` | risk-manager | Max drawdown < 3.0% | Circuit breaker readiness |

## Event Contract

Every event below lists trigger, actor, schema version, destination,
non-sensitive properties, retention, consent behavior, deduplication key, and
the product decision it supports.

| Event name | Trigger | Properties | Consent | Decision supported |
|---|---|---|---|---|
| `bridge_start` | User clicks Start Live Trading | `mode, timestamp, balance` | analytics | Track desk utilization |
| `order_placed` | Strategy confirms setup | `ticket, symbol, direction, lots` | analytics | Audit trade execution |
| `risk_halt` | Circuit breaker tripped | `reason, drawdown_pct, loss_usd` | analytics | Audit capital preservation |

Never send raw email, phone, message body, auth token, precise location, or
sensitive categories. All quantitative logging remains local in SQLite.

## Attribution

- Allowed campaign parameters: `utm_source, utm_medium, utm_campaign`
- Persistence window: Local session
- PII policy: Zero PII recorded or transmitted
- Server/client reconciliation: Local SQLite audit ledger

## Experiment Registry

| Experiment | Hypothesis | Audience | Variants | Primary metric | Guardrails | Stop/rollback |
|---|---|---|---|---|---|---|
| `exp_rr_1to5` | 1:5 R:R target with Breakeven at 2R maximizes expectancy | All MT4 live pairs | Base 1:3 vs Institutional 1:5 | Net Profit Expectancy | Max Drawdown 3% | Instant rollback via SettingsDialog |

## Quality Checks

- [x] Consent is respected before the first event and after revocation.
- [x] Duplicate events are rejected or deduplicated.
- [x] Invalid payloads are visible in monitoring.
- [x] Exposure is emitted only when the variant rendered.
- [x] `product-analytics-engineer` reviewed the event catalog.
