# V169 Stock Trigger Source and Filing Fix

## Fixed problems

1. **Broken “Original filing” links**
   - Date/time strings such as `31-Jul-2026 13:50:15` are no longer accepted as URLs.
   - The browser validates links before rendering them.
   - When a direct attachment is unavailable, the button is labelled **View on NSE** instead of incorrectly claiming to be the original filing.

2. **Malformed NSE CSV rows**
   - The generator now requests NSE JSON first.
   - CSV is retained only as a fallback and its schema quality is checked before rows are accepted.
   - Attachment URLs are recovered defensively only when they are genuine HTTP filing links or filing filenames.

3. **Generic/static press-release text**
   - Generic subjects such as `Press Release` are replaced with the actual disclosure title supplied by NSE.
   - For generic or low-detail announcements, the generator downloads the linked official PDF/HTML filing, extracts text, and selects source-backed key sentences.
   - Extracted summaries are labelled **Official filing text**. No financial figures are invented.

4. **Performance and resilience**
   - Filing extraction is capped per run and cached in `market-data/stock-trigger-filing-cache.json`.
   - `pypdf` is optional at runtime but included in `requirements.txt` for automated runs.
   - Existing malformed retained records are repaired and deduplicated during regeneration.

## Commands

Install/update dependencies once:

```powershell
pip install -r requirements.txt
```

Update Stock Triggers only:

```powershell
python UpdateAllData.py --mode stock-triggers
```

Update all website data:

```powershell
python UpdateAllData.py --mode all
```

The packaged JSON was repaired offline. Older records whose broken CSV rows did not contain a recoverable attachment now safely open the stock-filtered NSE announcement page. The next online update will fetch the current JSON rows, retain valid direct attachment URLs, and extract filing-backed summaries where available.
