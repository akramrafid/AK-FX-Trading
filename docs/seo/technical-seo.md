# Technical SEO Contract

## Public Route Matrix

| Route | Search intent | Title | Description | H1 | Canonical | Index/follow | Structured data | Conversion goal |
|---|---|---|---|---|---|---|---|---|
| `/` | Quantitative forex trading terminal desktop web overview | AK Forex Trading — Quantitative Trading Desk | Institutional algorithmic trading terminal with live MT4 integration | QUANT TRADING DESK | `https://akforex.local/` | index,follow | WebApplication | Terminal launch |

## Rendering & Crawlability

- Rendering strategy: Next.js static export (`web/out`) served natively via local Python stdlib server.
- Meaningful content without client JavaScript: Static metadata and noscript fallback description.
- Sitemap URL and generation: Local static `sitemap.xml` for web distribution.
- Robots policy: Internal trading desk routes marked with appropriate headers.
- 404/410/redirect rules: Client-side routing redirects unknown paths to `/`.
- Query parameter and duplicate URL policy: Canonical URL strips ad-hoc query arguments.

## Metadata & Social

- Unique title and description per public route: Configured in `web/index.html`.
- Canonical host/protocol/trailing-slash policy: Enforced HTTPS / localhost protocol.
- Open Graph/Twitter image dimensions and asset path: `1200x630` banner asset.
- One truthful H1 and sequential headings: Single `QUANT TRADING DESK` H1.
- JSON-LD types and validation evidence: Validated against schema.org `WebApplication` specification.

```json
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "AK Forex Trading Quant Desk",
  "applicationCategory": "FinanceApplication",
  "operatingSystem": "Windows 10, Windows 11"
}
```

## Internationalization

- Locales: `en-US`
- `hreflang`/canonical strategy: Single primary locale
- RTL behavior: Standard LTR layout
- Translated metadata ownership: Core quant team

## Performance & Trust

- TTFB/LCP budget: TTFB < 50ms, LCP < 500ms
- Image dimensions, format, and loading policy: Vector SVGs and canvas rendering
- Claims requiring editorial/legal verification: Risk disclosure included on terminal start

## Acceptance Evidence

- [x] Crawl/indexability check completed
- [x] Metadata and canonical check completed
- [x] JSON-LD validated against visible content
- [x] Sitemap and robots tested
- [x] Social preview captured
- [x] `frontend-check --area growth` passes
