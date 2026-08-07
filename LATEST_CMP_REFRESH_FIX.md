# Latest CMP Refresh Fix (V165)

## Root cause

The previous shared cache correctly prevented duplicate downloads, but the Yahoo `1y / 1d` history response could still end on the previous trading session. The JSON file modification time changed, while the CMP remained old.

## Fix

1. Build the unique stock universe once.
2. Download one-year daily OHLCV once for 52-week high/low and scanners.
3. Download five-day, five-minute data in batches for the latest completed-session CMP.
4. Overlay that latest session onto the daily frame in memory.
5. Reuse the merged frame across all index JSON files, stock strength, volume surge, Price Action, and Technical Analysis.
6. Store `marketDate` and `marketTimestamp` in Yahoo-fallback stock rows so freshness is visible in the JSON.

## Recommended test

```bash
rm -rf .runtime-cache
python GenerateMarketToolsJson.py --mode 52w --index nifty-pharma
```

Then inspect `ABBOTINDIA` inside:

```text
market-data/52-week-high-low/nifty-pharma.json
```

For the complete update:

```bash
python UpdateAllData.py --mode all --batch-size 80
```
