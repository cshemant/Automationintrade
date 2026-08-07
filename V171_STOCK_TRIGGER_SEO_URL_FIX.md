# V171 - Stock Trigger SEO URL and Sitemap Stability Fix

## Canonical event URL policy

Event URLs now use a stable format that is independent of derived category, sentiment, materiality score, AI wording, and later classification changes:

`/stock-triggers/events/{company-name}-{yyyy-mm-dd}-{stable-id}/`

Example:

`/stock-triggers/events/lemon-tree-hotels-limited-2026-08-07-a52f04f14c1a/`

The short stable id is derived primarily from the original source path, exchange timestamp, and raw exchange subject. NSE sequence ids are stored as metadata but are not allowed to change an already migrated URL.

## Search continuity

- Previous V170 event URLs are retained in `market-data/stock-trigger-url-history.json`.
- Root `_redirects` contains permanent 301 redirects from every previous event URL to the new canonical URL.
- Event and stock page directories are no longer wiped on each cron run, so historical indexable pages do not become 404 merely because they leave the rolling feed.
- Canonical tags on event pages point to the stable URL.

## Sitemap behavior

`/sitemap-stock-triggers.xml` now contains only:

- `<loc>`
- truthful `<lastmod>`

`<changefreq>` and `<priority>` were removed because Google ignores them.

Only indexable event pages (materiality >= 55 with a usable source) are listed. Historical indexable event URLs remain registered in the sitemap even after they leave the current rolling feed.

## Cron / GitHub Actions

The workflow now commits all Stock Trigger SEO artifacts:

- `sitemap-stock-triggers.xml`
- `robots.txt`
- `_redirects`
- `stock-triggers/events/`
- `stock-triggers/category/`
- `stock-triggers/methodology/`
- `stocks/`
- `market-data/stock-trigger-pages-manifest.json`
- `market-data/stock-trigger-url-history.json`

Normal scheduled `UpdateAllData.py --mode market` runs therefore keep the sitemap, pages, canonicals and redirects in sync.
