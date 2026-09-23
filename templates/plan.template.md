# {{PROJECT_NAME}} — Plan

> Filled in once, at bootstrap (`PROMPT_LIBRARY.md` §1 or `akstack init`).
> Revised only via the cross-cutting change prompt (`PROMPT_LIBRARY.md` §6.3) — never edited silently mid-build.

## 0. Track

**{{Product/Web | AI/ML | Hybrid}}** — decides which agents activate in
Phase 4. See `README.md`'s track table and `phases/PHASE-4-BUILD.md`.

## 1. What & Why

{{One paragraph: what this product/system does, who it's for, the problem
it solves. Written for someone who's never seen the requirement.}}

- **Primary user outcome:** {{What valuable result should happen?}}
- **Commercial model:** {{Free / subscription / usage / transaction / internal; state what "lucrative" means for this product.}}
- **Acquisition surfaces:** {{Public routes, search, referrals, paid campaigns, or none.}}
- **North-star metric:** {{The repeatable value event, not traffic.}}

## 2. Users & Roles

| Role | Can do | Cannot do |
|---|---|---|
| {{Admin}} | Full administrative access, tenant settings, audit logs | Cannot bypass MFA or access raw credentials |
| {{User}} | Self-service operations within authorized tenant scope | Cannot access resources of other tenants |

## 3. Domain & Hard Rules

**The most critical section in the file.** See `GLOBAL-RULES.md` §2 for
the reasoning. Name this project's non-negotiable domain invariants explicitly:

1. {{Rule 1: e.g., Money is never floating-point; all currency stored in integer minor units (cents).}}
2. {{Rule 2: e.g., Multi-table mutations must execute within an ACID database transaction.}}
3. {{Rule 3: e.g., Tenant isolation is enforced on every query; cross-tenant leakage is a P0 security defect.}}
4. {{Rule 4: e.g., Mutations on financial or external API actions require an idempotency key.}}

## 4. Architecture & Stack

- **Frontend:** {{Framework (Next.js / Vite / Remix), Styling (Vanilla CSS / Tailwind), State}}
- **Mobile (if applicable):** {{React Native / Expo / Flutter / PWA}}
- **Backend:** {{Runtime (Node.js / Python FastAPI / Go / Rust), Architecture (Modular Monolith / Microservices)}}
- **Database & Storage:** {{PostgreSQL / MySQL, ORM (Prisma / Drizzle / SQLAlchemy), Caching (Redis)}}
- **Auth & Security:** {{Provider (Auth0 / Supabase / NextAuth / Custom JWT), RBAC model}}
- **Third-Party Integrations:** {{Payments (Stripe), Email/SMS (Resend/Twilio), Webhooks}}
- **Observability & SRE:** {{OpenTelemetry, Prometheus metrics, Structured JSON logging, Sentry error tracking}}
- **Hosting/Infra:** {{Cloud provider (AWS / GCP / Cloudflare / Vercel), Containerization (Docker), CI/CD (GitHub Actions)}}
- **AI/ML Stack (if Track includes AI/ML):** {{Model providers, embeddings, vector store, orchestration framework, evaluation set}}
- **Frontend product surface:** {{Web / mobile / both / no user-facing UI}}
- **Design direction:** {{Product-specific visual thesis and one signature moment; do not use a generic style label alone.}}
- **Analytics:** {{Consent model, event destination, retention, and experiment tooling}}
- **SEO:** {{Public route/indexability strategy, locales, structured data}}

## 5. Data & Storage Invariants

{{Core entities, relationships, indexing guidelines, and data retention/backup policy. Full schema is designed in Phase 2 by senior-database-architect.}}

- **Auditability:** {{e.g. Append-only audit table for all sensitive mutations}}
- **Soft vs Hard Delete:** {{e.g. Soft deletion with deleted_at timestamp; GDPR purge job}}

## 6. Service Level Objectives (SLOs) & Performance Budget

- **API Latency:** P95 < 300ms, P99 < 800ms
- **Core Web Vitals:** LCP < 2.5s, INP < 200ms, CLS < 0.1
- **Availability Target:** 99.9% uptime
- **Accessibility Bar:** WCAG 2.2 AA compliance
- **Frontend Evidence Matrix:** 320, 375, 768, 1024, 1280, 1440px; landscape; light/dark; reduced motion; 200%/400% zoom

## 7. Phases & Milestones

Standard six-phase shape (`README.md`'s phase map). Note any project-specific deviations.

## 8. Non-Goals

{{What this explicitly will NOT do in this version. Defends against scope creep.}}

## 9. Open Questions & Assumptions

{{Every genuine ambiguity from the requirement, with the explicit assumption made and why — resolved here by a human, not guessed silently downstream.}}
