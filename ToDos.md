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

- [ ] **P1-T005** Comprehensive Test Suite for Rule Engine
  - **Owner:** senior-qa-architect
  - **Deps:** P1-T004
  - **Files:** tests/test_rule_engine.py
  - **Do:** Write exhaustive unit test suite testing Variant A/B bullish/bearish sweeps, 3-candle confirmation successes/failures, SL/TP mathematics for both directions, and edge cases (gap, incomplete bars, flat bars).
  - **Accept:** All tests pass cleanly with 100% coverage on rule engine logic.
  - **Verify:** python -m unittest tests.test_rule_engine -v

- [ ] **P1-G1** Phase 1 Rule Engine Verification Gate
  - **Owner:** coordinator
  - **Deps:** P1-T005
  - **Files:** docs/qa/phase1-report.md
  - **Do:** Execute full test suite, verify rule engine meets all Phase 1 specifications, and write Phase 1 verification report.
  - **Accept:** Complete report in docs/qa/phase1-report.md confirming zero intrabar leakage, exact 10:1 math, and passing tests.
  - **Verify:** python -m unittest tests.test_rule_engine -v

---

## Phase 2 — Architecture

Generate after Phase 1 sign-off (`PROMPT_LIBRARY.md` §3 / `phases/PHASE-2-ARCHITECTURE.md`). Do not invent Phase 2 tasks before Hard Rules are approved.

**Required owners:** `senior-system-architect` ★, `senior-system-designer`, `senior-database-architect` ★, `senior-security-engineer` ★, `senior-privacy-engineer` ★, `senior-sre-observability-engineer` ★, `senior-cloud-architect`, `senior-technical-writer`, `senior-ai-engineer` ★ (AI/ML & Hybrid only).

---

## Phase 3 — Design

Generate after architecture sign-off (`phases/PHASE-3-DESIGN.md`). Persist `design-system/MASTER.md` before any frontend/mobile coding.

For Product/Web and Hybrid, Phase 3 must include tasks owned by `senior-product-designer`, `ui-designer`, `design-system-engineer`, `content-designer`, `growth-cro-engineer`, `product-analytics-engineer`, `technical-seo-engineer`, and `senior-accessibility-engineer`. Screen tasks use `templates/screen-spec.template.md`; do not start frontend implementation with a placeholder Master or unapproved screen spec.

End Phase 3 with `P3-G1` HUMAN design sign-off. It must approve the resolved `design-system/MASTER.md`, screen-spec set, measurement plan, technical SEO contract, and accessibility spec before any Product/Web or Hybrid Phase 4 task may start.

---

## Phase 4 — Build

Generate after design sign-off (`phases/PHASE-4-BUILD.md`). Every task must have Owner, Files, Accept, and a Verify command that exits 0.

---

## Phase 5 — Quality & Security

Generate after build complete. Gate IDs must be parseable: `P5-G0-ML`, `P5-G1`, `P5-G2`, `P5-G3`, `P5-G3-P`, `P5-G4`, `P5-G4-CRO`, `P5-G4-A11Y`, `P5-G5`, `P5-G6`.

---

## Phase 6 — DevOps & Launch

Generate after G6 of Phase 5 (`phases/PHASE-6-DEVOPS-LAUNCH.md`).
