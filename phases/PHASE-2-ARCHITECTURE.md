# Phase 2 — Architecture & System Design

**Objective:** Establish the foundational technical shape — modular boundaries, database schema, API contracts, telemetry standards, threat models, and project Hard Rules — before any feature implementation begins.

## Active Agents

| Agent | Role in this Phase | Tier | Mode |
|---|---|---|---|
| `senior-system-architect` | High-level architecture, rendering strategy, C4 diagrams | ★ Senior | Implement |
| `senior-system-designer` | API contracts, interface specifications, data flow | Standard | Implement |
| `senior-database-architect` | Storage modeling, schema DDL, zero-downtime migrations, indexes | ★ Senior | Implement |
| `senior-security-engineer` | Threat model (STRIDE), authentication invariants, RBAC/ABAC | ★ Senior | Implement |
| `senior-sre-observability-engineer` | Telemetry architecture, golden signals, health check design | ★ Senior | Implement |
| `senior-technical-writer` | OpenAPI 3.1 specifications, architecture docs, ADR catalog | Standard | Implement |
| `senior-cloud-architect` | Infrastructure topology, cloud services, FinOps budget | Standard | Implement |
| `senior-privacy-engineer` | Data classification, retention, subject rights, DPIA | ★ Senior | Implement |
| `senior-ai-engineer` | AI system architecture, model orchestration (AI/ML & Hybrid) | ★ Senior | Implement |
| `product-analytics-engineer` | Event transport, consent boundary, retention and experiment data model | Standard | Implement |
| `technical-seo-engineer` | Rendering/indexability constraints and public route contract | Standard | Implement |

`senior-system-architect` establishes the overall boundaries first. `senior-database-architect`, `senior-security-engineer`, and `senior-sre-observability-engineer` are ★ Senior roles — never delegate to a lower model tier.

## Inputs
- Approved `plan.md` §0-2 from Phase 1.
- Technical constraints, target scale, and domain compliance rules.

## Outputs
- `plan.md` §3 (**Domain & Hard Rules** — the most critical artifact in the entire system).
- `plan.md` §4-6 (Architecture, Stack, Storage Invariants, SLO Budgets) finalized.
- C4 Context & Container diagrams in `docs/architecture/`.
- Concrete schema definitions and initial migration scripts in `db/` or `prisma/`.
- OpenAPI 3.1 specifications in `docs/openapi.yaml`.
- Initial ADRs in `docs/adr/`.
- `agents/TEAM.md` §3 (File Ownership) calibrated to the selected stack.
- Analytics event transport and consent boundaries aligned with privacy architecture.
- Public rendering, canonical, sitemap, and structured-data constraints aligned with the frontend architecture.
- Phase 3 and Phase 4 task lists generated in `ToDos.md`.

## Exit Criteria
- Human stakeholder has reviewed and explicitly approved `plan.md` §3 (Hard Rules).
- Database migrations execute cleanly forward and backward in test environment.
- All Phase 4 implementation tasks in `ToDos.md` have an explicit Owner, Files list, and Verify command.

## Next Phase
`phases/PHASE-3-DESIGN.md`
