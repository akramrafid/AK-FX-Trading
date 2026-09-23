# Phase 3 — Design & Accessibility System

**Objective:** Produce a persisted design system, comprehensive component design tokens, and approved screen specifications before frontend/mobile coding begins, guaranteeing UI developers never make arbitrary visual decisions.

## Active Agents

| Agent | Role in this Phase | Tier | Mode |
|---|---|---|---|
| `senior-product-designer` | Information architecture, layout systems, design token curation | Standard | Implement |
| `ui-designer` | High-fidelity screen specifications, micro-interactions, responsive states | Standard | Implement |
| `senior-accessibility-engineer` | WCAG 2.2 AA audit, keyboard focus flows, ARIA semantics | Standard | Implement |
| `brand-guardian` | Brand alignment, visual consistency, conversion review | Standard | Review-only |
| `content-designer` | UI copy, empty/error/success strings, voice | Standard | Implement |
| `design-system-engineer` | Token implementation, component contracts, gallery and traceability | Standard | Implement |
| `growth-cro-engineer` | Conversion hierarchy, trust, friction and experiment-ready screens | Standard | Implement |
| `product-analytics-engineer` | Screen events, consent behavior, experiment exposure contract | Standard | Implement |
| `technical-seo-engineer` | Metadata, canonical, structured-data and indexability requirements | Standard | Implement |

## External Tooling Integration
- **New Brand (No Existing Assets):** Execute `ui-ux-pro-max` against the domain category and `pinterest-researcher`'s moodboard direction.
- **Existing Brand Assets (Figma, PDFs, Screenshots):** Ingest brand guidelines via `design-system-skill`.
- **Persistence Mandate:** Persist the generated tokens and rules to `design-system/MASTER.md` before Phase 4 begins.

## Inputs
- Approved `plan.md` (target personas, brand tone, viewport requirements).
- Moodboard and competitor benchmarks from Phase 1.
- Technical API contracts and data models from Phase 2.

## Outputs
- `design-system/MASTER.md` (color tokens, typography scales, spacing units, elevations, radii).
- Page-level override files in `design-system/pages/*.md` if specific flows require unique layouts.
- Component specifications with explicit loading, empty, success, error, focus-visible, disabled, and reduced-motion states.
- High-fidelity screen specs using `templates/screen-spec.template.md`, including a specific visual thesis, signature moment, responsive behavior, copy, instrumentation, SEO, and accessibility.
- Component/gallery traceability map linking routes and screens to tokens and reusable components.
- Accessibility focus map and contrast audit report in `docs/design/accessibility-spec.md`.
- Measurement plan in `docs/analytics/measurement-plan.md` and technical SEO contract in `docs/seo/technical-seo.md`.

## Exit Criteria
- `design-system/MASTER.md` is committed and signed off by `brand-guardian`; no unresolved placeholders remain.
- Accessibility specs achieve WCAG 2.2 AA compliance across all proposed color pairs.
- Core user flows are specified in high fidelity so `senior-frontend-engineer` and `senior-mobile-engineer` have zero ambiguity during Phase 4.
- `python -m orchestrator.cli frontend-check --area design` passes.
- Human design sign-off task `P3-G1` approves the resolved Master, screen specs, measurement plan, technical SEO contract, and accessibility spec before Phase 4.

Recommended ledger entry:

```markdown
- [ ] **P3-G1** 🧑 HUMAN Approve frontend design system and screen set
  - **Owner:** coordinator
  - **Deps:** <all Phase 3 design tasks>
  - **Files:** `design-system/MASTER.md`, `docs/design/`
  - **Do:** Human reviews the visual thesis, screen specs, traceability, measurement, SEO, and accessibility artifacts.
  - **Accept:** Explicit approval is recorded with evidence.
  - **Verify:** manual review
```

## Next Phase
`phases/PHASE-4-BUILD.md`
