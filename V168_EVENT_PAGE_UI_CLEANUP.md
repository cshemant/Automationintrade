# V168 Event Page UI Cleanup

## Removed from visitor-facing stock-trigger event pages

- The repeated fallback badge: `No monetary value was reliably extracted; verify the original filing.`
- The repeated score-card label: `Transparent model v2.0`
- The visitor-facing `Scoring model` row in Event facts.
- The empty `Financial magnitude` row when no reliable value is available.

## Behaviour retained

- Dynamic five-factor materiality scoring remains active.
- Data-confidence scoring remains active.
- Internal `scoreVersion` metadata remains available in generated JSON for maintenance and compatibility.
- When real monetary, per-share, or action-ratio data is extracted, it is still shown to users.
- The daily page builder applies this cleanup to all newly generated pages automatically.
