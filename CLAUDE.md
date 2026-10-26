# CLAUDE.md

Instructions for this repository. The rules themselves live in the files
imported below — this file exists so Claude Code loads them, and must not
restate their content.

## Always loaded

@AGENTS.md
@GLOBAL-RULES.md
@plan.md

`plan.md` is imported because `GLOBAL-RULES.md` §2 delegates this project's
Domain Hard Rules to `plan.md` §3, and requires every agent to enforce them
regardless of role. §3 governs live-money execution — closed candles only
(zero look-ahead), the non-bypassable risk guardrails layer, dynamic position
sizing with hard clamps, and order idempotency. Treat any conflict with §3 as
stop-and-ask, never a judgment call.

## Read on demand, not imported

- `ToDos.md` — task ledger; §0 defines HANDOFF / QUESTION escalation
- `PROMPT_LIBRARY.md` — role prompt reference; §5 covers escalation
- `PROGRESS.md` — append-only run log
- `GETTING-STARTED.md` — setup

These churn or are reference-only. Open them when a task needs them; do not
import them here.
