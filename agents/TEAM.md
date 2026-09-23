# {{PROJECT_NAME}} — Team & Orchestration Roster

## §1. Full Roster (42 Roles)

| Agent | Phase | Track | Tier | Mode |
|---|---|---|---|---|
| `coordinator` | 0–6 | Shared | ★ Senior | Orchestrate only |
| `requirement-analyzer` | 1 Discovery | Shared | Standard | Implement |
| `senior-product-manager` | 1 Discovery | Shared | Standard | Implement |
| `ux-researcher` | 1 Discovery | Shared | Standard | Implement |
| `design-researcher` | 1 Discovery | Shared | Standard | Implement |
| `pinterest-researcher` | 1 Discovery | Shared | Standard | Implement |
| `content-designer` | 1 + 3 + 4 | Shared | Standard | Implement |
| `growth-cro-engineer` | 1 + 3 + 5 Gate + 6 Launch | Product/Web & Hybrid | Standard | Implement / Review-only |
| `product-analytics-engineer` | 1 + 3 + 4 + 5 Gate + 6 Launch | Product/Web & Hybrid | Standard | Implement / Review support |
| `technical-seo-engineer` | 1–6 | Product/Web & Hybrid | Standard | Implement / Review support |
| `senior-system-architect` | 2 Architecture | Shared | ★ Senior | Implement |
| `senior-system-designer` | 2 Architecture | Shared | Standard | Implement |
| `senior-cloud-architect` | 2 Architecture | Shared | Standard | Implement |
| `senior-database-architect` | 2 Architecture | Shared | ★ Senior | Implement |
| `senior-security-engineer` | 2 Architecture + 5 Gate | Shared | ★ Senior | Implement (P2) / Review-only (P5) |
| `senior-privacy-engineer` | 2 Architecture + 5 Gate | Shared | ★ Senior | Implement (P2) / Review-only (P5 G3-P) |
| `senior-sre-observability-engineer` | 2 Architecture + 6 Launch | Shared | ★ Senior | Implement |
| `senior-technical-writer` | 2 Architecture + 6 Launch | Shared | Standard | Implement |
| `senior-ai-engineer` | 2–4 AI strategy | AI/ML | ★ Senior | Implement (architecture only) |
| `senior-product-designer` | 3 Design | Shared | Standard | Implement |
| `ui-designer` | 3 Design | Shared | Standard | Implement |
| `senior-accessibility-engineer` | 3 Design + 5 Gate | Shared | Standard | Implement (P3) / Review-only (P5) |
| `brand-guardian` | 3 Design + 5 Gate | Shared | Standard | Review-only |
| `design-system-engineer` | 3 Design + 4 Build | Product/Web & Hybrid | Standard | Implement |
| `senior-backend-engineer` | 4 Build | Product/Web | Standard | Implement |
| `senior-frontend-engineer` | 4 Build | Product/Web | Standard | Implement |
| `senior-integration-engineer` | 4 Build | Product/Web | Standard | Implement |
| `senior-mobile-engineer` | 4 Build | Product/Web | Standard | Implement |
| `senior-ai-research-engineer` | 4 Build | AI/ML | ★ Senior | Implement |
| `senior-machine-learning-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-deep-learning-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-llm-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-generative-ai-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-nlp-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-computer-vision-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-data-engineer` | 4 Build | AI/ML | Standard | Implement |
| `senior-qa-architect` | 5 Gate (G1) | Shared | Standard | Implement (tests only) |
| `code-reviewer` | 5 Gate (G2) | Shared | Standard | Review-only |
| `visual-qa` | 5 Gate (G4) | Shared | Standard | Review-only |
| `senior-performance-engineer` | 5 Gate (G5) | Shared | Standard | Review-only |
| `senior-mlops-engineer` | 5 Gate (G0-ML) + 6 | AI/ML | Standard | Implement |
| `senior-devops-engineer` | 6 Launch | Shared | Standard | Implement |

Full role briefs: `agents/<agent-name>.md`.

---

## §2. Model Tier Policy

**★ Senior tasks must NEVER be delegated to a lower or faster model tier**, regardless of task size. Failure mode is an undetected invariant violation, schema hole, security/privacy breach, or unrecoverable production state — not a syntax error.

**★ Senior Roles (Mandatory Flagship Tier):**
- `coordinator`: Dispatch, gates, Hard Rule enforcement, human halt.
- `senior-system-architect`: Boundaries, modularity, topology.
- `senior-database-architect`: Schema, migrations, indexes, storage invariants.
- `senior-security-engineer`: Threat model, authz, OWASP.
- `senior-privacy-engineer`: Minimization, retention, subject rights, DPIA.
- `senior-sre-observability-engineer`: Telemetry, error budgets, degradation.
- `senior-ai-engineer`: Technique selection, safety bounds, eval bars.
- `senior-ai-research-engineer`: Algorithmic validation.

All other roles may run on standard tiers when Accept and Verify are strict.

---

## §3. File Ownership & Boundary Isolation

Two tasks with overlapping files never run in parallel. Empty `Files:` is treated as a collision with everything. Customize paths at bootstrap:

```
database/schema.sql, database/migrations/ → senior-database-architect only (★)
engine/ (rule_engine.py, backtester.py)  → senior-backend-engineer, senior-system-architect (★)
risk/ (risk_guardrails.py, sizing.py)    → senior-backend-engineer, senior-security-engineer (★)
bridge/ (dwx_connect/, mt4_ea/)          → senior-integration-engineer
data/ (historical/, dukascopy/)          → senior-data-engineer
journal/ (trade_logger.py, storage.py)   → senior-database-architect, senior-backend-engineer
ml/ (confidence_model.py, rl_agent.py)   → senior-machine-learning-engineer, senior-ai-research-engineer (★)
tests/                                   → senior-qa-architect (writes tests only, never edits source)
docs/, ADRs, specs                       → senior-technical-writer, or owning architect
plan.md, ToDos.md, PROGRESS.md, STOP     → coordinator / orchestrator CLI only
```

---

## §4. Standing Production Rules (Every Task, Every Agent)

1. **Domain Hard Rules (`plan.md` §3)** apply to every line, not just security's lines.
2. **Boundary Validation:** Zod/Pydantic/TypeBox at every transport edge. Never trust the client.
3. **Atomic Mutations:** Multi-step writes that must succeed or fail together run in an ACID transaction.
4. **Server-Side Authorization:** Re-check tenant and resource on every request. No client-only guards.
5. **Exact Financial Quantities:** Integer minor units or decimal types. Never float money.
6. **Idempotent Mutations & Webhooks:** Idempotency keys + signature verify.
7. **Production Telemetry:** Structured JSON, UTC, level, `trace_id`. No `console.log` / `print` in prod.
8. **Design System:** UI consumes `design-system/MASTER.md` tokens only.
9. **Accessibility:** WCAG 2.2 AA — semantics, labels, keyboard, 4.5:1 text.
10. **Privacy:** Minimization, purpose limitation, no PII in logs, no PII to model vendors unless `plan.md` allows it.
11. **Frontend quality:** Product/Web and Hybrid work has a product-specific visual thesis, screen-spec traceability, measurable funnel, technical SEO contract, and browser evidence.
12. **Surgical Scope:** Touch only `Files:`. Pre-existing junk goes to `PROGRESS.md`, not a drive-by refactor.
13. **Explicit Escalation:** Ambiguity, credentials, irreversible ops → `akstack question` or `akstack handoff`. Never guess.

---

## §5. Escalation & Autonomous Protocol

1. Hard Rule at risk, missing credential, or costly-to-reverse decision:
   - `akstack handoff <id> --blocked-on "..." --why "..."` (writes PROGRESS + `STOP`).
   - Do not fabricate credentials or mock away a real barrier.
2. Verify fails up to 3 times:
   - `akstack fail <id> --error "<diagnosis>"`
   - Dependents halt. After a fix: `akstack reset <id>`.
3. Review-only gates (G2, G3, G3-P, G4, G4-CRO, G4-A11Y, G5) file `-F` via `akstack finding`. They never patch production code.

---

## §6. Skills & Tooling Integration Across Roles

Each role brief in `agents/` is designed to leverage domain-specific skills and industry standards:

- **Frontend & UI/UX:** `senior-frontend-engineer`, `design-system-engineer`, `senior-product-designer`, `ui-designer`, `visual-qa` leverage design tokens, layout hierarchy, motion principles, and responsive engineering (`designer-skills`, `emilkowalski-skills`, `jakubkrehel-skills`, `mengto-skills`).
- **Growth, SEO & Analytics:** `growth-cro-engineer`, `technical-seo-engineer`, `product-analytics-engineer` leverage conversion rate optimization, structured data schemas, and analytics measurement frameworks (`marketingskills`, `ai-seo`, `schema`, `cro`).
- **Backend, Storage & APIs:** `senior-backend-engineer`, `senior-database-architect`, `senior-system-architect`, `senior-integration-engineer`, `senior-mobile-engineer` leverage clean/hexagonal architecture, zero-downtime database migrations, and API standards (`architecture-patterns`, `postgresql`, `database-optimizer`, `api-design-principles`).
- **DevOps, SRE & Cloud:** `senior-cloud-architect`, `senior-devops-engineer`, `senior-sre-observability-engineer`, `senior-performance-engineer` leverage IaC, container orchestration, distributed tracing, and SLO/error budget monitoring (`terraform-specialist`, `kubernetes-architect`, `distributed-tracing`, `grafana-dashboards`).
- **Security & Privacy:** `senior-security-engineer`, `senior-privacy-engineer` leverage STRIDE threat modeling, OWASP ASVS compliance, and GDPR/CCPA data privacy minimization (`threat-modeling-expert`, `auth-implementation-patterns`, `gdpr-data-handling`).
- **Quality Assurance & Verification:** `senior-qa-architect`, `code-reviewer`, `senior-accessibility-engineer` leverage TDD red-green-refactor workflows, automated E2E testing, and WCAG 2.2 AA / APCA standards (`tdd-orchestrator`, `e2e-testing-patterns`, `better-accessibility`).
- **AI/ML & LLM Engineering:** `senior-ai-engineer`, `senior-llm-engineer`, `senior-generative-ai-engineer`, `senior-mlops-engineer`, `senior-data-engineer` leverage RAG architectures, vector index tuning, and MLOps pipelines (`ai-engineer`, `rag-implementation`, `mlops-engineer`).

