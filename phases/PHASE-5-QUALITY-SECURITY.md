# Phase 5 — Quality & Security Gating

**Objective:** Execute the strict quality, security, privacy, accessibility, and performance gate sequence. Every review-only gate logs actionable findings as new `-F` tasks; reviewers NEVER grade or fix their own findings.

## Gate Sequence

| Gate | Agent | Focus / Review Bar | Mode |
|---|---|---|---|
| **G0-ML** *(AI/ML only)* | `senior-mlops-engineer` | Model lineage, reproducible training, metric threshold cleared | Implement |
| **G1 Test** | `senior-qa-architect` | Automated test suite 100% green, Hard Rules tested first | Implement (tests only) |
| **G2 Code Review** | `code-reviewer` | Clean architecture, error handling, maintainability, ownership | Review-only |
| **G3 Security** | `senior-security-engineer` | OWASP Top 10 + ASVS, auth boundaries, Hard Rules verification | Review-only |
| **G3-P Privacy** | `senior-privacy-engineer` | Minimization, retention, subject rights, PII in logs/prompts | Review-only |
| **G4 UX/Visual** | `visual-qa` + `brand-guardian` | Breakpoint fidelity, design system compliance, Impeccable slop check | Review-only |
| **G4-CRO** | `growth-cro-engineer` + `product-analytics-engineer` | Funnel clarity, truthful value/price, consent-aware events, SEO handoff | Review-only |
| **G4-A11Y Accessibility** | `senior-accessibility-engineer` | WCAG 2.2 AA compliance, axe-core audit, keyboard navigation | Review-only |
| **G5 Performance** | `senior-performance-engineer` | Core Web Vitals, API latency, Lighthouse CI thresholds | Review-only |
| **G6 Sign-Off** | coordinator / CLI | All prior gates `- [x]`, regression suite green, tag release | Sign-off |

Exact prompts and checklists: `PROMPT_LIBRARY.md` §4.

## How Findings Flow
- Every Critical and High finding from G2 through G5 becomes a new `-F` task (e.g. `P5-F01`) filed directly below the evaluating gate in `ToDos.md`; Medium/Low findings are also tracked unless explicitly deferred by a human.
- Tasks are assigned to the responsible implementation engineer.
- The gate remains unchecked until all filed finding tasks are implemented, verified, and re-reviewed.

## CLI Gate Execution

```bash
# Validate and clear a gate once verification criteria and a report file exist
python -m orchestrator.cli gate P5-G1 --evidence docs/qa/test-report.md
python -m orchestrator.cli gate P5-G3-P --evidence docs/qa/privacy-report.md
python -m orchestrator.cli gate P5-G4 --evidence docs/qa/visual-report.md
python -m orchestrator.cli gate P5-G4-CRO --evidence docs/analytics/cro-report.md
python -m orchestrator.cli gate P5-G4-A11Y --evidence docs/qa/accessibility-report.md
python -m orchestrator.cli gate P5-G5 --evidence docs/performance/report.md
```

## Exit Criteria
- All applicable gates G0-ML through G6 are checked `- [x]` (G4/CRO/A11Y are required for Product/Web and Hybrid).
- Zero unresolved Critical or High security, test, or accessibility defects.
- Full regression suite exits with code 0.
- `git tag phase-5-complete`.

## Next Phase
`phases/PHASE-6-DEVOPS-LAUNCH.md`
