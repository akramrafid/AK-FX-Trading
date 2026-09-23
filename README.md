# Akram's Production System (akstack)

Akram's personal production multi-agent system. Clone this into any new project, feed it a product requirement, and it runs a disciplined, autonomous engineering pipeline: architecture, database modeling, backend, integrations, frontend, mobile, UI/UX, AI/ML, SQA, accessibility, SRE, and DevOps.

## The Core Philosophy

Most AI-assisted builds fall apart because context scrolls away in an LLM conversation. `akstack` persists state deterministically on disk:
- `plan.md` (what/why/domain hard rules/SLO budgets),
- `ToDos.md` (the machine-parsable task ledger),
- `PROGRESS.md` (the append-only journal),
- `agents/` (42 role briefs, each with narrow responsibilities, explicit boundaries, and clean handoffs),
- `orchestrator/` & `bin/akstack` (zero-dependency programmatic CLI for topological sorting, conflict-free parallel wave scheduling, task transitions, and automated gating).

Every work session — whether minutes later or three weeks later — orients from disk. This makes multi-week autonomous builds immune to context resets, model switches, and long operational gaps.

## Frontend Quality Contract

Product/Web and Hybrid projects do not treat visual quality as a subjective final polish. The pipeline requires:

- A product-specific visual thesis and signature moment, persisted in `design-system/MASTER.md`.
- Screen specs with real copy, responsive compositions, state coverage, accessibility, instrumentation, and SEO metadata.
- A token-driven component system with route/screen/component traceability.
- An ethical acquisition-to-retention funnel, consent-aware analytics, and technical SEO route matrix.
- Browser evidence at 320, 375, 768, 1024, 1280, and 1440px plus dark mode, reduced motion, keyboard, long content, landscape, and zoom/reflow.
- A dedicated G4-CRO gate before accessibility and performance sign-off.

Run `python -m orchestrator.cli frontend-check --area all` before Phase 5. A beautiful screenshot without evidence, accessibility, discoverability, or measurable user value is not a passing frontend.

---

## Three Tracks, One Spine

Every project runs the same 7 phases (0 through 6). The active agents in Phase 4 (Build) depend on the project track declared in `plan.md` §0:

| Track | Target Applications | Active Phase 4 Implementation Agents |
|---|---|---|
| **Product/Web** | SaaS, CRUD apps, web portals, dashboards, mobile apps | `senior-backend-engineer`, `senior-frontend-engineer`, `senior-integration-engineer`, `senior-mobile-engineer` |
| **AI/ML** | Novel models, research pipelines, classical ML, LLM systems, vision/NLP | `senior-ai-research-engineer` (★), `senior-machine-learning-engineer`, `senior-deep-learning-engineer`, `senior-llm-engineer`, `senior-generative-ai-engineer`, `senior-nlp-engineer`, `senior-computer-vision-engineer`, `senior-data-engineer` |
| **Hybrid** | Full-stack products with embedded AI/LLM features | Both groups, operating on isolated files via `agents/TEAM.md` file ownership boundaries |

---

## Programmatic CLI Orchestrator (`bin/akstack`)

Akram-Stack includes a zero-dependency Python 3 CLI engine for automated task scheduling and gating:

```bash
python -m orchestrator.cli doctor
python -m orchestrator.cli status --json
python -m orchestrator.cli next --parallel
python -m orchestrator.cli packet
python -m orchestrator.cli start <task-id>
python -m orchestrator.cli complete <task-id>
python -m orchestrator.cli fail <task-id> --error "<diagnosis>"
python -m orchestrator.cli reset <task-id>
python -m orchestrator.cli approve <human-task-id> --notes "..." --evidence docs/approval.md
python -m orchestrator.cli resume --notes "handoff resolved"
python -m orchestrator.cli gate P5-G1 --evidence docs/qa/test-report.md
python -m orchestrator.cli gate P5-G4-CRO --evidence docs/analytics/cro-report.md
python -m orchestrator.cli finding P5-G2 --title "..." --owner senior-backend-engineer --severity High --file src/x.ts --issue "..." --fix "..."
python -m orchestrator.cli frontend-check --area all
python -m orchestrator.cli lint
python -m orchestrator.cli graph --mermaid
```

---

## Phase Map

| Phase | Specification | Produces | Key Roles |
|---|---|---|---|
| **0 — Setup** | `phases/PHASE-0-SETUP.md` | Dependencies installed, templates initialized, browser evidence kit | Coordinator, CLI |
| **1 — Discovery** | `phases/PHASE-1-DISCOVERY.md` | `plan.md` §1-2, capabilities, personas, funnel, measurement, SEO | `requirement-analyzer`, `senior-product-manager`, `ux-researcher`, `growth-cro-engineer`, `product-analytics-engineer`, `technical-seo-engineer`, `content-designer` |
| **2 — Architecture** | `phases/PHASE-2-ARCHITECTURE.md` | `plan.md` §3-6 (Hard Rules, Schema, C4 Diagrams, OpenAPI) | `senior-system-architect` (★), `senior-database-architect` (★), `senior-security-engineer` (★), `senior-privacy-engineer` (★), `senior-sre-observability-engineer` (★), `senior-technical-writer` |
| **3 — Design** | `phases/PHASE-3-DESIGN.md` | `design-system/MASTER.md`, screen specs, measurement and SEO contracts | `senior-product-designer`, `ui-designer`, `design-system-engineer`, `growth-cro-engineer`, `product-analytics-engineer`, `technical-seo-engineer`, `content-designer`, `senior-accessibility-engineer`, `brand-guardian` |
| **4 — Build** | `phases/PHASE-4-BUILD.md` | Complete product code, instrumented funnels, public SEO surfaces | Track implementation roles |
| **5 — Quality & Security** | `phases/PHASE-5-QUALITY-SECURITY.md` | Gates G0-ML through G6 (incl. G3-P privacy and G4-CRO) | `senior-qa-architect`, `code-reviewer`, `senior-security-engineer`, `senior-privacy-engineer`, `visual-qa`, `growth-cro-engineer`, `senior-accessibility-engineer`, `senior-performance-engineer` |
| **6 — DevOps & Launch** | `phases/PHASE-6-DEVOPS-LAUNCH.md` | CI/CD, hardened Docker, live staging/prod, observability, SLOs, funnel/RUM baselines, runbooks | `senior-devops-engineer`, `senior-sre-observability-engineer`, `senior-mlops-engineer`, `product-analytics-engineer`, `growth-cro-engineer`, `technical-seo-engineer`, `senior-technical-writer` |

---

## Complete Agent Roster (42 Roles)

See `agents/TEAM.md` for full tiers, ownership boundaries, and operational rules. Full list of agent briefs:

```
agents/
├── TEAM.md                              — roster, tiers, ownership, escalation
├── coordinator.md                       ★ orchestrate only (phases 0–6)
├── requirement-analyzer.md              ┐
├── senior-product-manager.md            │ Phase 1 — Discovery
├── ux-researcher.md                     │
├── design-researcher.md                 │
├── pinterest-researcher.md              │
├── content-designer.md                  │
├── growth-cro-engineer.md               │
├── product-analytics-engineer.md        │
├── technical-seo-engineer.md             ┘
├── senior-system-architect.md           ┐
├── senior-system-designer.md            │
├── senior-cloud-architect.md            │ Phase 2 — Architecture & System Design
├── senior-database-architect.md         │
├── senior-security-engineer.md          │
├── senior-privacy-engineer.md           │
├── senior-sre-observability-engineer.md │
├── senior-technical-writer.md           ┘
├── senior-product-designer.md           ┐
├── ui-designer.md                       │ Phase 3 — Design & Accessibility
├── senior-accessibility-engineer.md     │
├── brand-guardian.md                    │
├── design-system-engineer.md            ┘
├── senior-ai-engineer.md                (AI strategy, spans P2-P4)
├── senior-backend-engineer.md           ┐
├── senior-frontend-engineer.md          │ Phase 4 — Build (Product/Web)
├── senior-integration-engineer.md       │
├── senior-mobile-engineer.md            ┘
├── senior-ai-research-engineer.md       ┐
├── senior-machine-learning-engineer.md  │
├── senior-deep-learning-engineer.md     │
├── senior-llm-engineer.md               │ Phase 4 — Build (AI/ML)
├── senior-generative-ai-engineer.md     │
├── senior-nlp-engineer.md               │
├── senior-computer-vision-engineer.md   │
├── senior-data-engineer.md              ┘
├── senior-qa-architect.md               ┐
├── code-reviewer.md                     │
├── visual-qa.md                         │ Phase 5 — Quality & Security
├── senior-performance-engineer.md       │
├── senior-mlops-engineer.md             ┘ (AI/ML eval + registry gate)
└── senior-devops-engineer.md              Phase 6 — DevOps & Launch
```

---

## Directory Layout

```
akstack/
├── README.md                    — system overview
├── GETTING-STARTED.md           — step-by-step onboarding
├── GLOBAL-RULES.md              — global coding discipline & hard rule invariants
├── PROMPT_LIBRARY.md            — verbatim copy-paste prompts & CLI commands
├── bin/
│   ├── akstack                  — POSIX shell CLI launcher
│   └── akstack.bat              — Windows batch CLI launcher
├── orchestrator/                — Python 3 programmatic orchestration engine
│   ├── cli.py                   — terminal commands & formatted output
│   ├── engine.py                — task execution, verification, git commits
│   ├── graph.py                 — DAG resolution, cycle check, parallel waves
│   ├── models.py                — data models (Task, Gate, Plan)
│   ├── parser.py                — markdown parser & state updater
│   └── frontend.py              — framework-agnostic frontend contract checks
├── .agents/skills/akstack/       — native Antigravity skill integration
├── templates/
│   ├── plan.template.md
│   ├── ToDos.template.md
│   ├── PROGRESS.template.md
│   ├── adr.template.md
│   ├── design-system.MASTER.template.md
│   ├── runbook.template.md
│   ├── env-spec.template.md
│   ├── openapi.template.yaml
│   ├── screen-spec.template.md
│   ├── measurement-plan.template.md
│   ├── technical-seo.template.md
│   ├── visual-report.template.md
│   ├── accessibility-report.template.md
│   ├── performance-report.template.md
│   ├── component-traceability.template.md
│   ├── frontend-quality-checklist.md
│   ├── playwright.config.template.ts
│   └── frontend-ci.template.yml
├── agents/                      — 42 specialized role briefs + TEAM.md
├── phases/                      — 7 phase specifications
├── tests/                       — automated test suite for orchestrator
└── integrations/
    └── EXTERNAL-TOOLS.md        — external dependencies & tools
```
