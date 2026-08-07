# V170 - Dedicated Stock Triggers Sitemap

## Added
- Root-level `sitemap-stock-triggers.xml` generated automatically by `BuildStockTriggerPages.py`.
- Includes the Stock Triggers landing page, methodology, category pages, all generated `/stocks/<symbol>/` stock hubs, and quality-gated event pages.
- Event URLs are deduplicated before sitemap generation.
- `robots.txt` advertises both the main sitemap and the Stock Triggers sitemap.
- `market-data/stock-trigger-pages-manifest.json` records the dedicated sitemap path and URL count.

## Main sitemap behavior
The old generated Stock Trigger block is removed from `sitemap.xml`, so generated Stock Trigger URLs are reported through the dedicated sitemap instead of being duplicated in the main sitemap. The existing manually-listed `/stock-triggers/` landing URL remains in the main sitemap for backward compatibility.

## Why the sitemap is at the root
The stock-specific trigger hubs use `/stocks/<symbol>/`, which is outside `/stock-triggers/`. Keeping the dedicated sitemap at `/sitemap-stock-triggers.xml` allows it to validly list both `/stock-triggers/.../` and `/stocks/.../` URLs.

## Google Search Console
Submit:
`https://automationintrade.com/sitemap-stock-triggers.xml`

The normal sitemap remains:
`https://automationintrade.com/sitemap.xml`
