"""Publish generated premium research to D1, then remove its static JSON copies.
Requires CF_ACCOUNT_ID, CF_D1_DATABASE_ID, CF_D1_API_TOKEN in GitHub Actions.
Run after UpdateAllData.py --include-premium. Never put these secrets in the repo.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOLDERS = ('price-action', 'results', 'technical-analysis')
FREE_INDICES = {'NIFTY 50', 'NIFTY BANK', 'BANK NIFTY'}


def d1(sql, params=None):
    account = os.environ['CF_ACCOUNT_ID']
    database = os.environ['CF_D1_DATABASE_ID']
    token = os.environ['CF_D1_API_TOKEN']
    url = f'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query'
    body = json.dumps({'sql': sql, 'params': params or []}).encode()
    req = urllib.request.Request(url, body, headers={
        'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, method='POST')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.load(response)
            if not result.get('success') or any(not row.get('success') for row in result.get('result', [])):
                raise RuntimeError(f'D1 query failed: {result.get("errors")}')
            return
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise RuntimeError('D1 upload failed') from exc
            time.sleep(2 ** attempt)


def main():
    for name in ('CF_ACCOUNT_ID', 'CF_D1_DATABASE_ID', 'CF_D1_API_TOKEN'):
        if not os.environ.get(name):
            raise RuntimeError(f'Missing GitHub Actions secret {name}; refusing to publish premium JSON')
    index = json.loads((ROOT / 'market-data/stock-research-index.json').read_text())
    premium = {item['symbol'] for item in index['stocks']
               if item.get('accessTier') == 'premium' and
               not (set(map(str.upper, item.get('indices', []))) & FREE_INDICES)}
    if not premium:
        raise RuntimeError('Research index contains no premium stocks; refusing to change published files')
    d1('CREATE TABLE IF NOT EXISTS research_cards (symbol TEXT NOT NULL, view TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (symbol,view))')
    rows = []
    to_remove = []
    for folder in FOLDERS:
        base = ROOT / 'stock-research-data' / folder
        for symbol in sorted(premium):
            path = base / (symbol + '.json')
            if path.exists():
                payload = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError(f'Invalid research JSON: {path}')
                rows.append((symbol, folder, json.dumps(payload, separators=(',', ':'))))
                to_remove.append(path)
    if not rows:
        raise RuntimeError('No generated premium research JSON found; refusing to publish an empty research set')
    # Small batches stay within D1 parameter and SQL statement length limits.
    for i in range(0, len(rows), 5):
        batch = rows[i:i + 5]
        sql = ('INSERT INTO research_cards(symbol,view,payload) VALUES ' +
               ','.join('(?,?,?)' for _ in batch) +
               ' ON CONFLICT(symbol,view) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP')
        d1(sql, [value for row in batch for value in row])
    for path in to_remove:
        path.unlink()
    # Old public images can disclose research even after the JSON moves to D1.
    for folder in FOLDERS:
        for symbol in premium:
            for suffix in ('webp', 'png', 'jpg', 'jpeg'):
                path = ROOT / 'stock-research-data' / folder / f'{symbol}.{suffix}'
                if path.exists():
                    path.unlink()
    print(f'Synced {len(rows)} paid research cards to D1; removed public paid research assets from deploy tree')


if __name__ == '__main__':
    main()
