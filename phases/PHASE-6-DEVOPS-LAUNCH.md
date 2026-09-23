# Phase 6 — DevOps & Launch

**Objective:** Transition the gated, production-verified codebase into a live, highly available, observable production environment with automated CI/CD pipelines, verified disaster recovery backups, and tested rollback procedures.

## Active Agents

| Agent | Role in this Phase | Tier | Mode |
|---|---|---|---|
| `senior-devops-engineer` | CI/CD pipelines, Docker containerization, IaC deployment, backups | Standard | Implement |
| `senior-sre-observability-engineer` | Telemetry instrumentation, Prometheus dashboards, alerts, SLOs | ★ Senior | Implement |
| `senior-technical-writer` | Production runbooks, environment variable specs, disaster recovery guides | Standard | Implement |
| `senior-mlops-engineer` | Production model serving, drift monitoring (AI/ML & Hybrid tracks) | Standard | Implement |
| `product-analytics-engineer` | Funnel/RUM dashboards, event health, consent and experiment telemetry | Standard | Implement |
| `growth-cro-engineer` | Launch funnel baseline, experiment rollback and guardrail monitoring | Standard | Implement |
| `technical-seo-engineer` | Sitemap/indexation monitoring and search-console launch checks | Standard | Implement |

## Inputs
- Fully gated release candidate from Phase 5 (`git tag phase-5-complete`).
- Infrastructure topology from `senior-cloud-architect`.
- Telemetry standards from `senior-sre-observability-engineer`.

## Outputs
- Automated CI/CD pipeline (`.github/workflows/deploy.yml`).
- Hardened multi-stage container Dockerfiles with non-root runtime users.
- Live staging and production environments.
- Active Prometheus / Grafana observability and alerting rules.
- Disaster recovery backup verification and documented rollback commands in `docs/runbooks/`.
- Final `CHANGELOG.md` update.
- Product funnel and real-user performance baselines recorded before launch, with alerts for event loss, conversion guardrails, and indexability regressions.

## Exit Criteria
- Production environment is live and responding with HTTP 200 on `/health/live` and `/health/ready`.
- Automated rollback procedure has been executed and verified in staging.
- Automated daily database backup snapshot is configured and verified.
- `PROGRESS.md` contains the final phase summary entry.
- Acquisition, activation, and revenue events are verified in the production-safe analytics environment; no consent or PII regression is present.
- `git tag phase-6-complete` (or `v1.0.0`).

## Post-Launch Operations
All ongoing changes follow the same disciplined lifecycle:
- Cross-cutting requirement changes: `PROMPT_LIBRARY.md` §6.3.
- All new features pass Phase 5 gating before shipping to production.
