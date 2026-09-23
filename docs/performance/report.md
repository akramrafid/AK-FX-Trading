# Frontend Performance Evidence: {{Release / route set}}

- **Date:** {{YYYY-MM-DD}}
- **Tester:** senior-performance-engineer
- **Build commit:** `{{sha}}`
- **Network/device profile:** {{mobile mid-tier / cold cache / connection}}

## Metrics

| Route | TTFB | LCP | INP | CLS | JS transfer | Image transfer | Budget result |
|---|---:|---:|---:|---:|---:|---:|---|
| `{{/route}}` | | | | | | | |

## Review

- Third-party scripts and consent loading: {{}}
- Bundle and route-split budget: {{}}
- Image dimensions/formats/loading: {{}}
- Main-thread long tasks: {{}}
- API waterfalls/N+1 evidence: {{}}

## Decision

- [ ] Mobile and desktop budgets pass
- [ ] Any miss has a filed owner/cause task
- [ ] `frontend-check --area performance` passes
