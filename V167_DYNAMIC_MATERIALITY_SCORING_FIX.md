# V167 – Dynamic Materiality Scoring Fix

## Problem fixed

The earlier trigger score was largely derived from a category constant plus a few text checks. As a result, many records received the same score even when one filing contained a large order and another contained only an investor-call recording link.

## New model

Every trigger is recalculated on every daily run using five visible components:

1. Business materiality: 0–35
2. Evidence specificity: 0–20
3. Financial magnitude: 0–20
4. Market confirmation: 0–15
5. Recency or urgency: 0–10

The five components always add up to the displayed score out of 100.

A separate Data Confidence score is also generated. It measures source availability, filing detail and the number of concrete facts extracted. Confidence is not added to the materiality score.

## Important classification correction

Analyst meetings, conference calls, transcripts and recording links now use a separate `INVESTOR_MEETING` category. They are no longer treated as proof of institutional accumulation.

For the Varun Beverages example shown by the user, the new rules produce an informational score around 30/100 (the exact market-confirmation component can change daily), with zero financial-magnitude points when the filing only provides a recording link.

## Dynamic inputs

The score reads current values from the website's existing daily JSON files:

- `market-data/stock-strength-ranker.json`
- `market-data/volume-surge-scanner.json`
- `market-data/bullish-bearish-momentum-scanner.json`
- `market-data/stock-research-index.json`
- Fresh NSE announcement text and corporate-action data

Therefore, the score can change when the filing facts, price move, volume ratio, strength, urgency or available evidence changes.

## UI improvements

Each event page now displays:

- Materiality score and band
- Data confidence score
- Five-factor score breakdown with bars
- Exact reason for every component
- Financial magnitude extracted
- Current market-confirmation metrics
- Limitations that reduced materiality or confidence
- Scoring model version

The live feed cards and quick-detail dialog also show materiality band, confidence and the factor breakdown.

## Daily execution

No new cron is required. The existing command continues to update the feature:

```bash
python UpdateAllData.py --mode stock-triggers
```

The normal scheduled market workflow also runs the same generator. Retained records are re-scored with model v2.0 on every run, so old static scores do not remain in the 120-day history.
