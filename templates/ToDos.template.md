# {{PROJECT_NAME}} — Task Ledger

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

## Phase 1 — Discovery

**Exit Criteria:** Structured capability map + user personas + PRD + non-goals + open questions logged. Human has approved `plan.md` §1-2 and §8-9.

- [ ] **P1-T001** Produce structured capability map
  - **Owner:** requirement-analyzer
  - **Deps:** —
  - **Files:** `plan.md`, `docs/discovery/capabilities.md`
  - **Do:** Analyze the raw requirement. Separate explicitly asked / domain-implied / assumed. Draft `plan.md` §1-2 capability map, SEO scope if public-facing, and technical constraints. Do not choose a stack.
  - **Accept:** `plan.md` §1-2 populated; every assumption labeled; ambiguities listed for §9.
  - **Verify:** manual review

- [ ] **P1-T002** Write PRD, prioritized stories, and non-goals
  - **Owner:** senior-product-manager
  - **Deps:** P1-T001
  - **Files:** `plan.md`, `docs/prd.md`
  - **Do:** Produce a PRD with ruthlessly prioritized user stories (each with a so-that). Fill `plan.md` §8 Non-Goals. Nothing is P0 by default.
  - **Accept:** Stories are independently buildable; non-goals defend against scope creep.
  - **Verify:** manual review

- [ ] **P1-T003** Personas, journeys, and task flows
  - **Owner:** ux-researcher
  - **Deps:** P1-T001
  - **Files:** `docs/discovery/personas.md`, `docs/discovery/journeys.md`
  - **Do:** Write behavioral personas and end-to-end journeys including pre/post product touchpoints. Flag any core action that takes more than a few steps.
  - **Accept:** At least one primary and one secondary persona; journeys cover the PRD's P0 stories.
  - **Verify:** manual review

- [ ] **P1-T004** Competitor interaction-pattern analysis
  - **Owner:** design-researcher
  - **Deps:** P1-T001
  - **Files:** `docs/discovery/competitors.md`
  - **Do:** Analyze named comparables' core flows. Recommend patterns to adopt or reject. Interaction patterns only — not visual identity.
  - **Accept:** Each finding names a specific product and flow, plus a recommendation.
  - **Verify:** manual review

- [ ] **P1-T005** Visual moodboard and anti-patterns
  - **Owner:** pinterest-researcher
  - **Deps:** P1-T001
  - **Files:** `docs/discovery/moodboard.md`
  - **Do:** Direction for color, typography mood, imagery, and explicit category anti-patterns. Do not pick a final palette.
  - **Accept:** Direction is reasoned against the product category and brand personality.
  - **Verify:** manual review

- [ ] **P1-T006** Synthesize open questions and conversion copy outline
  - **Owner:** content-designer
  - **Deps:** P1-T002, P1-T003
  - **Files:** `plan.md`, `docs/discovery/copy-outline.md`
  - **Do:** Draft conversion-critical microcopy outline (onboarding, empty states, errors, CTAs) and push remaining ambiguities into `plan.md` §9.
  - **Accept:** `plan.md` §9 lists every genuine ambiguity with the assumption made; copy outline covers P0 flows.
  - **Verify:** manual review

- [ ] **P1-T007** Define funnel, north-star metric, and ethical CRO guardrails
  - **Owner:** growth-cro-engineer
  - **Deps:** P1-T002, P1-T003
  - **Files:** `docs/discovery/funnel.md`, `docs/discovery/experiment-principles.md`
  - **Do:** Map acquisition, signup, activation, core value, retention, and monetization. Define one north-star outcome, guardrails, and conversion hypotheses without dark patterns.
  - **Accept:** Every P0 journey has a measurable activation outcome and a trustworthy primary action.
  - **Verify:** manual review

- [ ] **P1-T008** Create privacy-aware product measurement plan
  - **Owner:** product-analytics-engineer
  - **Deps:** P1-T002, P1-T003
  - **Files:** `docs/analytics/measurement-plan.md`
  - **Do:** Define versioned funnel events, non-sensitive properties, consent behavior, attribution, experiment exposure, deduplication, and quality checks.
  - **Accept:** Every event supports a named product decision; no raw PII is collected by default.
  - **Verify:** manual review

- [ ] **P1-T009** Define public route and technical SEO contract
  - **Owner:** technical-seo-engineer
  - **Deps:** P1-T002
  - **Files:** `docs/seo/technical-seo.md`
  - **Do:** Map public routes to search intent, rendering, title/description, H1, canonical, indexability, structured data, social preview, and conversion goal.
  - **Accept:** Every public route has an explicit indexability decision and truthful search-to-value path.
  - **Verify:** manual review

- [ ] **P1-G1** 🧑 HUMAN Approve discovery plan
  - **Owner:** coordinator
  - **Deps:** P1-T002, P1-T003, P1-T004, P1-T005, P1-T006, P1-T007, P1-T008, P1-T009
  - **Files:** `plan.md`
  - **Do:** Human stakeholder reads and approves `plan.md` §1-2 and §8-9. Coordinator records the decision.
  - **Accept:** Written approval in PROGRESS.md. No hidden ambiguities remain.
  - **Verify:** manual review

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
