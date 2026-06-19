# Simple update flow

Use **one command** instead of running multiple scripts manually.

## Full update

```bash
python UpdateAllData.py --mode all
```

This runs:

1. `GenerateMarketToolsJson.py --mode all`
2. `GenerateTechnicalAnalysisJson.py`
3. `GenerateStockResearchIndex.py`

## Quick local test with only a few symbols

```bash
python UpdateAllData.py --mode research --technical-symbols MUTHOOTFIN,RELIANCE,TCS
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## Only rebuild homepage stock search index

```bash
python UpdateAllData.py --mode stock-index
```

## Only update market tools

```bash
python UpdateAllData.py --mode market
```

## Existing market-only modes still work

```bash
python UpdateAllData.py --mode fii-dii
python UpdateAllData.py --mode 52w
python UpdateAllData.py --mode index-performance
python UpdateAllData.py --mode stock-strength
python UpdateAllData.py --mode momentum-scanner
python UpdateAllData.py --mode volume-surge
python UpdateAllData.py --mode near-breakout
```

## Windows shortcut

Double-click or run:

```bat
UpdateAllData.bat
```

## GitHub Actions

The workflow now calls:

```bash
python UpdateAllData.py --mode "$MODE" --batch-size 80
```

So scheduled runs and manual runs use the same simplified flow.
