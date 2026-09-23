# {{PROJECT_NAME}} — Progress Journal

> Append-only. Never rewritten or trimmed. Read the most recent entries
> FIRST — they record what the environment actually is, which is not
> always what ToDos.md assumed when it was written.

## Task Completion Entry Format

```markdown
### {{YYYY-MM-DD HH:MM}} — <TASK-ID>: <title>
**Owner:** <agent-name>
**Changed:** <exact files modified>
**Verified:** <exact command run and its exit code 0 confirmation>
**Telemetry/Metrics:** <latency, bundle size, or test coverage impact if measured>
**Notes for next session:** <any context that saves the next session time>
**Status:** COMPLETED
```

## HANDOFF Entry (Human Intervention Required)

```markdown
### {{YYYY-MM-DD HH:MM}} — HANDOFF: <TASK-ID>
**Owner:** <agent-name>
**Blocked on:** <exact physical action, credential, or business decision required>
**Why the agent cannot proceed:** <credential / third-party dashboard approval / irreversible decision>
**STOP Signal:** Created `STOP` file in repo root.
**Work continued around it:** <none / details on non-dependent tasks executed>
```

## QUESTION Entry (Domain Ambiguity Escalation)

```markdown
### {{YYYY-MM-DD HH:MM}} — QUESTION: <TASK-ID>
**Owner:** <agent-name>
**The Ambiguity:** <what plan.md or ToDos.md left underspecified>
**Risk/Hard Rule at Stake:** <which domain rule or financial/data invariant is threatened>
**Options Considered:**
  1. Option A: <tradeoffs>
  2. Option B: <tradeoffs>
**Recommended Course:** <recommended option pending human sign-off>
```

## Gate Completion Entry (Gates G0-ML through G5)

```markdown
### {{YYYY-MM-DD HH:MM}} — GATE CLEARED: <GATE-ID>
**Reviewer:** <agent-name>
**Scope Reviewed:** <files or modules reviewed>
**Automated Check Result:** <test suite / linter / security scan / axe-core output summary>
**Evidence:** <workspace-relative report path(s), screenshot directory, or browser trace>
**Findings Summary:**
  - Critical: 0 open
  - High: 0 open
  - Medium/Low: <count filed or deferred>
**Status:** PASSED
```

## Phase Sign-Off Entry (Written at G6 Sign-off)

```markdown
### {{YYYY-MM-DD HH:MM}} — PHASE <N> SIGN-OFF COMPLETE
**Coordinator:** akstack
**Built:** <concise summary of shipped capabilities>
**Verification Summary:** <full regression test, lint, and build output summary>
**Known Gaps / Deferred:** <anything deferred to future phases with justification>
**Git Tag:** `phase-<N>-complete`
**Handoff to Phase <N+1>:** <essential context for the next phase's team>
```

---

<!-- Entries begin below this line. Append only. -->
