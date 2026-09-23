# Design System — MASTER

> Generated in Phase 3. Frontend and mobile consume these tokens only.
> Do not invent colors, type, or spacing in implementation.

## Brand

- Personality: {{}}
- Voice: {{}}
- Anti-patterns: {{}}

## Art Direction

- Chosen direction: {{one clear direction, not a list of styles}}
- Visual thesis: {{the feeling and product promise the interface should communicate}}
- Signature element: {{one memorable visual anchor users can recognize}}
- Composition rule: {{editorial / asymmetric / structured / immersive and why}}
- Image and illustration treatment: {{source, crop, aspect ratio, art direction}}
- Surfaces rule: {{where depth, borders, texture, or flat color are used}}

Do not default to a generic centered hero, interchangeable rounded cards, purple
gradients, excessive glass, or a dashboard made of equal-weight cards. Those are
allowed only when the product's audience and content make the choice explicit.

## Design Principles

1. Hierarchy before decoration: the primary user action is obvious within five seconds.
2. One strong visual idea per surface: variety comes from composition and content, not random effects.
3. Confidence through clarity: price, state, ownership, and next step are never obscured.
4. Restraint is a feature: motion, shadows, blur, and gradients earn their place.
5. Accessible by construction: contrast, focus, reduced motion, zoom, and content reflow are token-level concerns.

## Color

| Token | Light | Dark | Contrast vs surface | Usage |
|---|---|---|---|---|
| `--color-bg` | | | | App background |
| `--color-surface` | | | | Cards, panels |
| `--color-text` | | | ≥ 4.5:1 | Body text |
| `--color-text-muted` | | | ≥ 4.5:1 | Secondary text |
| `--color-primary` | | | ≥ 4.5:1 on bg | Primary CTA |
| `--color-danger` | | | ≥ 4.5:1 | Errors |
| `--color-border` | | | ≥ 3:1 | Dividers |

Never convey state by color alone.

## Typography

| Token | Size / line-height / weight | Usage |
|---|---|---|
| `--font-sans` | | UI |
| `--text-xs` | | Meta |
| `--text-sm` | | Captions |
| `--text-md` | | Body |
| `--text-lg` | | H3 |
| `--text-xl` | | H2 |
| `--text-display` | | H1 |

One `<h1>` per page. Do not skip heading levels.

## Spacing & Radii

Scale: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`. No magic numbers.

Content measure: {{max readable line length}}. Page gutter: {{mobile / tablet / desktop}}.
Grid: {{columns, max width, gutter, and when the grid intentionally breaks}}.
Radii: {{sm / md / lg / pill; use the smallest radius that supports the component}}.
Elevation: {{levels and use; avoid shadows as decoration}}.

## Iconography & Assets

- Icon family: {{one named family and stroke/fill rule}}
- Icon sizes: `--icon-sm`, `--icon-md`, `--icon-lg`
- Meaningful icons have accessible names; decorative icons are hidden.
- No emoji as structural UI icons.
- Asset manifest: {{path to approved assets and licenses}}

## Motion

- Duration: 150ms (micro), 250ms (panel), 400ms (page)
- Easing: `cubic-bezier(0.2, 0, 0, 1)`
- Honor `prefers-reduced-motion`

## Component states (mandatory)

Every interactive component specifies: default, hover, focus-visible, active, disabled, loading, empty, error, success.

Each component documents: purpose, anatomy, token dependencies, keyboard behavior,
screen-reader name/state, responsive behavior, content limits, and analytics events.

## Page Composition

Every page spec identifies: audience, intent, funnel stage, primary action,
secondary actions, proof/trust elements, responsive composition, and the empty/error
recovery path. Pages may override the system only through a documented page override.

## Breakpoints

- Mobile: 375–428
- Tablet: 768–1024
- Desktop: 1280–1920
- Touch target ≥ 44×44 CSS px
- Also verify 320px minimum content width, 200% and 400% zoom, landscape, forced colors, and reduced motion.
