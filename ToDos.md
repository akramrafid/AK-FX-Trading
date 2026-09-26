# AK Forex Trading — Task Ledger

## §0. Operating Contract

Read in full before every work session — no assumed memory of any prior session. `PROGRESS.md` is the only continuity. Use the `akstack` CLI (`python -m orchestrator.cli`) for deterministic task management.

1. **Orient**: Run `akstack status` or read `plan.md`, this file, `agents/TEAM.md`, `PROGRESS.md` (newest entries first).
2. **Select**: Run `akstack next` (or `akstack packet` for a machine-readable execution packet).
3. **🧑 HUMAN Task**: If blocked on a person, run `akstack handoff <id> --blocked-on "..." --why "..."`, which writes PROGRESS.md and creates `STOP`. After an explicit decision, run `akstack approve <id> --notes "..." --evidence <report>`.
4. **Gate Task (`-G`)**: Follow `phases/PHASE-5-QUALITY-SECURITY.md`. File findings with `akstack finding`. Never self-fix in review-only gates. Every gate needs a report file passed to `akstack gate --evidence`.
5. **Implement**:
   - Run `akstack start <task-id>` (marks `- [~]`).
   - Read `agents/<owner>.md` before editing.
   - Touch ONLY the paths specified in `Files:`.
   - Adhere to Hard Rules in `plan.md` §3 and standing rules in `agents/TEAM.md` §4.
6. **Verify**: Run `Verify:` command. Must exit 0.
7. **Complete**: Run `akstack complete <task-id>` (verify, journal, commit).
8. **Failure**: Up to 3 retries. Then `akstack fail <task-id> --error "<diagnosis>"`. Reset with `akstack reset <task-id>` after the fix.

**Reality beats the ledger.** Where `PROGRESS.md` shows the actual repository state differs from what a task assumed, follow `PROGRESS.md`, do the task's intent, and correct the ledger.

**Genuinely ambiguous + costly to reverse → `akstack question`, never a silent guess.**

### §0.1 Task ID Scheme

- `P<phase>-T<nnn>`: Standard implementation task.
- `P<phase>-G<n>` or `P<phase>-G<n>-SUFFIX`: Quality, security, or release gate (`P5-G4-A11Y`, `P5-G0-ML`).
- `P<phase>-F<nn>`: Gate finding fix (filed directly below failing gate).
- `P<phase>-C<nn>`: Cross-cutting requirement change request.

### §0.2 Task Format

```markdown
- [ ] **P<N>-T<NNN>** {{★ if architect-tier}} <title>
  - **Owner:** <agent from agents/TEAM.md>
  - **Deps:** <comma-separated task IDs, or —>
  - **Files:** <comma-separated exact paths>
  - **Do:** <specific instruction>
  - **Accept:** <observable done-condition>
  - **Verify:** `<exact shell command exiting 0>`
```

Small tasks beat large ones — if `Do:` requires more than a short paragraph, split it.

### §0.3 ★ Senior Tasks

Schema, core domain logic implementing a Hard Rule, security/auth internals, architectural topology, novel algorithm validation, and privacy threat models are ★ Senior. They MUST execute on the flagship model tier. See `agents/TEAM.md` §2.

### §0.4 Gate Sequence (Phase 5 Quality & Security)

| Gate | Owner | Reviews for | Mode |
|---|---|---|---|
| **G0-ML** *(AI/ML track)* | `senior-mlops-engineer` | Model lineage, reproducible training, eval threshold cleared | Implement |
| **G1 Test** | `senior-qa-architect` | Automated test suite 100% green, Hard Rules tested first | Implement (tests only) |
| **G2 Code Review** | `code-reviewer` | Clean architecture, error handling, maintainability, ownership | Review-only |
| **G3 Security** | `senior-security-engineer` | OWASP Top 10 + ASVS, auth boundaries, Hard Rules | Review-only |
| **G3-P Privacy** | `senior-privacy-engineer` | Data minimization, lawful basis, retention, DPIA | Review-only |
| **G4 UX/Visual** | `visual-qa` | Pixel/breakpoint fidelity, Impeccable critique | Review-only |
| **G4-CRO** | `growth-cro-engineer` + `product-analytics-engineer` | Funnel clarity, truthful value/price, consent-aware events, SEO | Review-only |
| **G4-A11Y Accessibility** | `senior-accessibility-engineer` | WCAG 2.2 AA, keyboard, screen readers | Review-only |
| **G5 Performance** | `senior-performance-engineer` | Core Web Vitals, Lighthouse CI, API latency | Review-only |
| **G6 Sign-off** | `coordinator` | All gates `- [x]`, tag `phase-<N>-complete` | Sign-off |

Each review-only gate files Critical/High findings as new `-F` tasks and stays unchecked until none remain open — reviewers NEVER edit production code.

---

## Phase 1 — Deterministic Rule Engine

**Exit Criteria:** A pure Python module taking closed OHLC candles, detecting Variant A/B sweeps, confirming 3-candle directional continuation, and outputting entry/SL/TP with 10:1 R:R. 100% green unit test suite.

- [x] **P1-T001** Implement OHLC Candle & Signal Data Structures
  - **Owner:** senior-backend-engineer
  - **Deps:** —
  - **Files:** engine/__init__.py, engine/models.py
  - **Do:** Define Candle, TradeSignal, SweepEvent, and Direction dataclasses/TypedDicts. Implement integrity validation (chronological timestamps, high >= low, high >= open, high >= close, low <= open, low <= close).
  - **Accept:** Robust, typed candle and signal data models with validation and serialization.
  - **Verify:** python -c "import engine.models"

- [x] **P1-T002** Implement Liquidity Sweep Detectors (Variant A & Variant B)
  - **Owner:** senior-backend-engineer
  - **Deps:** P1-T001
  - **Files:** engine/sweep_detector.py
  - **Do:** Implement Variant A (candle-to-candle sweep of prior opposite-colored candle's wick/body) and Variant B (swing-level sweep across recent swing highs/lows over configurable lookback). Evaluate closed candles only.
  - **Accept:** Accurate detection of bullish and bearish sweeps without future look-ahead.
  - **Verify:** python -c "import engine.sweep_detector"

- [x] **P1-T003** Implement 3-Candle Confirmation & 10:1 R:R Calculator
  - **Owner:** senior-backend-engineer
  - **Deps:** P1-T001
  - **Files:** engine/confirmation.py
  - **Do:** Implement 3-consecutive-candle directional confirmation test (all 3 candles closing green for long, red for short). Calculate Entry at candle 3 close, Stop-Loss beyond candle 1 extreme (accounting for spread/buffer on shorts), and Take-Profit at 10x risk distance. Discard on broken sequence.
  - **Accept:** Exact confirmation evaluation and mathematical 10:1 R:R calculation.
  - **Verify:** python -c "import engine.confirmation"

- [x] **P1-T004** ★ Consolidated Core Rule Engine
  - **Owner:** senior-system-architect
  - **Deps:** P1-T001, P1-T002, P1-T003
  - **Files:** engine/rule_engine.py
  - **Do:** Assemble the unified RuleEngine class/function taking closed OHLC candles and returning None or TradeSignal. Walks closed bars chronologically, manages sweep state transitions, verifies confirmations, and outputs trade parameters. Zero ML/RL dependencies.
  - **Accept:** Rule engine strictly operates on closed candles; returns TradeSignal matching all specification rules.
  - **Verify:** python -c "import engine.rule_engine"

- [x] **P1-T005** Comprehensive Test Suite for Rule Engine
  - **Owner:** senior-qa-architect
  - **Deps:** P1-T004
  - **Files:** tests/test_rule_engine.py
  - **Do:** Write exhaustive unit test suite testing Variant A/B bullish/bearish sweeps, 3-candle confirmation successes/failures, SL/TP mathematics for both directions, and edge cases (gap, incomplete bars, flat bars).
  - **Accept:** All tests pass cleanly with 100% coverage on rule engine logic.
  - **Verify:** python tests/test_rule_engine.py

- [x] **P1-G1** Phase 1 Rule Engine Verification Gate
  - **Owner:** coordinator
  - **Deps:** P1-T005
  - **Files:** docs/qa/phase1-report.md
  - **Do:** Execute full test suite, verify rule engine meets all Phase 1 specifications, and write Phase 1 verification report.
  - **Accept:** Complete report in docs/qa/phase1-report.md confirming zero intrabar leakage, exact 10:1 math, and passing tests.
  - **Verify:** python tests/test_rule_engine.py

---

## Phase 2 — Architecture & Backtesting

- [x] **P2-T001** Historical Data Ingestion Pipeline
  - **Owner:** senior-data-engineer
  - **Deps:** P1-G1
  - **Files:** data/loader.py
  - **Do:** Implement historical OHLCV data loader supporting Dukascopy and MT4 CSV formats, timestamp validation, timezone conversion to UTC, missing candle detection, and candle generation into Candle models.
  - **Accept:** Loads and normalizes historical CSV into sorted, validated Candle sequence.
  - **Verify:** python -c "import data.loader"

- [x] **P2-T002** Event-Driven Backtest Simulator
  - **Owner:** senior-backend-engineer
  - **Deps:** P2-T001
  - **Files:** engine/backtester.py
  - **Do:** Implement event-driven backtesting engine iterating over closed M5 candles using the exact RuleEngine from Phase 1. Incorporate bid/ask spread modeling, slippage simulation (in pips), dynamic lot sizing calculation, position lifecycle tracking, and trade outcome accounting.
  - **Accept:** Zero lookahead bias; accurate fill simulation at next candle open or immediate close timestamp; exact PnL and R-multiple tracking.
  - **Verify:** python -c "import engine.backtester"

- [x] **P2-T003** Performance & Risk Metrics Calculator
  - **Owner:** senior-backend-engineer
  - **Deps:** P2-T002
  - **Files:** engine/metrics.py
  - **Do:** Implement quantitative metrics calculator computing total trades, win rate %, average R-multiple, profit factor, maximum equity drawdown (% and currency), maximum consecutive losses, Sharpe ratio, and trade duration stats.
  - **Accept:** Exact formula computations matching standard financial reporting.
  - **Verify:** python -c "import engine.metrics"

- [x] **P2-T004** ★ PostgreSQL Schema & Trade Journal Data Layer
  - **Owner:** senior-database-architect
  - **Deps:** P1-G1
  - **Files:** database/schema.sql
  - **Do:** Design PostgreSQL DDL schema for trading system: candles, sweep_events, trade_signals, orders, fills, daily_metrics, and audit logs. Define constraints, foreign keys, timestamps with timezone, and composite indexes on (symbol, timeframe, timestamp).
  - **Accept:** Clean SQL schema adhering to financial precision invariants (numeric/decimal types for prices/lots, no floating point for money).
  - **Verify:** python -c "open('database/schema.sql').read()"

- [x] **P2-T005** Backtester Verification Test Suite
  - **Owner:** senior-qa-architect
  - **Deps:** P2-T002, P2-T003, P2-T004
  - **Files:** tests/test_backtester.py
  - **Do:** Implement comprehensive unit and integration test suite for the data loader, backtester engine, spread/slippage modeling, and metrics engine with synthetic multi-month market cycles.
  - **Accept:** 100% green test suite validating backtesting mechanics and metrics computation.
  - **Verify:** python tests/test_backtester.py

- [x] **P2-G1** Phase 2 Architecture & Backtest Verification Gate
  - **Owner:** coordinator
  - **Deps:** P2-T005
  - **Files:** docs/qa/phase2-report.md
  - **Do:** Execute full backtest suite, generate performance metrics on multi-year sample data, verify risk metrics, and document backtest findings and system architecture in docs/qa/phase2-report.md.
  - **Accept:** Comprehensive Phase 2 verification report detailing win rate, average R, max drawdown, and strategy viability.
  - **Verify:** python tests/test_backtester.py

---

## Phase 3 — MT4 Execution Bridge

- [x] **P3-T001** DWX Connect Protocol & Command Handler
  - **Owner:** senior-integration-engineer
  - **Deps:** P2-G1
  - **Files:** bridge/dwx_client.py, bridge/__init__.py
  - **Do:** Implement DWX Connect file-based client protocol. Reads bar data files written by MT4 EA, formats execution commands (OPEN, MODIFY, CLOSE) to command files, reads trade execution reports, and tracks open orders.
  - **Accept:** Clean read/write file protocol with atomic file locking and error handling.
  - **Verify:** python -c "import bridge.dwx_client"

- [x] **P3-T002** Dynamic Position Sizing & Currency Pip Value Engine
  - **Owner:** senior-backend-engineer
  - **Deps:** P3-T001
  - **Files:** bridge/sizing.py
  - **Do:** Implement precision dynamic position sizing with quote currency exchange rate awareness for major/cross pairs (EUR/USD, GBP/USD, USD/JPY, EUR/JPY, AUD/USD). Implements hard bounds (0.01 lot min, 50.0 lot max) and accounts for quote currency pip value.
  - **Accept:** Exact lot size computation compliant with Hard Rule 3.
  - **Verify:** python -c "import bridge.sizing"

- [x] **P3-T003** MT4 Bar Poller & Signal Execution Bridge
  - **Owner:** senior-integration-engineer
  - **Deps:** P3-T001, P3-T002
  - **Files:** bridge/executor.py
  - **Do:** Build the unified bridge runner that watches the MT4 incoming candle file, passes closed bars to RuleEngine, computes position sizing on signal, and writes idempotent order commands with deterministic magic numbers.
  - **Accept:** Closed-bar event loop triggering orders on confirmed 3-candle breakouts.
  - **Verify:** python -c "import bridge.executor"

- [x] **P3-T004** MQL4 Expert Advisor Specification & Script
  - **Owner:** senior-integration-engineer
  - **Deps:** P3-T001
  - **Files:** bridge/mql4/DWX_AutoTrader.mq4
  - **Do:** Provide the complete, production-grade MQL4 Expert Advisor designed to attach to MT4 charts. On new bar (time change), writes closed OHLC to DWX bar file, polls DWX command file, executes market orders with slippage tolerance and magic number, and logs fills.
  - **Accept:** Valid MQL4 source script ready for MT4 MetaEditor compilation.
  - **Verify:** python -c "open('bridge/mql4/DWX_AutoTrader.mq4').read()"

- [x] **P3-T005** Bridge & Execution Simulation Test Suite
  - **Owner:** senior-qa-architect
  - **Deps:** P3-T003, P3-T004
  - **Files:** tests/test_bridge.py, bridge/dwx_client.py, bridge/executor.py, bridge/sizing.py
  - **Do:** Write end-to-end integration tests for DWX file protocol, mock MT4 bar generation, command writing, idempotency checking, and error recovery on locked/malformed files.
  - **Accept:** 100% green test suite validating live bridge pipeline.
  - **Verify:** python tests/test_bridge.py

- [x] **P3-G1** Phase 3 Bridge Verification Gate
  - **Owner:** coordinator
  - **Deps:** P3-T005
  - **Files:** docs/qa/phase3-report.md
  - **Do:** Run bridge test suite, verify file protocol roundtrip, validate position sizing edge cases, and compile Phase 3 gate report.
  - **Accept:** Comprehensive Phase 3 verification report confirming MT4 EA readiness, atomic command protocol, and passing tests.
  - **Verify:** python tests/test_bridge.py

---

## Phase 4 — Non-Bypassable Risk Guardrails & Circuit Breakers

- [x] **P4-T001** Risk State & Invariant Models
  - **Owner:** senior-backend-engineer
  - **Deps:** P3-G1
  - **Files:** risk/models.py, risk/__init__.py
  - **Do:** Define immutable data models for AccountState, RiskLimits, TradeRejectionReason, DailyPnLTracker, and ValidationResult.
  - **Accept:** Strongly typed domain models for account balances, daily loss calculations, and trade constraints.
  - **Verify:** python -c "import risk.models"

- [x] **P4-T002** Non-Bypassable Risk Guardrails Engine
  - **Owner:** senior-backend-engineer
  - **Deps:** P4-T001
  - **Files:** risk/guardrails.py, risk/__init__.py
  - **Do:** Implement standalone RiskGuardrails with non-bypassable validate_trade() evaluating daily loss limits (3.0%), max open trades (default 1), max daily trades (default 3), spread ceiling (default 2.5 pips), and session time filter (London/NY 07:00-17:00 UTC).
  - **Accept:** Every trade passed through mandatory validation; zero bypass allowed.
  - **Verify:** python -c "import risk.guardrails"

- [x] **P4-T003** Bridge & Risk Integration Pipeline
  - **Owner:** senior-integration-engineer
  - **Deps:** P4-T002
  - **Files:** bridge/executor.py
  - **Do:** Integrate RiskGuardrails directly into BridgeExecutor._execute_signal() preceding command dispatch. If rejected by risk, log rejection and prevent order submission.
  - **Accept:** Bridge rejecting trades whenever risk guardrails or circuit breakers trip.
  - **Verify:** python -c "import bridge.executor"

- [x] **P4-T004** Risk Guardrails & Circuit Breaker Test Suite
  - **Owner:** senior-qa-architect
  - **Deps:** P4-T002, P4-T003
  - **Files:** tests/test_risk.py
  - **Do:** Author comprehensive test suite testing daily loss halt, max open trades, max daily trades, spread filter, session window filter, and emergency halt.
  - **Accept:** 100% green test suite verifying complete risk containment.
  - **Verify:** python tests/test_risk.py

- [x] **P4-G1** Phase 4 Risk Guardrails Verification Gate
  - **Owner:** coordinator
  - **Deps:** P4-T004
  - **Files:** docs/qa/phase4-report.md
  - **Do:** Verify all risk guardrail tests, validate circuit breaker trip actions, and produce Phase 4 verification report.
  - **Accept:** Comprehensive Phase 4 verification report confirming zero bypassable routes and full risk containment.
  - **Verify:** python tests/test_risk.py

---

## Phase 5 — Quality & Security

**Exit Criteria:** All build code (Phases 1–4) passes comprehensive automated tests, code review, security audit, and performance validation. Zero critical/high findings open.

- [x] **P5-G1** Comprehensive Test Suite Verification
  - **Owner:** senior-qa-architect
  - **Deps:** P4-G1
  - **Files:** tests/test_rule_engine.py, tests/test_backtester.py, tests/test_bridge.py, tests/test_risk.py
  - **Do:** Run full regression suite. Verify all Hard Rules from plan.md §3 have explicit test coverage. Document coverage matrix mapping each Hard Rule to specific test(s).
  - **Accept:** 100% green test suite. Every Hard Rule (§3.1–§3.9) mapped to at least one test. Coverage report in docs/qa/phase5-g1-report.md.
  - **Verify:** python -m unittest discover -s tests -v

- [x] **P5-G2** Code Review — Architecture & Maintainability
  - **Owner:** code-reviewer
  - **Deps:** P5-G1
  - **Files:** docs/qa/phase5-g2-report.md
  - **Do:** Review all production code (engine/, bridge/, risk/, data/, database/) for clean architecture, error handling, naming, separation of concerns, type annotations. File findings as -F tasks. Review-only — do not edit production code.
  - **Accept:** Code review report in docs/qa/phase5-g2-report.md with zero critical/high findings open.
  - **Verify:** python -m unittest discover -s tests -v

- [x] **P5-G3** Security Audit
  - **Owner:** senior-security-engineer
  - **Deps:** P5-G1
  - **Files:** docs/qa/phase5-g3-report.md
  - **Do:** Audit for OWASP Top 10, file system injection in DWX file protocol, command injection via magic numbers, SQL injection potential in schema design, path traversal in data loader, and secret exposure. Review-only — do not edit production code.
  - **Accept:** Security audit report in docs/qa/phase5-g3-report.md with zero critical/high findings open.
  - **Verify:** python -m unittest discover -s tests -v

- [x] **P5-G5** Performance Validation
  - **Owner:** senior-performance-engineer
  - **Deps:** P5-G1
  - **Files:** docs/qa/phase5-g5-report.md
  - **Do:** Profile rule engine evaluation latency (target: <50ms per candle). Profile backtester throughput (target: >10,000 candles/sec). Profile DWX file write latency. Verify memory usage on multi-year backtests stays bounded. Document findings.
  - **Accept:** Performance report in docs/qa/phase5-g5-report.md confirming SLO compliance from plan.md §6.
  - **Verify:** python -m unittest discover -s tests -v

- [x] **P5-G6** Phase 5 Sign-Off
  - **Owner:** coordinator
  - **Deps:** P5-G1, P5-G2, P5-G3, P5-G5
  - **Files:** docs/qa/phase5-signoff.md
  - **Do:** Verify all prior gates passed with zero critical/high open. Run full regression. Tag `phase-5-complete`. Write sign-off report.
  - **Accept:** All gates P5-G1 through P5-G5 checked. Sign-off report in docs/qa/phase5-signoff.md.
  - **Verify:** python -m unittest discover -s tests -v

---

## Phase 6 — DevOps & Launch

**Exit Criteria:** Automated deployment harness, process supervisor watchdog, multi-channel alerting engine, production configuration, disaster recovery runbooks, and 100% green test suite.

- [x] **P6-T001** Process Supervisor & Health Watchdog
  - **Owner:** senior-devops-engineer
  - **Deps:** P5-G6
  - **Files:** bridge/watchdog.py
  - **Do:** Build process supervisor and health watchdog that monitors MT4 DWX file heartbeat, tracks memory footprint, logs health status, and triggers emergency halt if MT4 stops updating.
  - **Accept:** Standalone watchdog providing heartbeat tracking and graceful failure handling.
  - **Verify:** python -c "import bridge.watchdog"

- [x] **P6-T002** Alerts & Notifications Dispatcher
  - **Owner:** senior-sre-observability-engineer
  - **Deps:** P6-T001
  - **Files:** integrations/alerts.py, integrations/__init__.py
  - **Do:** Implement multi-channel alert dispatcher (Telegram Bot API, HTTP webhook, logging) wired to RiskGuardrails circuit breaker and DWX error callbacks.
  - **Accept:** Automated broadcasting of circuit breaker halts, emergency stops, and order execution events.
  - **Verify:** python -c "import integrations.alerts"

- [x] **P6-T003** Production Configuration & Launch Harness
  - **Owner:** senior-devops-engineer
  - **Deps:** P6-T001, P6-T002
  - **Files:** config.py, .env.example, scripts/run_bridge.bat, scripts/run_bridge.sh
  - **Do:** Create unified production configuration parser validating MT4 files directory, symbol settings, risk limits, and startup scripts for Windows VPS and Linux.
  - **Accept:** Fully validated configuration engine and cross-platform launcher scripts.
  - **Verify:** python -c "import config"

- [x] **P6-T004** Operations & Disaster Recovery Runbooks
  - **Owner:** senior-technical-writer
  - **Deps:** P6-T003
  - **Files:** docs/runbooks/operations.md, docs/runbooks/disaster-recovery.md
  - **Do:** Author operational manuals detailing MT4 terminal setup, DWX EA attachment, bridge startup, circuit breaker recovery, kill-switch engagement, and disaster recovery.
  - **Accept:** Comprehensive, unambiguous step-by-step production runbooks.
  - **Verify:** python -m unittest discover -s tests -v

- [x] **P6-T005** DevOps & Watchdog Test Suite
  - **Owner:** senior-qa-architect
  - **Deps:** P6-T001, P6-T002, P6-T003
  - **Files:** tests/test_devops.py
  - **Do:** Implement comprehensive unit and integration tests covering watchdog heartbeat detection, alert dispatching, configuration validation, and failure modes.
  - **Accept:** 100% green test suite verifying DevOps and supervision layer.
  - **Verify:** python tests/test_devops.py

- [x] **P6-G1** Phase 6 DevOps & Launch Verification Gate
  - **Owner:** coordinator
  - **Deps:** P6-T004, P6-T005
  - **Files:** docs/qa/phase6-report.md
  - **Do:** Verify all DevOps components, execute full test suite, validate production runbooks, and produce Phase 6 launch readiness report.
  - **Accept:** Full launch readiness verified with 100% green tests.
  - **Verify:** python -m unittest discover -s tests -v

---

## Phase 7 — Live Rollout Safeguards & Divergence Monitoring

**Exit Criteria:** Micro-lot initial deployment (0.01 lot) ladder, real-time multi-environment divergence monitoring (Win Rate, Slippage, Drawdown), automatic fail-safe lockdown, and 100% green test suite.

- [x] **P7-T001** Phased Sizing Ladder & Micro-Lot Deployment
  - **Owner:** senior-backend-engineer
  - **Deps:** P6-G1
  - **Files:** bridge/live_rollout.py
  - **Do:** Build LiveRolloutManager implementing progressive ScalingTier progression from Tier 1 (0.01 micro-lots for first 50 live trades) to Tier 4 (full size).
  - **Accept:** Micro-lot confinement for initial deployment and sample-gated scaling.
  - **Verify:** python -c "import bridge.live_rollout"

- [x] **P7-T002** Multi-Environment Divergence Monitor
  - **Owner:** senior-system-architect
  - **Deps:** P7-T001
  - **Files:** bridge/live_rollout.py
  - **Do:** Implement DivergenceMonitor evaluating win rate departure (>5%), median execution slippage (>1.5 pips), and drawdown divergence (>10%).
  - **Accept:** Automatic DIVERGENCE_HALT trigger and demotion to Tier 1 upon divergence trip.
  - **Verify:** python -c "import bridge.live_rollout"

- [x] **P7-T003** Live Rollout Test Suite & Verification Gate
  - **Owner:** senior-qa-architect
  - **Deps:** P7-T001, P7-T002
  - **Files:** tests/test_live_rollout.py, docs/qa/phase7-report.md
  - **Do:** Implement unit tests for scaling ladder, slippage limits, win-rate bounds, and divergence demotion.
  - **Accept:** 100% green test suite and Phase 7 report.
  - **Verify:** python -m unittest discover -s tests -p "test_live_rollout.py"

---

## Phase 8 — Post-Live ML/RL Regime Scoring & Dynamic Trade Management

**Exit Criteria:** Pure Python session regime confidence classifier, dynamic trade management policy (breakeven at +3R, trailing stop lock at +5R), strict non-bypassable risk invariant, and 100% green test suite.

- [x] **P8-T001** Trade Feature Extractor & Market Context Engine
  - **Owner:** senior-ai-engineer
  - **Deps:** P7-T003
  - **Files:** engine/ml_optimization.py
  - **Do:** Build TradeFeatureExtractor computing session hour, London/NY overlap, London open, sweep depth, risk pips, and timeframe.
  - **Accept:** Normalized feature vectors for machine learning inference.
  - **Verify:** python -c "import engine.ml_optimization"

- [x] **P8-T002** Pure Python Session Regime Confidence Model
  - **Owner:** senior-ai-engineer
  - **Deps:** P8-T001
  - **Files:** engine/ml_optimization.py
  - **Do:** Implement zero-dependency logistic regression classifier with mini-batch gradient descent trained directly on SQLite trade journal records.
  - **Accept:** Probability score P(Win|x) filtering low-probability breakout setups.
  - **Verify:** python -c "import engine.ml_optimization"

- [x] **P8-T003** Dynamic Trade Manager & Capital Protection Policy
  - **Owner:** senior-system-architect
  - **Deps:** P8-T002
  - **Files:** engine/ml_optimization.py
  - **Do:** Implement DynamicTradeManager policy moving stop loss to breakeven (+0.5 pip spread buffer) at +3R, and trailing stop to lock in +3R profit at +5R while holding for 10R TP.
  - **Accept:** Elimination of "winner-turned-loser" regret while preserving asymmetric 10:1 upside.
  - **Verify:** python -c "import engine.ml_optimization"

- [x] **P8-T004** Strict Non-Bypassable Risk Invariant & Pipeline Integration
  - **Owner:** senior-system-architect
  - **Deps:** P8-T002, P8-T003
  - **Files:** engine/ml_optimization.py, tests/test_ml_optimization.py, docs/qa/phase8-report.md
  - **Do:** Build validate_signal_with_ml_and_risk ensuring ML recommendations can prune signals but can never bypass or override RiskGuardrails. Implement comprehensive test suite.
  - **Accept:** 100% green tests and complete Phase 8 QA verification report.
  - **Verify:** python -m unittest discover -s tests -p "test_ml_optimization.py"

