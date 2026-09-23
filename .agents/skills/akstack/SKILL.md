---
name: akstack
description: Production-grade multi-agent orchestration framework for full-stack applications across architecture, system design, databases, frontend, backend, integrations, mobile, SQA, SRE, privacy, and DevOps.
---

# Akram-Stack (akstack) Orchestrator Skill

## Overview
Akram-Stack persists state in `plan.md`, `ToDos.md`, and `PROGRESS.md`, runs a 7-phase lifecycle (0–6), isolates agents by file ownership, enforces domain Hard Rules, and ships only through the applicable gates G0-ML → G6 (including G3-P privacy and G4-CRO frontend review).

You are the **coordinator** unless a task Owner says otherwise. Orient from disk. Do not rely on chat memory.

## Bootstrap

```bash
python -m orchestrator.cli doctor
python -m orchestrator.cli init "Project Name" --track Product/Web   # or AI/ML | Hybrid
python -m orchestrator.cli lint
```

STOP after init until a human has approved `plan.md` §3 (Hard Rules), §8 (non-goals), and §9 (open questions).

## Session loop

```bash
python -m orchestrator.cli status --json
python -m orchestrator.cli next
python -m orchestrator.cli packet              # full agent packet for the next task
python -m orchestrator.cli start <task-id>
# implement strictly within Files:; read agents/<owner>.md first
python -m orchestrator.cli complete <task-id>
```

Parallel waves (disjoint files only): `python -m orchestrator.cli next --parallel`

Human task or credential: `python -m orchestrator.cli handoff <id> --blocked-on "..." --why "..."` then halt.

After the person resolves it: `python -m orchestrator.cli resume --notes "..."`.

Ambiguity: `python -m orchestrator.cli question <id> --ambiguity "..." --risk "..." --recommended "..."`

Blocked: `python -m orchestrator.cli fail <id> --error "..."` then later `reset`.

## Core Agent Roster
- **Orchestration:** `coordinator` (★)
- **Architecture:** `senior-system-architect` (★), `senior-system-designer`, `senior-cloud-architect`, `senior-database-architect` (★), `senior-security-engineer` (★), `senior-privacy-engineer` (★), `senior-sre-observability-engineer` (★), `senior-technical-writer`
- **Discovery/Design:** `requirement-analyzer`, `senior-product-manager`, `ux-researcher`, `design-researcher`, `pinterest-researcher`, `content-designer`, `senior-product-designer`, `ui-designer`, `senior-accessibility-engineer`, `brand-guardian`
- **Frontend growth:** `design-system-engineer`, `growth-cro-engineer`, `product-analytics-engineer`, `technical-seo-engineer`
- **Build:** `senior-backend-engineer`, `senior-frontend-engineer`, `senior-integration-engineer`, `senior-mobile-engineer`, plus AI/ML specialists when track requires them
- **Quality:** `senior-qa-architect` (tests only), `code-reviewer`, `visual-qa`, `senior-performance-engineer` (review-only)
- **Launch:** `senior-devops-engineer`, `senior-mlops-engineer`

## Mandatory Engineering Principles
1. Never violate Hard Rules in `plan.md` §3.
2. Review-only gates (G2, G3, G3-P, G4, G4-CRO, G4-A11Y, G5) never edit source; they file `-F` tasks.
3. ★ Senior work stays on the flagship model tier.
4. Validate all inputs at transport boundaries (Zod/Pydantic). Defend OWASP (BOLA/IDOR, SQLi, XSS, SSRF).
5. Empty `Files:` is not parallel-safe. Overlapping files never share a wave.
6. No PII in logs; no PII to model vendors unless `plan.md` explicitly allows it.
7. `STOP` file present → do not start another task.
8. Product/Web and Hybrid frontends require a product-specific visual thesis, screen-spec evidence, privacy-aware funnel measurement, technical SEO contract, and browser evidence before G6.

## Gates

```bash
python -m orchestrator.cli gate P5-G0-ML --evidence docs/qa/ml-eval-report.md  # skipped automatically on Product/Web
python -m orchestrator.cli gate P5-G1 --evidence docs/qa/test-report.md
python -m orchestrator.cli gate P5-G2 --evidence docs/qa/code-review.md
python -m orchestrator.cli gate P5-G3 --evidence docs/qa/security-report.md
python -m orchestrator.cli gate P5-G3-P --evidence docs/qa/privacy-report.md
python -m orchestrator.cli gate P5-G4 --evidence docs/qa/visual-report.md
python -m orchestrator.cli gate P5-G4-CRO --evidence docs/analytics/cro-report.md
python -m orchestrator.cli gate P5-G4-A11Y --evidence docs/qa/accessibility-report.md
python -m orchestrator.cli gate P5-G5 --evidence docs/performance/report.md
python -m orchestrator.cli gate P5-G6 --evidence docs/qa/release-signoff.md
```

File a finding: `python -m orchestrator.cli finding P5-G2 --title "..." --owner senior-backend-engineer --severity High --file src/x.ts --issue "..." --fix "..."`

## Specialized Skills & Capabilities Integration

akstack coordinates execution across domain-specific skill ecosystems to enforce industry best practices:

| Domain | Integrated Skills / Standards | Applicable Agents |
|---|---|---|
| **Frontend & Design System** | `designer-skills` (visual-hierarchy, design-token, fitts-law, typography-scale, responsive-design, dark-mode-design, motion-system), `emilkowalski-skills` (animate, apple-design), `jakubkrehel-skills` (better-ui, better-typography, better-colors, better-layout), `mengto-skills` (landing-page, tailwindcss, gsap, cobejs) | `senior-frontend-engineer`, `design-system-engineer`, `senior-product-designer`, `ui-designer`, `visual-qa` |
| **Growth, SEO & CRO** | `marketingskills` (cro, copywriting, seo-audit, ai-seo, schema, analytics, emails, launch), `antigravity-skills-manager` (seo-meta-optimizer, seo-structure-architect) | `growth-cro-engineer`, `technical-seo-engineer`, `product-analytics-engineer`, `content-designer` |
| **Backend & Architecture** | `architecture-patterns` (clean/hexagonal), `api-design-principles`, `go-concurrency-patterns`, `fastapi-pro`, `nodejs-backend-patterns`, `error-handling-patterns` | `senior-system-architect`, `senior-system-designer`, `senior-backend-engineer`, `senior-integration-engineer`, `senior-mobile-engineer` |
| **Databases & Storage** | `postgresql`, `database-optimizer`, `database-migrations-sql-migrations`, `sql-optimization-patterns`, `cqrs-implementation`, `event-store-design` | `senior-database-architect`, `senior-backend-engineer` |
| **Cloud, DevOps & SRE** | `terraform-specialist`, `kubernetes-architect`, `k8s-manifest-generator`, `github-actions-templates`, `distributed-tracing`, `grafana-dashboards`, `prometheus-configuration`, `slo-implementation`, `incident-responder` | `senior-cloud-architect`, `senior-devops-engineer`, `senior-sre-observability-engineer`, `senior-performance-engineer` |
| **Security & Privacy** | `threat-modeling-expert` (STRIDE/PASTA), `stride-analysis-patterns`, `auth-implementation-patterns`, `backend-security-coder`, `frontend-security-coder`, `security-auditor`, `gdpr-data-handling`, `secrets-management` | `senior-security-engineer`, `senior-privacy-engineer` |
| **Quality & Verification** | `tdd-orchestrator`, `e2e-testing-patterns` (Playwright/Cypress), `python-testing-patterns`, `javascript-testing-patterns`, `better-accessibility` (WCAG 2.2 AA), `screen-reader-testing` | `senior-qa-architect`, `code-reviewer`, `senior-accessibility-engineer`, `visual-qa` |
| **AI / ML & LLMs** | `ai-engineer`, `rag-implementation`, `llm-application-dev-langchain-agent`, `vector-database-engineer`, `vector-index-tuning`, `embedding-strategies`, `machine-learning-ops-ml-pipeline` | `senior-ai-engineer`, `senior-llm-engineer`, `senior-generative-ai-engineer`, `senior-mlops-engineer`, `senior-data-engineer` |

## Diagnostics

```bash
python -m orchestrator.cli lint
python -m orchestrator.cli doctor
python -m orchestrator.cli graph --mermaid
```

