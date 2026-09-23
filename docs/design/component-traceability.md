# Component & Token Traceability

Every P0 route maps to a screen spec, composition, reusable components, and
the tokens those components consume. This is the bridge between design intent
and code review.

| Route / screen | Screen spec | Composition | Components | Tokens / page override | Browser evidence |
|---|---|---|---|---|---|
| `{{/route}}` | `{{docs/design/name.md}}` | `{{}}` | `{{}}` | `{{}}` | `{{}}` |

## New Pattern Decisions

| Pattern | Why it is needed | Master token/component update | Approval |
|---|---|---|---|
| `{{}}` | | | |

Rules:

- A page may compose existing components; it may not duplicate their tokens.
- A new visual pattern requires a Master update or documented page override.
- Every row has loading, empty, error, success, focus, disabled, and reduced-motion coverage.
