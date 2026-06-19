# Stock Research Search Setup

This version uses **lightweight JSON + HTML cards** instead of heavy generated images.

User flow:

1. Select analysis type: `Price Action`, `Results`, or `Technical Analysis`.
2. Search by stock name or symbol.
3. The website reads JSON and renders a clean HTML card instantly.

The static site does not run Python in the browser. Python/GitHub Actions generate small JSON outputs, and the browser only renders values from JSON.

## Output folders

```text
stock-research-data/price-action/{SYMBOL}.json
stock-research-data/results/{SYMBOL}.json
stock-research-data/technical-analysis/{SYMBOL}.json
```

## Technical Analysis JSON generation

Use this new command to generate detailed technical-analysis JSON files:

```bash
python GenerateTechnicalAnalysisJson.py
```

For quick local testing with only a few symbols:

```bash
python GenerateTechnicalAnalysisJson.py --symbols MUTHOOTFIN,RELIANCE,TCS
```

For a small batch test:

```bash
python GenerateTechnicalAnalysisJson.py --limit 10
```

The script reads the stock universe from:

```text
market-data/52-week-high-low/*.json
```

and writes detailed files to:

```text
stock-research-data/technical-analysis/{SYMBOL}.json
```

## Full local update order

```bash
python GenerateMarketToolsJson.py --mode all
python GenerateTechnicalAnalysisJson.py
python GenerateStockResearchIndex.py
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## Search index rebuild

After any stock research JSON files are generated, run:

```bash
python GenerateStockResearchIndex.py
```

This creates/updates:

```text
market-data/stock-research-index.json
```

## Example JSON shape

```json
{
  "view": "Positive / Watch Zone",
  "summary": "Technical analysis view with trend, RSI, volume, support/resistance and action zones rendered from JSON.",
  "metrics": [
    { "label": "Trend", "value": "Positive" },
    { "label": "Signal", "value": "Positive / Watch Zone" },
    { "label": "1D Move", "value": 0.42, "type": "percent" },
    { "label": "RSI", "value": "58.31" }
  ],
  "levels": [
    { "label": "Close", "value": 3528.9, "type": "price" },
    { "label": "Support", "value": 3420.2, "type": "price" },
    { "label": "Resistance", "value": 3610.2, "type": "price" },
    { "label": "Buy Zone", "value": "₹3,420.20 → ₹3,457.89" }
  ],
  "rows": [
    { "label": "Chart Mood", "value": "Positive setup; avoid chasing extended moves" },
    { "label": "Risk Note", "value": "Respect support if momentum weakens" },
    { "label": "Best Use", "value": "Technical zone reference" }
  ]
}
```

This keeps the site fast because it renders HTML from data instead of loading a 500 KB to 2 MB image for every stock.


## Simplified one-command update

Use this command for the full local update:

```bash
python UpdateAllData.py --mode all
```

This automatically runs market tools JSON, Technical Analysis research JSON, and the homepage stock research index in the correct order.

For quick research testing:

```bash
python UpdateAllData.py --mode research --technical-symbols MUTHOOTFIN,RELIANCE,TCS
```
