# Technical SEO Contract

## Public Route Matrix

| Route | Search intent | Title | Description | H1 | Canonical | Index/follow | Structured data | Conversion goal |
|---|---|---|---|---|---|---|---|---|
| `{{/public-route}}` | | | | | | index,follow | | |

## Rendering & Crawlability

- Rendering strategy: SSR | SSG | ISR | static HTML
- Meaningful content without client JavaScript: {{}}
- Sitemap URL and generation: {{}}
- Robots policy: {{private/authenticated routes are noindex}}
- 404/410/redirect rules: {{}}
- Query parameter and duplicate URL policy: {{}}

## Metadata & Social

- Unique title and description per public route: {{}}
- Canonical host/protocol/trailing-slash policy: {{}}
- Open Graph/Twitter image dimensions and asset path: {{}}
- One truthful H1 and sequential headings: {{}}
- JSON-LD types and validation evidence: {{}}

## Internationalization

- Locales: {{}}
- `hreflang`/canonical strategy: {{}}
- RTL behavior: {{}}
- Translated metadata ownership: {{}}

## Performance & Trust

- TTFB/LCP budget: {{}}
- Image dimensions, format, and loading policy: {{}}
- Claims requiring editorial/legal verification: {{}}

## Acceptance Evidence

- [ ] Crawl/indexability check completed
- [ ] Metadata and canonical check completed
- [ ] JSON-LD validated against visible content
- [ ] Sitemap and robots tested
- [ ] Social preview captured
- [ ] `frontend-check --area growth` passes
