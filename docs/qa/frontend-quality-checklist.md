# Frontend Quality Contract

Use this as the acceptance checklist for Product/Web and Hybrid builds. The
numbers are defaults; `plan.md` may set stricter budgets.

## Visual quality

- [ ] A product-specific visual thesis and signature moment are present.
- [ ] Type, color, spacing, radius, elevation, icons, imagery, and motion use tokens.
- [ ] No generic centered hero, equal-weight card grid, purple gradient, excessive glass, or stock imagery without a product reason.
- [ ] Primary action and value/price/commitment are clear in five seconds.
- [ ] Loading, empty, success, error, focus, disabled, and reduced-motion states exist.

## Browser evidence

- [ ] Screenshots or traces at 320, 375, 768, 1024, 1280, and 1440px.
- [ ] Portrait and landscape checked.
- [ ] Light and dark mode checked.
- [ ] Long content and translated strings checked.
- [ ] 200% and 400% zoom/reflow checked.

## Accessibility

- [ ] axe or equivalent automated check has zero serious/critical violations.
- [ ] Keyboard-only path covers every P0 flow.
- [ ] Screen reader announces names, roles, states, errors, and async updates.
- [ ] Contrast meets WCAG 2.2 AA; color is never the only signal.
- [ ] Focus is visible, not obscured, and restored after overlays.

## Commercial integrity

- [ ] Funnel events are listed in `docs/analytics/measurement-plan.md`.
- [ ] Consent is respected before analytics/marketing events.
- [ ] No raw PII is sent to analytics.
- [ ] Public routes have truthful metadata, canonical, structured data, sitemap, and robots behavior.
- [ ] No dark patterns, hidden fees, fake proof, fake scarcity, or confirmshaming.

## Performance

- [ ] TTFB, LCP, INP, CLS, JS transfer, image transfer, and third-party script cost are recorded.
- [ ] Mobile cold-cache performance meets `plan.md` budgets.
- [ ] Images have dimensions and appropriate loading priority.
- [ ] No unnecessary client JavaScript or layout-shifting animation.
