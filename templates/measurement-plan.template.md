# Product Measurement Plan

## North-Star Outcome

- **North-star metric:** {{repeatable user value, not page views}}
- **Activation definition:** {{observable moment of first value}}
- **Revenue event:** {{paid conversion or other business outcome}}
- **Retention window:** {{e.g. 7-day / 30-day retained value}}
- **Guardrails:** {{refunds, complaints, latency, accessibility, opt-outs}}

## Funnel

| Stage | User intent | Event | Owner | Primary metric | Guardrail |
|---|---|---|---|---|---|
| Acquisition | | | | | |
| Signup start | | | | | |
| Signup complete | | | | | |
| Activation | | | | | |
| Core value | | | | | |
| Checkout start | | | | | |
| Paid conversion | | | | | |
| Retention | | | | | |

## Event Contract

Every event below must list trigger, actor, schema version, destination,
non-sensitive properties, retention, consent behavior, deduplication key, and
the product decision it supports.

| Event name | Trigger | Properties | Consent | Decision supported |
|---|---|---|---|---|
| `{{event_name}}` | | | analytics | |

Never send raw email, phone, message body, auth token, precise location, or
sensitive categories unless a documented privacy decision explicitly permits it.

## Attribution

- Allowed campaign parameters: `{{utm_source, utm_medium, utm_campaign}}`
- Persistence window: {{}}
- PII policy: {{}}
- Server/client reconciliation: {{}}

## Experiment Registry

| Experiment | Hypothesis | Audience | Variants | Primary metric | Guardrails | Stop/rollback |
|---|---|---|---|---|---|---|
| `{{id}}` | | | | | | |

No experiment ships without a pre-registered metric, exposure event, eligibility
rule, minimum sample/duration rule, and rollback owner.

## Quality Checks

- [ ] Consent is respected before the first event and after revocation.
- [ ] Duplicate events are rejected or deduplicated.
- [ ] Invalid payloads are visible in monitoring.
- [ ] Exposure is emitted only when the variant rendered.
- [ ] `product-analytics-engineer` reviewed the event catalog.
