# Screen Spec: {{Page or flow name}}

- **Status:** Draft | Approved
- **Owner:** ui-designer
- **Route:** `{{/route}}`
- **Primary persona:** {{}}
- **User intent:** {{what the user is trying to accomplish}}
- **Funnel stage:** acquisition | activation | core value | retention | monetization
- **Primary success action:** {{one action}}
- **Design system:** `design-system/MASTER.md`
- **Page override:** `{{design-system/pages/name.md or none}}`

## Visual Direction

- **Visual thesis:** {{how the page should feel and why}}
- **Signature moment:** {{the memorable composition/interaction}}
- **Avoid:** {{specific generic or category anti-patterns}}
- **Content hierarchy:** {{what is seen first, second, third}}

## Anatomy

1. {{region}} — purpose, component, semantic heading, tokens
2. {{region}} — purpose, component, semantic heading, tokens
3. {{region}} — purpose, component, semantic heading, tokens

## Content

- H1: {{}}
- Supporting copy: {{}}
- Primary CTA: {{verb + outcome}}
- Secondary CTA: {{}}
- Proof/trust: {{truthful evidence only}}
- Error/empty copy: see `docs/discovery/copy-outline.md`

## Responsive States

| Viewport | Layout | Visibility/order changes | Overflow behavior |
|---|---|---|---|
| 320–428 | | | |
| 768–1024 | | | |
| 1280–1920 | | | |

Also specify landscape, 200%/400% zoom, keyboard viewport, and long translated strings.

## Interaction States

For every interactive element: default, hover, focus-visible, pressed, disabled,
loading, success, error, and reduced-motion behavior.

## Accessibility

- Landmark and heading outline: {{}}
- Focus order and focus restoration: {{}}
- Labels, descriptions, error association, live regions: {{}}
- Contrast pairs: {{ratios and token names}}
- Keyboard alternative for every gesture: {{}}

## Instrumentation

- Events: {{event names from measurement plan}}
- Properties: {{non-sensitive, schema-versioned properties}}
- Experiment exposure: {{id/variant or none}}

## SEO (public routes only)

- Title / description: {{}}
- Canonical / indexability: {{}}
- JSON-LD / OG image: {{}}
- Server-rendered content requirement: {{}}

## Acceptance Evidence

- [ ] Approved against `design-system/MASTER.md`
- [ ] Screenshot at 320, 375, 768, 1024, 1280, and 1440px
- [ ] Loading, empty, success, error, focus-visible, and disabled states captured
- [ ] `frontend-check --area design` passes
