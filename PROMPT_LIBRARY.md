# Prompt Library — akstack

Copy these verbatim or execute with the programmatic CLI (`python -m orchestrator.cli` / `bin/akstack`).
Substitute `{{PROJECT_NAME}}`, `{{N}}` (phase number), and the product requirement where indicated.

---

## 1. Bootstrap

Run once, at the start of a new project, after Phase 0 setup is complete (`phases/PHASE-0-SETUP.md`).

CLI Shortcut:
```bash
python -m orchestrator.cli init "{{PROJECT_NAME}}" --track Product/Web
```

Agent Prompt:
```
You are bootstrapping a new project with akstack. The files in this repo:
plan.md, ToDos.md, agents/TEAM.md, agents/<role>.md, PROGRESS.md.

Here is the product requirement in the person's own words:
"<PASTE THE PRODUCT REQUIREMENT HERE>"

STEP 1 — Track. Based on the requirement, is this Product/Web, AI/ML, or
Hybrid? State your read and confirm with the person before proceeding — this
decides which agents activate in Phase 4.

STEP 2 — Fill plan.md. Read requirement-analyzer.md and
senior-product-manager.md first, then work through the template:
  §0 Track — as confirmed above.
  §1-2 — restate the requirement precisely, no embellishment.
  §3 Domain & Hard Rules — this is the most important section in the whole
  system. Think hard: what invariant, if silently violated, would corrupt
  data or cause real harm in this specific domain? If you're not confident,
  ask rather than guess.
  §4-6 — propose stack/architecture appropriate to the requirement and
  track, flagging every assumption.
  §8 — non-goals.
  §9 — every genuine ambiguity as an open question. Do not resolve
  ambiguity by silently picking the likely interpretation when it would be
  expensive to reverse.

STEP 3 — Fill agents/TEAM.md §3 File Ownership for the actual chosen stack.

STEP 4 — Generate ToDos.md Phase 1 tasks only (per phases/PHASE-1-DISCOVERY.md),
including the funnel/CRO, analytics, and technical SEO tasks for Product/Web
and Hybrid tracks.
Use the task format in ToDos.md §0.2.

STEP 5 — Run `python -m orchestrator.cli lint` to verify structure.

STEP 6 — Report every open question and assumption. STOP here — do not
proceed to execution. A human reviews plan.md, especially §3, §8, and §9,
before anything else happens. Complete a HUMAN task with:
python -m orchestrator.cli approve <task-id> --notes "..." --evidence <report>
```

After approval, generate each subsequent phase's tasks one phase at a time (not all six up front) — later phases must reflect what earlier ones actually produced.

---

## 2. The Build Loop (Single Task)

Zero memory of the previous run — `ToDos.md` and `PROGRESS.md` are the only continuity, which is why every task ends in a commit.

CLI Shortcuts:
```bash
python -m orchestrator.cli doctor
python -m orchestrator.cli next
python -m orchestrator.cli packet
python -m orchestrator.cli start <task-id>
python -m orchestrator.cli complete <task-id>
```

Agent Prompt:
```
You are one iteration of the akstack build loop for {{PROJECT_NAME}}. You
have no memory of previous iterations. The repository is your only state.

STEP 1 — Orient. Run `python -m orchestrator.cli status` and read plan.md,
ToDos.md, agents/TEAM.md, PROGRESS.md (newest entries first).

STEP 2 — Select. Run `python -m orchestrator.cli next` to pick exactly one task.

STEP 3 — Build. Run `python -m orchestrator.cli start <task-id>`. Read the
role brief in agents/<owner>.md for the task's Owner before writing anything.
Touch only its Files: list. Apply every rule in agents/TEAM.md §4 and
GLOBAL-RULES.md without exception.

STEP 4 — Verify, record, complete. Run the task's Verify command. If the task
is UI-facing, run `python -m orchestrator.cli frontend-check --area all`, run a
real browser pass at the approved matrix, and attach evidence before marking
Accept satisfied. Impeccable is a useful supplement, not a substitute for
browser evidence.
If the task is ★, confirm you are the strongest model tier available.
Run `python -m orchestrator.cli complete <task-id>` to verify, record, and commit.

Print:
  COMPLETED: <task-id>
  NEXT: <next task-id>
```

---

## 3. Whole-Phase Run

CLI Shortcut:
```bash
# View runnable tasks partitioned into conflict-free parallel waves
python -m orchestrator.cli next --phase {{N}} --parallel
```

Agent Prompt:
```
Complete all remaining `- [ ]` tasks in PHASE {{N}} of {{PROJECT_NAME}},
per phases/PHASE-{{N}}-*.md, then run that phase's gate(s), then stop.

Repeat the Build Loop (§2) task by task in dependency order, re-reading
PROGRESS.md between tasks — your own last entry may contain context the
next task needs.

If multiple remaining tasks share no dependencies and their Files: lists
do not overlap at all, verify via `python -m orchestrator.cli next --parallel`
before parallel dispatch. Overlapping-file corruption from simultaneous
edits is the top failure mode of autonomous builds.

When every task in the phase is `- [x]`, run its gate(s) from §4 below in
order. Stop after the last gate and report: every task completed, anything a
human must do (check PROGRESS.md for HANDOFF entries), and the next phase's
first task.

For Phase 3 Product/Web or Hybrid work, do not start Phase 4 until `P3-G1`
HUMAN design sign-off approves the resolved Master, screen-spec set,
measurement plan, technical SEO contract, and accessibility spec.
```

---

## 4. Gate Prompts

Run applicable gates in this order: G0-ML (AI/ML and Hybrid), G1, G2, G3,
G3-P, G4, G4-CRO, G4-A11Y, G5, G6. Product/Web and Hybrid require the
frontend gates; AI/ML without a user-facing frontend may omit them.

### 4.0 AI/ML Model Eval gate (G0-ML — AI/ML track only, runs before G1)

```
You are senior-mlops-engineer for {{PROJECT_NAME}}. Read
agents/senior-mlops-engineer.md and plan.md §3, §5.

For every model artifact produced in Phase {{N}}: confirm it traces to a
versioned dataset and logged hyperparameters, and that its evaluation
metric clears the threshold plan.md requires.

For anything that doesn't clear this bar, file a new -F task into ToDos.md
directly below this gate, owned by the engineer who produced it. Leave the
gate unchecked until every model artifact in this phase is registered,
reproducible, and above threshold.
```

### 4.1 Test gate (G1)

```
You are senior-qa-architect for {{PROJECT_NAME}}. Read
agents/senior-qa-architect.md.

Phase {{N}} is code-complete. Write and run the tests that prove it.
Prioritize plan.md §3 Hard Rules first — that's where this project loses
the most if something breaks silently. Tests are deterministic: fixed
dates/IDs, seeded randomness, isolated setup/teardown.

Run the full suite. You write tests only — file any defect with a
reproduction for the owning engineer, never fix production code yourself.

Gate passes only when the suite is genuinely green (exit code 0). Capture the
output in `docs/qa/test-report.md`, then check it off:
python -m orchestrator.cli gate P{{N}}-G1 --evidence docs/qa/test-report.md
```

### 4.2 Code Review gate (G2)

```
You are code-reviewer for {{PROJECT_NAME}}. Read agents/code-reviewer.md,
agents/TEAM.md §3-4, and plan.md §3.

Review all code added in Phase {{N}} for production-grade quality: edge
cases beyond the happy path, error handling, maintainability, file-ownership
and Hard Rule compliance, test coverage adequacy, and documentation.

You are REVIEW-ONLY. You do not edit code.

For every finding:
  SEVERITY: Critical | High | Medium | Low
  FILE: path:line
  ISSUE: what is wrong
  IMPACT: why it matters in production
  FIX: specific remediation

For each Critical/High finding, file a new -F task into ToDos.md directly
below this gate, owned by whoever should fix it, in the standard task
format. Leave the gate unchecked until none remain open.
```

### 4.3b Privacy gate (G3-P)

```
You are senior-privacy-engineer (gate mode) for {{PROJECT_NAME}}. Read
agents/senior-privacy-engineer.md and plan.md §3.

Review all code added in Phase {{N}} for data minimization, purpose
limitation, PII in logs/prompts, retention, and subject-rights coverage.
You are REVIEW-ONLY.

File each Critical/High finding as a new -F task:
python -m orchestrator.cli finding P{{N}}-G3-P --title "..." --owner <agent> --severity High --file path --issue "..." --fix "..."

Leave the gate unchecked until none remain open. Capture the report in
`docs/qa/privacy-report.md`. If clean:
python -m orchestrator.cli gate P{{N}}-G3-P --evidence docs/qa/privacy-report.md
```

### 4.3 Security gate (G3)

```
You are senior-security-engineer (gate mode) for {{PROJECT_NAME}}. Read
agents/senior-security-engineer.md and plan.md §3.

Review all code added in Phase {{N}} against OWASP Top 10 + ASVS plus this
project's Hard Rules. You are REVIEW-ONLY.

For every finding: SEVERITY | FILE:line | ISSUE | EXPLOIT (concrete input/state) | FIX.
Report only what you can substantiate with a concrete failure scenario.

File each Critical/High finding as a new -F task below this gate. Leave it
unchecked until none remain open. Capture the report in
`docs/qa/security-report.md`. If clean, run:
python -m orchestrator.cli gate P{{N}}-G3 --evidence docs/qa/security-report.md
```

### 4.4 UX/Visual gate (G4)

```
Run visual-qa and brand-guardian together on what was actually built in
Phase {{N}} — not the design spec, the real shipped UI. Read
agents/visual-qa.md and agents/brand-guardian.md.

Check every target breakpoint from plan.md. Check against
design-system/MASTER.md for drift. If Impeccable is installed, run its
critique as part of this pass rather than duplicating checks by hand.

Both are REVIEW-ONLY. File findings with:
python -m orchestrator.cli finding P{{N}}-G4 --title "..." --owner senior-frontend-engineer --severity High --file path --issue "..." --fix "..."
When clean, attach `docs/qa/visual-report.md` and run:
python -m orchestrator.cli gate P{{N}}-G4 --evidence docs/qa/visual-report.md
```

### 4.4b Conversion, Analytics & SEO gate (G4-CRO)

```
You are growth-cro-engineer with product-analytics-engineer for
{{PROJECT_NAME}}. Read agents/growth-cro-engineer.md,
agents/product-analytics-engineer.md, agents/technical-seo-engineer.md,
docs/discovery/funnel.md, docs/analytics/measurement-plan.md, and
docs/seo/technical-seo.md.

Review the real built acquisition, signup, activation, pricing, and checkout
surfaces. Check that value, price, commitment, proof, primary CTA, consent,
and recovery are clear. Verify funnel events fire only for rendered actions,
contain no raw PII, respect consent, and support the stated product decision.
Verify public routes have truthful metadata, canonical/indexability, structured
data, sitemap/robots behavior, and meaningful server-rendered content.

This is REVIEW-ONLY. No dark patterns. File findings with `akstack finding`.
When clean, attach `docs/analytics/cro-report.md` and run:
python -m orchestrator.cli gate P{{N}}-G4-CRO --evidence docs/analytics/cro-report.md
```

### 4.5 Accessibility gate (G4-A11Y)

```
You are senior-accessibility-engineer for {{PROJECT_NAME}}. Read
agents/senior-accessibility-engineer.md.

Audit all screens and components added in Phase {{N}} against WCAG 2.2 AA:
- Keyboard navigation (focus visible, no focus traps, tab order).
- Color contrast >= 4.5:1 (>= 3:1 for large text/icons).
- Semantic HTML (proper heading hierarchy, landmarks, buttons vs links).
- ARIA labels and live regions for dynamic content.

You are REVIEW-ONLY. File findings as -F tasks. Capture automated and manual
evidence in `docs/qa/accessibility-report.md`. When compliant, run:
python -m orchestrator.cli gate P{{N}}-G4-A11Y --evidence docs/qa/accessibility-report.md
```

### 4.6 Performance gate (G5)

```
You are senior-performance-engineer for {{PROJECT_NAME}}. Read
agents/senior-performance-engineer.md.

Measure Core Web Vitals and API latency against plan.md's budget (or defaults:
LCP < 2.5s, INP < 200ms, CLS < 0.1, API P95 < 300ms). Trace any miss to its
specific cause.

REVIEW-ONLY. File findings as -F tasks. Capture numbers in
`docs/performance/report.md`. When budget is cleared:
python -m orchestrator.cli gate P{{N}}-G5 --evidence docs/performance/report.md
```

### 4.7 Sign-off gate (G6)

```
Phase {{N}} sign-off for {{PROJECT_NAME}}.
1. Confirm every task and every applicable gate in this phase is `- [x]`. A `- [!]`
   task means the phase is not done — stop and report it.
2. Run the full lint/test/build regression suite.
3. Re-read the phase's exit criteria in phases/PHASE-{{N}}-*.md and confirm
   each is genuinely met — demonstrate it, don't assume it.
4. Append a phase summary to PROGRESS.md.
5. Capture the sign-off in `docs/qa/release-signoff.md`.
6. python -m orchestrator.cli gate P{{N}}-G6 --evidence docs/qa/release-signoff.md
   (the CLI creates `phase-{{N}}-complete` after the gate passes)
```

---

## 5. Recovery Prompts

### 5.1 A task is blocked (`- [!]`)

```
ToDos.md has a task marked `- [!]`. Read PROGRESS.md for the recorded error.
Diagnose root cause rather than retrying blindly: under-specified? too large?
missing dependency? wrong Verify command?

Then either: (a) fix the problem and reset to `- [ ]`, (b) split it into smaller tasks,
(c) correct its Files:/Accept:/Verify: fields and reset, or (d) mark 🧑 HUMAN if it is
genuinely a human decision.

Record your reasoning in PROGRESS.md and commit.
```

### 5.2 The loop is stuck

```
No task has completed in several iterations. Run `python -m orchestrator.cli status`
and `python -m orchestrator.cli lint`. Diagnose: unmet dependencies, cyclic dependencies,
an orphaned `- [~]`, or a missed STOP file?

Fix root cause, record in PROGRESS.md, and report what changed.
```

### 5.3 Reverting a bad task

```bash
git log --oneline -10
git reset --hard <commit-before-the-bad-task>
```
Reset that task's checkbox to `- [ ]` in `ToDos.md` and re-run the loop.

---

## 6. Ad-Hoc Prompts

### 6.1 Status

```bash
python -m orchestrator.cli status
```

### 6.2 Re-plan a phase

```
Phase {{N}} has proven wrong in practice: <what went wrong>.
Re-plan only this phase, keeping the task format and ID scheme. Preserve
completed `- [x]` tasks. Explain what changed and why in PROGRESS.md. Do
not touch other phases. Run `python -m orchestrator.cli lint` after updating.
```

### 6.3 Cross-cutting change (including live system, post-Phase-6)

```
A requirement has changed: <the new requirement>.
1. Update plan.md — the relevant section, plus §9 if an assumption changed.
2. Identify every affected ToDos.md task. Completed ones get a new
   `- [ ] P<N>-C<nn>` change task; pending ones are edited in place.
3. If this touches a live system, pass through Phase 5 quality gates before
   re-shipping.
4. Run `python -m orchestrator.cli lint`.
5. Summarize impact in PROGRESS.md and commit.
```
