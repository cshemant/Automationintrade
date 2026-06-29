"""
GenerateMarketToolsJson.py
Single final hybrid script for Automation In Trade Market Tools JSON.

What this script does:
- Updates all JSON files under:
    market-data/52-week-high-low/
- Updates homepage snapshot:
    market-data/nse-snapshot.json
- Tries data sources in this order:
    1) Yahoo Finance using yfinance
    2) NSE quote API as fallback when accessible
    3) Previous JSON value as safe fallback
- Adds validation so wrong prices like split-adjusted / bad-source values are not blindly published.

Recommended daily workflow:
1. Put this file in the website root folder where index.html exists.
2. Install:
       pip install yfinance pandas requests
3. Run after market close:
       python GenerateMarketToolsJson_Final.py

   To update only FII/DII activity data:
       python GenerateMarketToolsJson_Final.py --only-fii-dii

   Optional modes:
       python GenerateMarketToolsJson_Final.py --mode all
       python GenerateMarketToolsJson_Final.py --mode fii-dii
       python GenerateMarketToolsJson_Final.py --mode index-performance
       python GenerateMarketToolsJson_Final.py --mode market-snapshot
       python GenerateMarketToolsJson_Final.py --mode 52w
       python GenerateMarketToolsJson_Final.py --mode stock-strength
       python GenerateMarketToolsJson_Final.py --mode volume-surge
       python GenerateMarketToolsJson_Final.py --mode near-breakout

4. Upload these updated paths as required:
       market-data/52-week-high-low/
       market-data/nse-snapshot.json
       market-data/fii-dii-activity.json
    market-data/stock-strength-ranker.json
       market-data/index-performance.json
       market-data/volume-surge-scanner.json
    market-data/near-breakout-scanner.json

Important:
- NSE may return 403 Forbidden. This is handled automatically.
- Yahoo may sometimes return bad/split-adjusted values. Validation is applied against previous JSON values.
- If both sources fail, the script preserves the previous JSON value instead of publishing blanks.
"""

import argparse
import json
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import pandas as pd
import requests
import yfinance as yf
import re


# ============================================================
# BASIC CONFIG
# ============================================================

WEBSITE_ROOT = Path(".")
JSON_FOLDER = WEBSITE_ROOT / "market-data" / "52-week-high-low"
MARKET_SNAPSHOT_FILE = WEBSITE_ROOT / "market-data" / "nse-snapshot.json"
FII_DII_ACTIVITY_FILE = WEBSITE_ROOT / "market-data" / "fii-dii-activity.json"
STOCK_STRENGTH_FILE = WEBSITE_ROOT / "market-data" / "stock-strength-ranker.json"
MOMENTUM_SCANNER_FILE = WEBSITE_ROOT / "market-data" / "bullish-bearish-momentum-scanner.json"
VOLUME_SURGE_FILE = WEBSITE_ROOT / "market-data" / "volume-surge-scanner.json"
NEAR_BREAKOUT_FILE = WEBSITE_ROOT / "market-data" / "near-breakout-scanner.json"
INDEX_PERFORMANCE_FILE = WEBSITE_ROOT / "market-data" / "index-performance.json"

# Constituents:
# True = try to download fresh constituent list from NiftyIndices CSV.
# If failed, existing JSON symbols are used.
TRY_DOWNLOAD_CONSTITUENTS = True

# Delay to reduce Yahoo/NSE rate-limit issues.
REQUEST_SLEEP_SECONDS = 0.45

# Yahoo historical period for 52-week high-low.
YFINANCE_PERIOD = "1y"
YFINANCE_INTERVAL = "1d"

# Price validation:
# If new CMP differs from previous JSON CMP by more than this %, it is considered suspicious.
# This prevents bad values like Havells 1200 becoming 4172.
MAX_REASONABLE_CMP_DIFF_PCT = 35

# If previous CMP is missing, this hard range check is used.
# Indian stock prices normally are not negative. Very tiny values are also ignored.
MIN_VALID_PRICE = 0.05

# If True, suspicious new values are replaced with previous JSON values.
# If previous JSON value is missing, suspicious source is still saved but marked Data Check Required.
PREFER_PREVIOUS_WHEN_SUSPICIOUS = True

DEFAULT_YAHOO_SUFFIX = ".NS"

MAX_NSE_RETRIES = 2


# ============================================================
# INDEX CONFIG
# ============================================================

INDEX_CONFIG = {
    "nifty-50": {
        "indexName": "NIFTY 50",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    },
    "nifty-midcap-50": {
        "indexName": "NIFTY MIDCAP 50",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap50list.csv",
    },
    "nifty-bank": {
        "indexName": "NIFTY BANK",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
    },
    "nifty-fmcg": {
        "indexName": "NIFTY FMCG",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyfmcglist.csv",
    },
    "nifty-auto": {
        "indexName": "NIFTY AUTO",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyautolist.csv",
    },
    "nifty-psu-bank": {
        "indexName": "NIFTY PSU BANK",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftypsubanklist.csv",
    },
    "nifty-pvt-bank": {
        "indexName": "NIFTY PVT BANK",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_nifty_privatebanklist.csv",
    },
    "nifty-next-50": {
        "indexName": "NIFTY NEXT 50",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
    },
    "nifty-100": {
        "indexName": "NIFTY 100",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    },
    "nifty-metal": {
        "indexName": "NIFTY METAL",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftymetallist.csv",
    },
    "nifty-pharma": {
        "indexName": "NIFTY PHARMA",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftypharmalist.csv",
    },
    "nifty-it": {
        "indexName": "NIFTY IT",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyitlist.csv",
    },
    "nifty-realty": {
        "indexName": "NIFTY REALTY",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyrealtylist.csv",
    },
    "nifty-infra": {
        "indexName": "NIFTY INFRA",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyinfralist.csv",
    },
    "nifty-energy": {
        "indexName": "NIFTY ENERGY",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyenergylist.csv",
    },
    "nifty-media": {
        "indexName": "NIFTY MEDIA",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftymedialist.csv",
    },
    "nifty-commodities": {
        "indexName": "NIFTY COMMODITIES",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftycommoditieslist.csv",
    },
    "nifty-financial-services": {
        "indexName": "NIFTY FINANCIAL SERVICES",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyfinancelist.csv",
    },
    "finnifty": {
        "indexName": "FINNIFTY",
        "csvUrl": "https://www.niftyindices.com/IndexConstituent/ind_niftyfinancelist.csv",
    },
    "sensex": {
        "indexName": "S&P BSE SENSEX",
        # Uses existing JSON symbols because this is BSE, not NiftyIndices.
        "csvUrl": None,
    },
}


# Homepage market strip symbols.
# Yahoo index symbols may fail for some indices. Previous JSON fallback is used.
MARKET_SNAPSHOT_YAHOO_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "MIDCAP SELECT": None,
    "INDIA VIX": "^INDIAVIX",
}


# Full-page index performance table.
# NSE allIndices is tried first. Yahoo Finance and previous JSON are used as safe fallbacks.
INDEX_PERFORMANCE_INDICES = [
    "NIFTY 50",
    "NIFTY MIDCAP 50",
    "NIFTY BANK",
    "NIFTY FMCG",
    "NIFTY AUTO",
    "NIFTY PSU BANK",
    "NIFTY PVT BANK",
    "NIFTY NEXT 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY METAL",
    "NIFTY PHARMA",
    "NIFTY IT",
    "NIFTY REALTY",
    "NIFTY INFRA",
    "NIFTY ENERGY",
    "NIFTY MEDIA",
    "NIFTY COMMODITIES",
    "NIFTY FINANCIAL SERVICES",
    "FINNIFTY",
    "S&P BSE SENSEX",
]

# Aliases help match NSE API naming variations.
INDEX_PERFORMANCE_NSE_ALIASES = {
    "NIFTY PVT BANK": ["NIFTY PRIVATE BANK"],
    "FINNIFTY": ["NIFTY FINANCIAL SERVICES"],
    "S&P BSE SENSEX": ["SENSEX", "BSE SENSEX", "S&P BSE SENSEX"],
}

# Yahoo symbols are only fallback. NSE allIndices should normally provide fresher data.
INDEX_PERFORMANCE_YAHOO_SYMBOLS = {
    "NIFTY 50": ["^NSEI"],
    "NIFTY BANK": ["^NSEBANK"],
    "NIFTY IT": ["^CNXIT", "NIFTY_IT.NS"],
    "NIFTY PHARMA": ["^CNXPHARMA"],
    "NIFTY AUTO": ["^CNXAUTO"],
    "NIFTY FMCG": ["^CNXFMCG"],
    "NIFTY METAL": ["^CNXMETAL"],
    "NIFTY REALTY": ["^CNXREALTY"],
    "NIFTY ENERGY": ["^CNXENERGY"],
    "NIFTY MEDIA": ["^CNXMEDIA"],
    "NIFTY INFRA": ["^CNXINFRA"],
    "S&P BSE SENSEX": ["^BSESN"],
}


# ============================================================
# NSE SESSION CONFIG
# ============================================================

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def create_nse_session():
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    for url in [
        "https://www.nseindia.com/",
        "https://www.nseindia.com/market-data/live-equity-market",
    ]:
        try:
            session.get(url, timeout=15)
            time.sleep(0.5)
        except Exception:
            pass

    return session


NSE_SESSION = create_nse_session()


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value.lower() in ["", "nan", "-", "none", "null"]:
                return None
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def round_or_none(value, digits=2):
    value = safe_float(value)
    if value is None:
        return None
    return round(value, digits)


def clean_symbol(symbol):
    return str(symbol).strip().upper()


def yahoo_symbol_for_nse(symbol):
    symbol = clean_symbol(symbol)
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}{DEFAULT_YAHOO_SUFFIX}"


def format_timestamp():
    return datetime.now().strftime("%d-%b-%Y %H:%M IST")


def read_json_file(path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def read_existing_json(slug):
    path = JSON_FOLDER / f"{slug}.json"
    return read_json_file(
        path,
        {
            "indexName": INDEX_CONFIG.get(slug, {}).get("indexName", slug.upper()),
            "slug": slug,
            "stocks": [],
        },
    )


def write_json(slug, payload):
    JSON_FOLDER.mkdir(parents=True, exist_ok=True)
    path = JSON_FOLDER / f"{slug}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")


def get_previous_stock_map(slug):
    data = read_existing_json(slug)
    result = {}
    for item in data.get("stocks", []):
        symbol = clean_symbol(item.get("symbol", ""))
        if symbol:
            result[symbol] = item
    return result



def is_publishable_stock_item(item):
    symbol = str(item.get("symbol", "")).strip().lower()
    name = str(item.get("stockName", "")).strip().lower()
    status = str(item.get("status", "")).strip().lower()

    def _num(v):
        try:
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    cmp_price = _num(item.get("cmp"))
    high52 = _num(item.get("high52"))
    low52 = _num(item.get("low52"))

    if "dummy" in symbol or "dummy" in name:
        return False
    if status in ["data unavailable", "unavailable"] or "data unavailable" in status:
        return False
    if cmp_price is None or cmp_price <= 0:
        return False
    if high52 is None or high52 <= 0:
        return False
    if low52 is None or low52 <= 0:
        return False

    return True


def get_existing_constituents(slug):
    data = read_existing_json(slug)
    rows = []
    for item in data.get("stocks", []):
        symbol = clean_symbol(item.get("symbol", ""))
        stock_name = str(item.get("stockName", symbol)).strip()
        if symbol and "DUMMY" not in symbol and "dummy" not in stock_name.lower():
            rows.append({"symbol": symbol, "stockName": stock_name})
    return rows


def calculate_status(down_from_high_pct, above_low_pct):
    if down_from_high_pct is None or above_low_pct is None:
        return "Data Unavailable"

    # Near low first because it is more actionable as a risk/context label.
    if above_low_pct <= 5:
        return "Near 52W Low"
    if down_from_high_pct <= -30:
        return "Deep Correction"
    if down_from_high_pct <= -15:
        return "Corrected"
    if down_from_high_pct >= -5:
        return "Near 52W High"
    return "Mid Range"


def add_calculated_fields(item):
    cmp_price = safe_float(item.get("cmp"))
    high52 = safe_float(item.get("high52"))
    low52 = safe_float(item.get("low52"))

    down_from_high_pct = ((cmp_price - high52) / high52) * 100 if cmp_price and high52 else None
    above_low_pct = ((cmp_price - low52) / low52) * 100 if cmp_price and low52 else None

    item["downFromHighPct"] = round_or_none(down_from_high_pct)
    item["aboveLowPct"] = round_or_none(above_low_pct)
    item["status"] = calculate_status(down_from_high_pct, above_low_pct)

    return item


# ============================================================
# CONSTITUENT LOADING
# ============================================================

def download_constituents_from_csv(csv_url):
    if not csv_url:
        return []

    headers = {
        "User-Agent": NSE_HEADERS["User-Agent"],
        "Accept": "text/csv,application/csv,text/plain,*/*",
        "Referer": "https://www.niftyindices.com/",
    }

    try:
        response = requests.get(csv_url, headers=headers, timeout=20)
        response.raise_for_status()

        from io import StringIO
        df = pd.read_csv(StringIO(response.text))
        df.columns = [str(col).strip() for col in df.columns]

        symbol_col = None
        name_col = None

        for col in df.columns:
            low = col.lower().strip()
            if low == "symbol":
                symbol_col = col
            if low in ["company name", "company", "name", "security name"]:
                name_col = col

        if symbol_col is None:
            return []

        rows = []
        for _, row in df.iterrows():
            symbol = clean_symbol(row.get(symbol_col, ""))
            stock_name = str(row.get(name_col, symbol)).strip() if name_col else symbol
            if symbol and symbol.lower() != "nan":
                rows.append({"symbol": symbol, "stockName": stock_name})

        return rows

    except Exception as e:
        print(f"Could not download constituents: {csv_url} -> {e}")
        return []


def get_constituents(slug):
    config = INDEX_CONFIG[slug]

    rows = []
    if TRY_DOWNLOAD_CONSTITUENTS and config.get("csvUrl"):
        rows = download_constituents_from_csv(config["csvUrl"])

    if not rows:
        print(f"Using existing JSON symbols for {slug}")
        rows = get_existing_constituents(slug)

    seen = set()
    unique_rows = []
    for row in rows:
        symbol = clean_symbol(row.get("symbol", ""))
        if symbol and symbol not in seen:
            seen.add(symbol)
            unique_rows.append({
                "symbol": symbol,
                "stockName": row.get("stockName", symbol),
            })

    return unique_rows


# ============================================================
# SOURCE 1: YAHOO FINANCE
# ============================================================

def fetch_from_yahoo(symbol, stock_name):
    yahoo_symbol = yahoo_symbol_for_nse(symbol)

    ticker = yf.Ticker(yahoo_symbol)
    hist = ticker.history(period=YFINANCE_PERIOD, interval=YFINANCE_INTERVAL, auto_adjust=False)

    if hist is None or hist.empty:
        raise ValueError("No Yahoo history data")

    hist = hist.dropna(subset=["High", "Low", "Close"])
    if hist.empty:
        raise ValueError("No valid Yahoo OHLC data")

    cmp_price = safe_float(hist["Close"].iloc[-1])
    prev_close = safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cmp_price
    high52 = safe_float(hist["High"].max())
    low52 = safe_float(hist["Low"].min())

    if cmp_price is None or cmp_price <= MIN_VALID_PRICE:
        raise ValueError("Invalid Yahoo CMP")

    change_pct = ((cmp_price - prev_close) / prev_close) * 100 if prev_close else None

    item = {
        "symbol": clean_symbol(symbol),
        "stockName": stock_name or symbol,
        "high52": round_or_none(high52),
        "low52": round_or_none(low52),
        "cmp": round_or_none(cmp_price),
        "changePct": round_or_none(change_pct),
        "source": "Yahoo",
        "dataQuality": "OK",
    }

    return add_calculated_fields(item)


# ============================================================
# SOURCE 2: NSE QUOTE API
# ============================================================

def nse_get_json(url):
    global NSE_SESSION

    last_error = None

    for attempt in range(1, MAX_NSE_RETRIES + 1):
        try:
            response = NSE_SESSION.get(url, timeout=20)

            if response.status_code in [401, 403]:
                NSE_SESSION = create_nse_session()
                response = NSE_SESSION.get(url, timeout=20)

            response.raise_for_status()
            return response.json()

        except Exception as e:
            last_error = e
            time.sleep(1.2 * attempt)

    raise RuntimeError(str(last_error))


def fetch_from_nse(symbol, stock_name):
    encoded_symbol = quote(clean_symbol(symbol), safe="")
    url = f"https://www.nseindia.com/api/quote-equity?symbol={encoded_symbol}"

    data = nse_get_json(url)
    price = data.get("priceInfo", {})

    cmp_price = safe_float(price.get("lastPrice"))
    prev_close = safe_float(price.get("previousClose"))
    p_change = safe_float(price.get("pChange"))

    week = price.get("weekHighLow", {}) or {}
    high52 = safe_float(week.get("max"))
    low52 = safe_float(week.get("min"))

    if high52 is None:
        high52 = safe_float(price.get("weekHighLowMax"))
    if low52 is None:
        low52 = safe_float(price.get("weekHighLowMin"))

    if cmp_price is None or cmp_price <= MIN_VALID_PRICE:
        raise ValueError("Invalid NSE CMP")

    if p_change is None and prev_close:
        p_change = ((cmp_price - prev_close) / prev_close) * 100

    company_name = data.get("info", {}).get("companyName") or stock_name or symbol

    item = {
        "symbol": clean_symbol(symbol),
        "stockName": company_name,
        "high52": round_or_none(high52),
        "low52": round_or_none(low52),
        "cmp": round_or_none(cmp_price),
        "changePct": round_or_none(p_change),
        "source": "NSE",
        "dataQuality": "OK",
    }

    return add_calculated_fields(item)


# ============================================================
# VALIDATION AND FALLBACK
# ============================================================

def cmp_diff_pct(new_cmp, previous_cmp):
    new_cmp = safe_float(new_cmp)
    previous_cmp = safe_float(previous_cmp)

    if new_cmp is None or previous_cmp is None or previous_cmp <= 0:
        return None

    return abs((new_cmp - previous_cmp) / previous_cmp) * 100


def looks_suspicious(item, previous_item):
    cmp_price = safe_float(item.get("cmp"))

    if cmp_price is None or cmp_price <= MIN_VALID_PRICE:
        return True, "CMP missing or invalid"

    high52 = safe_float(item.get("high52"))
    low52 = safe_float(item.get("low52"))

    if high52 is not None and low52 is not None:
        if low52 > high52:
            return True, "52W low greater than 52W high"
        if cmp_price > high52 * 1.20:
            return True, "CMP too far above 52W high"
        if cmp_price < low52 * 0.80:
            return True, "CMP too far below 52W low"

    if previous_item:
        previous_cmp = safe_float(previous_item.get("cmp"))
        diff = cmp_diff_pct(cmp_price, previous_cmp)

        if diff is not None and diff > MAX_REASONABLE_CMP_DIFF_PCT:
            return True, f"CMP differs from previous JSON by {round(diff, 2)}%"

    return False, ""


def build_from_previous(symbol, stock_name, previous_item, reason):
    if previous_item:
        item = dict(previous_item)
        item["symbol"] = clean_symbol(item.get("symbol", symbol))
        item["stockName"] = item.get("stockName") or stock_name or symbol
        item["source"] = "Previous JSON"
        item["dataQuality"] = f"Fallback: {reason}"
        return add_calculated_fields(item)

    return {
        "symbol": clean_symbol(symbol),
        "stockName": stock_name or symbol,
        "high52": None,
        "low52": None,
        "cmp": None,
        "changePct": None,
        "downFromHighPct": None,
        "aboveLowPct": None,
        "status": "Data Unavailable",
        "source": "None",
        "dataQuality": f"Unavailable: {reason}",
    }


def choose_best_stock_data(symbol, stock_name, previous_item):
    errors = []

    # Priority 1: Yahoo, because NSE quote API often blocks scripted requests.
    for source_name, fetcher in [
        ("Yahoo", fetch_from_yahoo),
        ("NSE", fetch_from_nse),
    ]:
        try:
            item = fetcher(symbol, stock_name)
            suspicious, reason = looks_suspicious(item, previous_item)

            if not suspicious:
                return item

            errors.append(f"{source_name} suspicious: {reason}")

            if previous_item and PREFER_PREVIOUS_WHEN_SUSPICIOUS:
                return build_from_previous(symbol, stock_name, previous_item, reason)

            item["dataQuality"] = f"Data Check Required: {reason}"
            item["status"] = "Data Check Required"
            return item

        except Exception as e:
            errors.append(f"{source_name} failed: {e}")

    return build_from_previous(symbol, stock_name, previous_item, " | ".join(errors))


# ============================================================
# INDEX JSON GENERATION
# ============================================================

def update_index_json(slug):
    config = INDEX_CONFIG[slug]
    index_name = config["indexName"]

    print(f"\nUpdating {index_name} ({slug})")

    constituents = get_constituents(slug)
    previous_map = get_previous_stock_map(slug)

    if not constituents:
        print(f"No constituents found for {slug}. Skipping.")
        return

    updated_stocks = []

    for i, row in enumerate(constituents, start=1):
        symbol = clean_symbol(row["symbol"])
        stock_name = row.get("stockName", symbol)
        previous_item = previous_map.get(symbol)

        print(f"  {i}/{len(constituents)} {symbol}")

        item = choose_best_stock_data(symbol, stock_name, previous_item)
        updated_stocks.append(item)

        time.sleep(REQUEST_SLEEP_SECONDS)

    updated_stocks = [item for item in updated_stocks if is_publishable_stock_item(item)]

    updated_stocks = sorted(
        updated_stocks,
        key=lambda x: x["downFromHighPct"] if x.get("downFromHighPct") is not None else 9999
    )

    payload = {
        "indexName": index_name,
        "slug": slug,
        "updatedAt": format_timestamp(),
        "sourceNote": (
            "Generated by Automation In Trade hybrid script. "
            "Primary source: Yahoo Finance via yfinance; fallback: NSE quote API where accessible; "
            "previous JSON used when live sources fail or look suspicious. Values may be delayed. "
            "Educational use only."
        ),
        "stocks": updated_stocks,
    }

    write_json(slug, payload)


# ============================================================
# HOMEPAGE MARKET SNAPSHOT
# ============================================================

def fetch_index_snapshot_from_yahoo(name, yahoo_symbol):
    if not yahoo_symbol:
        return None

    ticker = yf.Ticker(yahoo_symbol)
    hist = ticker.history(period="5d", interval="1d", auto_adjust=False)

    if hist is None or hist.empty:
        return None

    hist = hist.dropna(subset=["Close"])
    if hist.empty:
        return None

    last = safe_float(hist["Close"].iloc[-1])
    prev = safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last

    if last is None:
        return None

    change = last - prev if prev is not None else None
    change_pct = (change / prev) * 100 if prev else None

    return {
        "name": name,
        "value": round_or_none(last),
        "change": round_or_none(change),
        "changePct": round_or_none(change_pct),
        "source": "Yahoo",
    }


def fetch_market_snapshot_from_nse_all_indices():
    url = "https://www.nseindia.com/api/allIndices"
    data = nse_get_json(url)
    rows = data.get("data", [])

    required = {
        "NIFTY 50": "NIFTY 50",
        "NIFTY BANK": "BANK NIFTY",
        "NIFTY MIDCAP SELECT": "MIDCAP SELECT",
        "INDIA VIX": "INDIA VIX",
    }

    found = {}
    for row in rows:
        index_name = str(row.get("index", "")).strip().upper()
        if index_name in required:
            display_name = required[index_name]
            found[display_name] = {
                "name": display_name,
                "value": round_or_none(row.get("last")),
                "change": round_or_none(row.get("variation")),
                "changePct": round_or_none(row.get("percentChange")),
                "source": "NSE",
            }

    return found


def update_market_snapshot():
    print("\nUpdating homepage market snapshot")

    previous = read_json_file(MARKET_SNAPSHOT_FILE, {"indices": []})
    previous_items = {
        item.get("name"): item
        for item in previous.get("indices", [])
        if isinstance(item, dict)
    }

    nse_items = {}
    try:
        nse_items = fetch_market_snapshot_from_nse_all_indices()
    except Exception as e:
        print(f"NSE allIndices snapshot failed: {e}")

    final_items = []

    for name in ["NIFTY 50", "BANK NIFTY", "MIDCAP SELECT", "INDIA VIX"]:
        item = nse_items.get(name)

        if item is None:
            try:
                item = fetch_index_snapshot_from_yahoo(name, MARKET_SNAPSHOT_YAHOO_SYMBOLS.get(name))
            except Exception as e:
                print(f"Yahoo snapshot failed for {name}: {e}")
                item = None

        if item is None and name in previous_items:
            item = previous_items[name]
            item["source"] = "Previous JSON"

        if item is not None:
            final_items.append(item)

    MARKET_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "updatedAt": format_timestamp(),
        "sourceNote": "Generated by hybrid script using NSE/Yahoo with previous JSON fallback. Values may be delayed.",
        "indices": final_items,
    }

    with MARKET_SNAPSHOT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {MARKET_SNAPSHOT_FILE}")



# ============================================================
# FULL-PAGE INDEX PERFORMANCE SNAPSHOT
# ============================================================

def normalize_index_name(value):
    return " ".join(str(value or "").upper().replace("&", "AND").split())


def first_available_number(row, keys):
    for key in keys:
        if isinstance(row, dict) and key in row:
            value = safe_float(row.get(key))
            if value is not None:
                return value
    return None


def format_number(value):
    value = safe_float(value)
    if value is None:
        return "-"
    return f"{value:,.2f}"


def format_pct(value, show_plus=False):
    value = safe_float(value)
    if value is None:
        return "-"
    sign = "+" if show_plus and value > 0 else ""
    return f"{sign}{value:.1f}%"


def index_previous_map(previous_payload):
    result = {}
    for item in previous_payload.get("indices", []):
        if isinstance(item, dict) and item.get("name"):
            result[normalize_index_name(item.get("name"))] = item
    return result


def parse_nse_index_row(row):
    cmp_price = first_available_number(row, [
        "last", "lastPrice", "lastTradedPrice", "ltp", "indexValue", "value", "close"
    ])
    high52 = first_available_number(row, [
        "yearHigh", "yearlyHigh", "high52", "week52High", "52WeekHigh", "high52Week", "oneYearHigh"
    ])
    low52 = first_available_number(row, [
        "yearLow", "yearlyLow", "low52", "week52Low", "52WeekLow", "low52Week", "oneYearLow"
    ])
    change_pct = first_available_number(row, [
        "percentChange", "perChange", "pChange", "changePercent", "pctChange", "percentchange"
    ])

    # Some NSE responses may not include 52W fields for all indices.
    # In that case, the caller can still use Yahoo/previous JSON for those fields.
    return cmp_price, high52, low52, change_pct


def fetch_index_performance_from_nse_all_indices():
    data = nse_get_json("https://www.nseindia.com/api/allIndices")
    rows = data.get("data", data if isinstance(data, list) else [])

    row_map = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("index") or row.get("indexName") or row.get("name")
        normalized = normalize_index_name(name)
        if normalized:
            row_map[normalized] = row

    result = {}

    for display_name in INDEX_PERFORMANCE_INDICES:
        aliases = [display_name] + INDEX_PERFORMANCE_NSE_ALIASES.get(display_name, [])
        row = None
        for alias in aliases:
            row = row_map.get(normalize_index_name(alias))
            if row:
                break
        if not row:
            continue

        cmp_price, high52, low52, change_pct = parse_nse_index_row(row)
        if cmp_price is None:
            continue

        result[display_name] = {
            "name": display_name,
            "high52Num": high52,
            "low52Num": low52,
            "cmpNum": cmp_price,
            "chgNum": change_pct,
            "source": "NSE",
        }

    return result


def fetch_single_index_from_yahoo(display_name):
    candidates = INDEX_PERFORMANCE_YAHOO_SYMBOLS.get(display_name, [])

    for yahoo_symbol in candidates:
        try:
            ticker = yf.Ticker(yahoo_symbol)
            hist = ticker.history(period="1y", interval="1d", auto_adjust=False)
            if hist is None or hist.empty:
                continue
            hist = hist.dropna(subset=["High", "Low", "Close"])
            if hist.empty:
                continue

            cmp_price = safe_float(hist["Close"].iloc[-1])
            prev_close = safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cmp_price
            high52 = safe_float(hist["High"].max())
            low52 = safe_float(hist["Low"].min())

            if cmp_price is None or cmp_price <= MIN_VALID_PRICE:
                continue

            change_pct = ((cmp_price - prev_close) / prev_close) * 100 if prev_close else None

            return {
                "name": display_name,
                "high52Num": high52,
                "low52Num": low52,
                "cmpNum": cmp_price,
                "chgNum": change_pct,
                "source": "Yahoo",
            }
        except Exception as e:
            print(f"Yahoo index fallback failed for {display_name} ({yahoo_symbol}): {e}")

    return None


def merge_index_with_previous(display_name, live_item, previous_item):
    previous_item = previous_item or {}

    cmp_price = safe_float(live_item.get("cmpNum")) if live_item else None
    high52 = safe_float(live_item.get("high52Num")) if live_item else None
    low52 = safe_float(live_item.get("low52Num")) if live_item else None
    change_pct = safe_float(live_item.get("chgNum")) if live_item else None

    # Fill missing values from previous JSON so a partial NSE row does not publish blanks.
    if high52 is None:
        high52 = safe_float(previous_item.get("high52"))
    if low52 is None:
        low52 = safe_float(previous_item.get("low52"))
    if cmp_price is None:
        cmp_price = safe_float(previous_item.get("cmp"))
    if change_pct is None:
        change_pct = safe_float(str(previous_item.get("chg", "")).replace("%", ""))

    from_high = None
    if cmp_price is not None and high52 is not None and high52 > 0:
        from_high = ((cmp_price - high52) / high52) * 100
    else:
        from_high = safe_float(str(previous_item.get("fromHigh", "")).replace("%", ""))

    source = live_item.get("source") if live_item else "Previous JSON"

    return {
        "high52": format_number(high52),
        "low52": format_number(low52),
        "name": display_name,
        "cmp": format_number(cmp_price),
        "fromHigh": format_pct(from_high, show_plus=False),
        "chg": format_pct(change_pct, show_plus=True),
        "source": source,
    }


def calculate_index_market_mood(indices):
    positives = 0
    negatives = 0

    for item in indices:
        chg = safe_float(str(item.get("chg", "")).replace("%", ""))
        if chg is None:
            continue
        if chg > 0:
            positives += 1
        elif chg < 0:
            negatives += 1

    total = positives + negatives
    if total == 0:
        return "Data Updating"

    positive_ratio = positives / total
    if positive_ratio >= 0.65:
        return "Broadly Positive"
    if positive_ratio <= 0.35:
        return "Broadly Weak"
    return "Mixed Market"


def update_index_performance():
    print("\nUpdating full-page index performance snapshot")

    previous = read_json_file(INDEX_PERFORMANCE_FILE, {"indices": []})
    previous_items = index_previous_map(previous)

    nse_items = {}
    try:
        nse_items = fetch_index_performance_from_nse_all_indices()
        print(f"Fetched NSE allIndices rows for {len(nse_items)} indices")
    except Exception as e:
        print(f"NSE allIndices index performance failed: {e}")

    final_indices = []

    for display_name in INDEX_PERFORMANCE_INDICES:
        live_item = nse_items.get(display_name)

        # Yahoo fallback is useful for Sensex and some popular indices if NSE blocks or omits fields.
        if live_item is None or live_item.get("high52Num") is None or live_item.get("low52Num") is None:
            yahoo_item = fetch_single_index_from_yahoo(display_name)
            if yahoo_item:
                if live_item:
                    for key in ["high52Num", "low52Num", "cmpNum", "chgNum"]:
                        if live_item.get(key) is None:
                            live_item[key] = yahoo_item.get(key)
                    live_item["source"] = f"{live_item.get('source', 'NSE')} + Yahoo fallback"
                else:
                    live_item = yahoo_item

        previous_item = previous_items.get(normalize_index_name(display_name))
        final_indices.append(merge_index_with_previous(display_name, live_item, previous_item))
        time.sleep(0.15)

    market_mood = calculate_index_market_mood(final_indices)

    payload = {
        "title": "Index Performance",
        "date": datetime.now().strftime("%d %B %Y"),
        "marketMood": market_mood,
        "updatedAt": format_timestamp(),
        "sourceNote": (
            "Generated by Automation In Trade hybrid script. Primary source: NSE allIndices; "
            "fallback: Yahoo Finance where available; previous JSON used when live source is unavailable. "
            "Values may be delayed. Educational use only."
        ),
        "indices": final_indices,
    }

    INDEX_PERFORMANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PERFORMANCE_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {INDEX_PERFORMANCE_FILE}")

# ============================================================
# FII / DII ACTIVITY SNAPSHOT
# ============================================================

def parse_nse_date(value):
    if not value:
        return None

    value = str(value).strip()

    for fmt in ["%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    return None


def nse_get_text(url):
    global NSE_SESSION

    last_error = None

    for attempt in range(1, MAX_NSE_RETRIES + 1):
        try:
            response = NSE_SESSION.get(url, timeout=20)

            if response.status_code in [401, 403]:
                NSE_SESSION = create_nse_session()
                response = NSE_SESSION.get(url, timeout=20)

            response.raise_for_status()
            return response.text

        except Exception as e:
            last_error = e
            time.sleep(1.2 * attempt)

    raise RuntimeError(str(last_error))


def normalize_column_name(col):
    return (
        str(col)
        .replace("\n", " ")
        .replace("₹", "")
        .replace("( Crores )", "")
        .replace("(₹ Crores)", "")
        .replace("(₹ Crores )", "")
        .replace("  ", " ")
        .strip()
        .lower()
    )


def parse_money_value(value):
    value = str(value).replace(",", "").replace("₹", "").replace("Cr", "").strip()
    return round_or_none(value, 2)


def build_fii_dii_payload_from_rows(dii_row, fii_row):
    latest_date = parse_nse_date(dii_row["date"])

    if latest_date is None:
        raise ValueError(f"Could not parse FII/DII date: {dii_row['date']}")

    final_rows = [
        {
            "category": "DII",
            "buyValue": parse_money_value(dii_row["buy"]),
            "sellValue": parse_money_value(dii_row["sell"]),
            "netValue": parse_money_value(dii_row["net"]),
        },
        {
            "category": "FII/FPI",
            "buyValue": parse_money_value(fii_row["buy"]),
            "sellValue": parse_money_value(fii_row["sell"]),
            "netValue": parse_money_value(fii_row["net"]),
        },
    ]

    total_net = sum(safe_float(row["netValue"]) or 0 for row in final_rows)
    headline = f"Net {'Inflow' if total_net >= 0 else 'Outflow'} ₹{abs(round(total_net)):,} Cr"

    return {
        "date": latest_date.strftime("%d-%b-%Y"),
        "headline": headline,
        "updatedAt": format_timestamp(),
        "sourceNote": "Generated from NSE-only FII/FPI & DII Capital Market Segment table. Values may be delayed.",
        "categories": final_rows,
    }


def fetch_fii_dii_from_api():
    """
    NSE API sometimes gives stale data, but when it is fresh,
    this is faster than browser scraping.
    """
    data = nse_get_json("https://www.nseindia.com/api/fiidiiTradeReact")

    if not isinstance(data, list):
        data = data.get("data", [])

    dii_row = None
    fii_row = None

    for row in data:
        category = str(row.get("category", "")).strip().upper()

        item = {
            "date": row.get("date", ""),
            "buy": row.get("buyValue"),
            "sell": row.get("sellValue"),
            "net": row.get("netValue"),
        }

        if category == "DII":
            dii_row = item
        elif "FII" in category or "FPI" in category:
            fii_row = item

    if not dii_row or not fii_row:
        raise ValueError("API did not return both DII and FII/FPI rows")

    return build_fii_dii_payload_from_rows(dii_row, fii_row)


def parse_fii_dii_rows_from_text(block_text):
    """
    Parse NSE-only FII/DII rows from rendered text.
    Works even when Selenium returns table text as one long string.
    """
    text = " ".join(str(block_text or "").replace("\xa0", " ").split())

    # Expected pattern:
    # DII 27-May-2026 14,690.91 11,265.52 3,425.39
    # FII/FPI 27-May-2026 11,084.46 11,739.95 -655.49
    row_pattern = re.compile(
        r"\b(DII|FII/FPI)\b\s+"
        r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+"
        r"(-?[\d,]+(?:\.\d+)?)\s+"
        r"(-?[\d,]+(?:\.\d+)?)\s+"
        r"(-?[\d,]+(?:\.\d+)?)",
        re.IGNORECASE
    )

    rows = []
    for match in row_pattern.finditer(text):
        rows.append({
            "category": match.group(1).upper(),
            "date": match.group(2),
            "buy": match.group(3),
            "sell": match.group(4),
            "net": match.group(5),
        })

    dii_row = None
    fii_row = None

    for row in rows:
        category = row["category"].upper()
        if category == "DII":
            dii_row = row
        elif "FII" in category or "FPI" in category:
            fii_row = row

    if dii_row and fii_row:
        return dii_row, fii_row

    return None, None


def fetch_fii_dii_from_selenium():
    """
    Browser-rendered fallback.

    IMPORTANT:
    The NSE page has two similar tables:
    1) NSE-only Capital Market Segment
    2) Combined NSE, BSE and MSEI Capital Market Segment

    This function reads the FIRST VISIBLE table containing DII and FII/FPI rows.
    On the NSE page, that first visible table is the NSE-only table that you circled.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = Options()

    # Keep headless. If NSE layout changes, you can temporarily comment this line
    # to see the browser while debugging.
    options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--user-agent=" + NSE_HEADERS["User-Agent"])

    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://www.nseindia.com/reports/fii-dii")

        WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Wait until DII/FII text appears. This is stronger than waiting only for <table>.
        WebDriverWait(driver, 45).until(
            lambda d: ("DII" in d.find_element(By.TAG_NAME, "body").text and "FII" in d.find_element(By.TAG_NAME, "body").text)
        )

        time.sleep(4)

        # Scroll a little so lazy-rendered report tables are definitely in DOM.
        driver.execute_script("window.scrollTo(0, 420);")
        time.sleep(1.5)

        tables = driver.find_elements(By.TAG_NAME, "table")

        visible_candidates = []

        for table in tables:
            try:
                info = driver.execute_script("""
                    const t = arguments[0];
                    const r = t.getBoundingClientRect();
                    const s = window.getComputedStyle(t);
                    return {
                        text: t.innerText || "",
                        top: r.top,
                        width: r.width,
                        height: r.height,
                        display: s.display,
                        visibility: s.visibility,
                        opacity: s.opacity
                    };
                """, table)

                text = info.get("text", "")
                width = float(info.get("width") or 0)
                height = float(info.get("height") or 0)
                display = str(info.get("display", ""))
                visibility = str(info.get("visibility", ""))
                opacity = str(info.get("opacity", ""))

                if display == "none" or visibility == "hidden" or opacity == "0":
                    continue

                if width <= 100 or height <= 20:
                    continue

                if "DII" not in text or "FII" not in text:
                    continue

                dii_row, fii_row = parse_fii_dii_rows_from_text(text)
                if dii_row and fii_row:
                    visible_candidates.append((float(info.get("top") or 999999), dii_row, fii_row, text))

            except Exception:
                continue

        if visible_candidates:
            # First visible matching table on screen = NSE-only table.
            visible_candidates.sort(key=lambda x: x[0])
            dii_row, fii_row = visible_candidates[0][1], visible_candidates[0][2]
            return build_fii_dii_payload_from_rows(dii_row, fii_row)

        # Fallback: parse page section text between first and second headings.
        page_text = driver.find_element(By.TAG_NAME, "body").text
        page_text_clean = " ".join(page_text.replace("\xa0", " ").split())

        first_heading = "FII/FPI & DII trading activity on NSE in Capital Market Segment"
        second_heading = "FII/FPI & DII trading activity on NSE, BSE and MSEI in Capital Market Segment"

        first_pos = page_text_clean.find(first_heading)
        second_pos = page_text_clean.find(second_heading)

        if first_pos == -1:
            # final fallback: parse first DII/FII pair on the page
            dii_row, fii_row = parse_fii_dii_rows_from_text(page_text_clean)
        else:
            if second_pos == -1 or second_pos <= first_pos:
                first_section_text = page_text_clean[first_pos:]
            else:
                first_section_text = page_text_clean[first_pos:second_pos]

            dii_row, fii_row = parse_fii_dii_rows_from_text(first_section_text)

        if not dii_row or not fii_row:
            raise ValueError("Could not parse NSE-only FII/DII rows from rendered page")

        return build_fii_dii_payload_from_rows(dii_row, fii_row)

    finally:
        driver.quit()


def update_fii_dii_activity():
    print("\nUpdating FII/DII activity snapshot")

    previous = read_json_file(FII_DII_ACTIVITY_FILE, {
        "date": format_timestamp(),
        "headline": "FII / DII Activity",
        "updatedAt": format_timestamp(),
        "categories": []
    })

    payload = None
    errors = []

    try:
        payload = fetch_fii_dii_from_selenium()
        print(f"Fetched NSE-only FII/DII from rendered NSE page: {payload.get('date')}")
    except Exception as e:
        errors.append(f"API failed: {e}")
        print(f"API failed: {e}")

    # If API gives stale data compared to previous JSON date, try Selenium.
    try_selenium = False

    if payload is None:
        try_selenium = True
    else:
        new_date = parse_nse_date(payload.get("date"))
        old_date = parse_nse_date(previous.get("date"))

        if old_date is not None and new_date is not None and new_date < old_date:
            print("API returned older data than previous JSON. Trying Selenium...")
            try_selenium = True

    if try_selenium:
        try:
            payload = fetch_fii_dii_from_selenium()
            print(f"Fetched FII/DII from rendered NSE page: {payload.get('date')}")
        except Exception as e:
            errors.append(f"Selenium failed: {e}")
            print(f"Selenium failed: {e}")

    if payload is None:
        print("FII/DII update failed, using previous JSON:", " | ".join(errors))
        payload = previous
        payload["updatedAt"] = previous.get("updatedAt") or format_timestamp()
        payload["sourceNote"] = "Previous JSON fallback. Refresh from verified FII/DII data source."

    FII_DII_ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with FII_DII_ACTIVITY_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {FII_DII_ACTIVITY_FILE}")


# ============================================================
# AIT STOCK STRENGTH RANKER
# ============================================================

def clamp_number(value, low=0, high=100):
    value = safe_float(value)
    if value is None:
        return low
    return max(low, min(high, value))


def percentile_ranker(values):
    clean_values = sorted([v for v in values if v is not None])

    def rank(value):
        value = safe_float(value)
        if value is None or not clean_values:
            return 50.0
        if len(clean_values) == 1:
            return 50.0
        below = sum(1 for v in clean_values if v < value)
        return (below / (len(clean_values) - 1)) * 100

    return rank


def build_stock_strength_rows_from_52w_json():
    universe = {}
    latest_updated_at = None

    if not JSON_FOLDER.exists():
        return [], latest_updated_at

    for path in sorted(JSON_FOLDER.glob("*.json")):
        data = read_json_file(path, {})
        index_name = data.get("indexName") or path.stem
        if data.get("updatedAt") and latest_updated_at is None:
            latest_updated_at = data.get("updatedAt")

        for stock in data.get("stocks", []):
            symbol = clean_symbol(stock.get("symbol", ""))
            stock_name = str(stock.get("stockName") or symbol).strip()
            if not symbol or "DUMMY" in symbol or "dummy" in stock_name.lower():
                continue

            cmp_price = safe_float(stock.get("cmp"))
            high52 = safe_float(stock.get("high52"))
            low52 = safe_float(stock.get("low52"))
            if not cmp_price or cmp_price <= 0 or not high52 or high52 <= 0 or not low52 or low52 <= 0:
                continue

            item = universe.setdefault(symbol, {
                "symbol": symbol,
                "stockName": stock_name,
                "cmp": round_or_none(cmp_price),
                "high52": round_or_none(high52),
                "low52": round_or_none(low52),
                "changePct": round_or_none(stock.get("changePct")),
                "downFromHighPct": round_or_none(stock.get("downFromHighPct")),
                "aboveLowPct": round_or_none(stock.get("aboveLowPct")),
                "status": stock.get("status") or "",
                "indices": [],
            })

            if index_name not in item["indices"]:
                item["indices"].append(index_name)

            # Keep latest values from whichever index JSON is currently being read.
            for key in ["cmp", "high52", "low52", "changePct", "downFromHighPct", "aboveLowPct"]:
                value = safe_float(stock.get(key))
                if value is not None:
                    item[key] = round_or_none(value)
            item["stockName"] = stock_name or item["stockName"]
            item["status"] = stock.get("status") or item.get("status") or ""

    rows = list(universe.values())
    daily_rank = percentile_ranker([safe_float(row.get("changePct")) for row in rows])

    for row in rows:
        change_pct = safe_float(row.get("changePct"))
        down_from_high = safe_float(row.get("downFromHighPct"))
        above_low = safe_float(row.get("aboveLowPct"))

        # Score design:
        # 38% daily relative momentum, 34% 52W high proximity,
        # 18% distance from 52W low, 10% broad-index membership/liquidity proxy.
        momentum_score = daily_rank(change_pct) * 0.38
        high_proximity_score = clamp_number(100 + (down_from_high if down_from_high is not None else -50), 0, 100) * 0.34
        low_distance_score = clamp_number(above_low, 0, 100) * 0.18
        index_bonus = min(len(row.get("indices", [])), 4) / 4 * 10

        score = round(momentum_score + high_proximity_score + low_distance_score + index_bonus, 1)
        row["strengthScore"] = score
        row["indices"] = sorted(row.get("indices", []))[:6]

        if score >= 78:
            row["signal"] = "Strong Momentum"
        elif score >= 65:
            row["signal"] = "Positive Watchlist"
        elif score >= 50:
            row["signal"] = "Neutral / Stable"
        elif score >= 35:
            row["signal"] = "Weak / Corrected"
        else:
            row["signal"] = "High Weakness"

    rows = sorted(rows, key=lambda item: safe_float(item.get("strengthScore")) or 0, reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    return rows, latest_updated_at


def update_stock_strength_ranker():
    print("\nUpdating AIT Stock Strength Ranker")
    previous = read_json_file(STOCK_STRENGTH_FILE, {})
    rows, latest_updated_at = build_stock_strength_rows_from_52w_json()

    if not rows and previous.get("stocks"):
        print("Stock strength update failed, using previous JSON.")
        payload = previous
        payload["updatedAt"] = previous.get("updatedAt") or format_timestamp()
    else:
        payload = {
            "toolName": "AIT Stock Strength Ranker",
            "updatedAt": latest_updated_at or format_timestamp(),
            "generatedAt": format_timestamp(),
            "universeCount": len(rows),
            "sourceNote": (
                "Generated from existing Automation In Trade 52-week high-low JSON files. "
                "Strength score combines daily move percentile, 52-week high proximity, "
                "distance from 52-week low, and index membership. Educational use only."
            ),
            "stocks": rows,
        }

    STOCK_STRENGTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STOCK_STRENGTH_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {STOCK_STRENGTH_FILE}")


def classify_momentum_bias(row):
    change_pct = safe_float(row.get("changePct")) or 0
    strength_score = safe_float(row.get("strengthScore")) or 0

    if change_pct >= 1.0 and strength_score >= 65:
        return "Bullish Momentum", round(strength_score + min(change_pct * 2, 12), 1)
    if change_pct <= -1.0 and strength_score <= 45:
        return "Bearish Momentum", round((100 - strength_score) + min(abs(change_pct) * 2, 12), 1)
    if change_pct >= 1.0 and strength_score < 50:
        return "Reversal Watch", round(55 + min(change_pct * 3, 18), 1)
    if change_pct <= -1.0 and strength_score > 55:
        return "Pullback Watch", round(55 + min(abs(change_pct) * 2, 14), 1)
    return "Neutral", round(strength_score, 1)


def build_momentum_rows_from_strength_rows(strength_rows):
    rows = []
    for source_row in strength_rows:
        if safe_float(source_row.get("cmp")) is None:
            continue
        bias, momentum_score = classify_momentum_bias(source_row)
        if bias == "Neutral":
            continue
        rows.append({
            "symbol": source_row.get("symbol"),
            "stockName": source_row.get("stockName"),
            "indices": source_row.get("indices", []),
            "cmp": round_or_none(source_row.get("cmp")),
            "changePct": round_or_none(source_row.get("changePct")),
            "downFromHighPct": round_or_none(source_row.get("downFromHighPct")),
            "aboveLowPct": round_or_none(source_row.get("aboveLowPct")),
            "strengthScore": round_or_none(source_row.get("strengthScore"), 1),
            "momentumScore": momentum_score,
            "bias": bias,
        })

    bias_order = {
        "Bullish Momentum": 0,
        "Bearish Momentum": 1,
        "Reversal Watch": 2,
        "Pullback Watch": 3,
    }
    rows = sorted(rows, key=lambda item: (bias_order.get(item.get("bias"), 9), -(safe_float(item.get("momentumScore")) or 0)))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def update_bullish_bearish_momentum_scanner():
    print("\nUpdating Bullish/Bearish Momentum Scanner")
    previous = read_json_file(MOMENTUM_SCANNER_FILE, {})

    strength_payload = read_json_file(STOCK_STRENGTH_FILE, {})
    strength_rows = strength_payload.get("stocks", []) if isinstance(strength_payload, dict) else []

    if not strength_rows:
        try:
            strength_rows, latest_updated_at = build_stock_strength_rows_from_52w_json()
        except Exception:
            strength_rows, latest_updated_at = [], None
    else:
        latest_updated_at = strength_payload.get("updatedAt")

    rows = build_momentum_rows_from_strength_rows(strength_rows)

    if not rows and previous.get("stocks"):
        print("Momentum scanner update failed, using previous JSON.")
        payload = previous
        payload["updatedAt"] = previous.get("updatedAt") or format_timestamp()
    else:
        payload = {
            "toolName": "Bullish/Bearish Momentum Scanner",
            "updatedAt": latest_updated_at or format_timestamp(),
            "generatedAt": format_timestamp(),
            "universeCount": len(strength_rows),
            "signalCount": len(rows),
            "sourceNote": (
                "Generated from AIT Stock Strength Ranker and existing 52-week high-low JSON files. "
                "Signals use daily move, strength score and 52-week position. Educational use only."
            ),
            "stocks": rows,
        }

    MOMENTUM_SCANNER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MOMENTUM_SCANNER_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {MOMENTUM_SCANNER_FILE}")


# ============================================================
# VOLUME SURGE SCANNER
# ============================================================

def fetch_volume_metrics_from_yahoo(symbol):
    yahoo_symbol = yahoo_symbol_for_nse(symbol)
    ticker = yf.Ticker(yahoo_symbol)
    hist = ticker.history(period="45d", interval="1d", auto_adjust=False)

    if hist is None or hist.empty or "Volume" not in hist.columns:
        raise ValueError("No Yahoo volume history")

    hist = hist.dropna(subset=["Close", "Volume"])
    hist = hist[hist["Volume"] > 0]
    if len(hist) < 8:
        raise ValueError("Not enough valid volume history")

    last_volume = safe_float(hist["Volume"].iloc[-1])
    prev_volumes = hist["Volume"].iloc[:-1].tail(20)
    avg_volume_20 = safe_float(prev_volumes.mean()) if len(prev_volumes) else None
    last_close = safe_float(hist["Close"].iloc[-1])
    prev_close = safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last_close

    if not last_volume or not avg_volume_20 or avg_volume_20 <= 0:
        raise ValueError("Invalid volume values")

    change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else None

    return {
        "volume": round_or_none(last_volume, 0),
        "avgVolume20": round_or_none(avg_volume_20, 0),
        "volumeSurgeRatio": round_or_none(last_volume / avg_volume_20, 2),
        "changePctFromVolumeSource": round_or_none(change_pct),
        "volumeSource": "Yahoo",
    }


def classify_volume_surge(row):
    ratio = safe_float(row.get("volumeSurgeRatio"))
    change_pct = safe_float(row.get("changePct")) or 0
    strength_score = safe_float(row.get("strengthScore")) or 50

    if ratio is None:
        return "Volume Watchlist", round(clamp_number(abs(change_pct) * 8 + strength_score * 0.35, 0, 100), 1)

    base = clamp_number(ratio * 28, 0, 60)
    move_component = min(abs(change_pct) * 5, 22)
    strength_component = clamp_number(strength_score, 0, 100) * 0.18
    volume_score = round(clamp_number(base + move_component + strength_component, 0, 100), 1)

    if ratio >= 1.5 and change_pct >= 0.5:
        return "Bullish Volume Surge", volume_score
    if ratio >= 1.5 and change_pct <= -0.5:
        return "Bearish Volume Surge", volume_score
    if ratio >= 1.3 and change_pct >= 0.8 and strength_score < 55:
        return "High Volume Reversal", volume_score
    if ratio >= 1.2:
        return "Volume Watchlist", volume_score
    return "Neutral", volume_score


def build_volume_surge_rows_from_strength_rows(strength_rows, previous_rows=None):
    previous_rows = previous_rows or []
    previous_map = {clean_symbol(row.get("symbol", "")): row for row in previous_rows if row.get("symbol")}
    rows = []

    for i, source_row in enumerate(strength_rows, start=1):
        symbol = clean_symbol(source_row.get("symbol", ""))
        if not symbol or safe_float(source_row.get("cmp")) is None:
            continue

        row = {
            "symbol": symbol,
            "stockName": source_row.get("stockName"),
            "indices": source_row.get("indices", []),
            "cmp": round_or_none(source_row.get("cmp")),
            "changePct": round_or_none(source_row.get("changePct")),
            "downFromHighPct": round_or_none(source_row.get("downFromHighPct")),
            "aboveLowPct": round_or_none(source_row.get("aboveLowPct")),
            "strengthScore": round_or_none(source_row.get("strengthScore"), 1),
        }

        try:
            metrics = fetch_volume_metrics_from_yahoo(symbol)
            row.update(metrics)
            if row.get("changePct") is None and metrics.get("changePctFromVolumeSource") is not None:
                row["changePct"] = metrics.get("changePctFromVolumeSource")
        except Exception as e:
            prev = previous_map.get(symbol)
            if prev:
                for key in ["volume", "avgVolume20", "volumeSurgeRatio", "volumeSource"]:
                    row[key] = prev.get(key)
                row["volumeSource"] = "Previous JSON"
            else:
                row["volume"] = None
                row["avgVolume20"] = None
                row["volumeSurgeRatio"] = None
                row["volumeSource"] = f"Unavailable: {e}"

        signal, volume_score = classify_volume_surge(row)
        if signal == "Neutral":
            continue
        row["signal"] = signal
        row["volumeScore"] = volume_score
        rows.append(row)
        time.sleep(REQUEST_SLEEP_SECONDS)

    signal_order = {
        "Bullish Volume Surge": 0,
        "Bearish Volume Surge": 1,
        "High Volume Reversal": 2,
        "Volume Watchlist": 3,
    }
    rows = sorted(rows, key=lambda item: (signal_order.get(item.get("signal"), 9), -(safe_float(item.get("volumeScore")) or 0)))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def update_volume_surge_scanner():
    print("\nUpdating Volume Surge Scanner")
    previous = read_json_file(VOLUME_SURGE_FILE, {})

    strength_payload = read_json_file(STOCK_STRENGTH_FILE, {})
    strength_rows = strength_payload.get("stocks", []) if isinstance(strength_payload, dict) else []

    if not strength_rows:
        try:
            strength_rows, latest_updated_at = build_stock_strength_rows_from_52w_json()
        except Exception:
            strength_rows, latest_updated_at = [], None
    else:
        latest_updated_at = strength_payload.get("updatedAt")

    rows = build_volume_surge_rows_from_strength_rows(strength_rows, previous.get("stocks", []))

    if not rows and previous.get("stocks"):
        print("Volume surge scanner update failed, using previous JSON.")
        payload = previous
        payload["updatedAt"] = previous.get("updatedAt") or format_timestamp()
    else:
        payload = {
            "toolName": "Volume Surge Scanner",
            "updatedAt": latest_updated_at or format_timestamp(),
            "generatedAt": format_timestamp(),
            "universeCount": len(strength_rows),
            "signalCount": len(rows),
            "sourceNote": (
                "Generated from AIT Stock Strength Ranker universe with Yahoo Finance volume history. "
                "Volume surge ratio compares latest volume with 20-day average volume. Educational use only."
            ),
            "stocks": rows,
        }

    VOLUME_SURGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with VOLUME_SURGE_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {VOLUME_SURGE_FILE}")


# ============================================================
# NEAR BREAKOUT SCANNER
# ============================================================

def classify_near_breakout(row):
    cmp_price = safe_float(row.get("cmp"))
    high52 = safe_float(row.get("high52"))
    change_pct = safe_float(row.get("changePct")) or 0
    strength_score = safe_float(row.get("strengthScore")) or 50

    if cmp_price is None or high52 is None or high52 <= 0:
        return "Data Unavailable", None, 0

    breakout_gap = ((high52 - cmp_price) / high52) * 100
    proximity_component = clamp_number(100 - max(breakout_gap, 0) * 10, 0, 100) * 0.52
    momentum_component = clamp_number(change_pct * 10, -20, 25)
    strength_component = clamp_number(strength_score, 0, 100) * 0.33
    score = round(clamp_number(proximity_component + strength_component + momentum_component, 0, 100), 1)

    if breakout_gap <= 0:
        return "Fresh Breakout", round_or_none(breakout_gap), max(score, 92)
    if breakout_gap <= 1.5 and change_pct >= 0.25:
        return "Near Breakout", round_or_none(breakout_gap), score
    if breakout_gap <= 4 and change_pct >= 1.0 and strength_score >= 60:
        return "Breakout Watch", round_or_none(breakout_gap), score
    if breakout_gap <= 3 and change_pct < 0:
        return "Retest Near High", round_or_none(breakout_gap), score
    if breakout_gap <= 6 and change_pct >= 2.0:
        return "Momentum Breakout Watch", round_or_none(breakout_gap), score

    return "Neutral", round_or_none(breakout_gap), score


def build_near_breakout_rows_from_strength_rows(strength_rows):
    rows = []
    for source_row in strength_rows:
        symbol = clean_symbol(source_row.get("symbol", ""))
        if not symbol or safe_float(source_row.get("cmp")) is None:
            continue

        row = {
            "symbol": symbol,
            "stockName": source_row.get("stockName"),
            "indices": source_row.get("indices", []),
            "cmp": round_or_none(source_row.get("cmp")),
            "high52": round_or_none(source_row.get("high52")),
            "low52": round_or_none(source_row.get("low52")),
            "changePct": round_or_none(source_row.get("changePct")),
            "downFromHighPct": round_or_none(source_row.get("downFromHighPct")),
            "aboveLowPct": round_or_none(source_row.get("aboveLowPct")),
            "strengthScore": round_or_none(source_row.get("strengthScore"), 1),
        }

        signal, breakout_gap, breakout_score = classify_near_breakout(row)
        if signal == "Neutral":
            continue
        row["signal"] = signal
        row["breakoutGapPct"] = breakout_gap
        row["breakoutScore"] = breakout_score
        rows.append(row)

    signal_order = {
        "Fresh Breakout": 0,
        "Near Breakout": 1,
        "Breakout Watch": 2,
        "Momentum Breakout Watch": 3,
        "Retest Near High": 4,
    }
    rows = sorted(rows, key=lambda item: (signal_order.get(item.get("signal"), 9), -(safe_float(item.get("breakoutScore")) or 0)))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def update_near_breakout_scanner():
    print("\nUpdating Near Breakout Scanner")
    previous = read_json_file(NEAR_BREAKOUT_FILE, {})

    strength_payload = read_json_file(STOCK_STRENGTH_FILE, {})
    strength_rows = strength_payload.get("stocks", []) if isinstance(strength_payload, dict) else []

    if not strength_rows:
        try:
            strength_rows, latest_updated_at = build_stock_strength_rows_from_52w_json()
        except Exception:
            strength_rows, latest_updated_at = [], None
    else:
        latest_updated_at = strength_payload.get("updatedAt")

    rows = build_near_breakout_rows_from_strength_rows(strength_rows)

    if not rows and previous.get("stocks"):
        print("Near breakout scanner update failed, using previous JSON.")
        payload = previous
        payload["updatedAt"] = previous.get("updatedAt") or format_timestamp()
    else:
        payload = {
            "toolName": "Near Breakout Scanner",
            "updatedAt": latest_updated_at or format_timestamp(),
            "generatedAt": format_timestamp(),
            "universeCount": len(strength_rows),
            "signalCount": len(rows),
            "sourceNote": (
                "Generated from AIT Stock Strength Ranker and existing 52-week high-low JSON files. "
                "Breakout score uses 52-week high proximity, daily move and strength score. Educational use only."
            ),
            "stocks": rows,
        }

    NEAR_BREAKOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NEAR_BREAKOUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {NEAR_BREAKOUT_FILE}")

# ============================================================
# MAIN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Automation In Trade market JSON files."
    )
    parser.add_argument(
        "--mode",
        choices=["all", "52w", "market-snapshot", "fii-dii", "index-performance", "stock-strength", "momentum-scanner", "volume-surge", "near-breakout"],
        default="all",
        help=(
            "Choose what to update. "
            "all = 52-week JSON + market snapshot + FII/DII; "
            "52w = only index 52-week high-low files; "
            "market-snapshot = only homepage NSE snapshot; "
            "fii-dii = only FII/DII activity JSON; index-performance = only full-page index performance JSON; stock-strength = only AIT Stock Strength Ranker JSON; momentum-scanner = only Bullish/Bearish Momentum Scanner JSON; volume-surge = only Volume Surge Scanner JSON; near-breakout = only Near Breakout Scanner JSON."
        ),
    )
    parser.add_argument(
        "--only-fii-dii",
        action="store_true",
        help="Shortcut for --mode fii-dii. Updates only market-data/fii-dii-activity.json.",
    )
    return parser.parse_args()


def update_sector_wise_stock_pages():
    """Rebuild sector-wise JSON/pages from the freshly updated stock strength universe."""
    import subprocess
    import sys

    script_path = Path(__file__).resolve().parent / "GenerateSectorWiseStocks.py"
    if not script_path.exists():
        print("Sector page update skipped: GenerateSectorWiseStocks.py not found.")
        return
    print("\nUpdating Sector Wise Stocks from latest Stock Strength data")
    subprocess.run([sys.executable, str(script_path)], check=True)


def print_upload_paths(paths):
    print("\nCompleted successfully.")
    print("Upload these updated paths:")
    for path in paths:
        print(f"  {path}")


def main():
    args = parse_args()
    mode = "fii-dii" if args.only_fii_dii else args.mode

    if mode in ["all", "52w"] and not JSON_FOLDER.exists():
        raise FileNotFoundError(
            f"Folder not found: {JSON_FOLDER}\n"
            "Run this script from website root folder where index.html exists."
        )

    upload_paths = []

    if mode in ["all", "52w"]:
        for slug in INDEX_CONFIG.keys():
            update_index_json(slug)
        upload_paths.append(JSON_FOLDER)

    if mode in ["all", "market-snapshot"]:
        update_market_snapshot()
        upload_paths.append(MARKET_SNAPSHOT_FILE)

    if mode in ["all", "index-performance"]:
        update_index_performance()
        upload_paths.append(INDEX_PERFORMANCE_FILE)

    if mode in ["all", "fii-dii"]:
        update_fii_dii_activity()
        upload_paths.append(FII_DII_ACTIVITY_FILE)

    if mode in ["all", "stock-strength"]:
        update_stock_strength_ranker()
        upload_paths.append(STOCK_STRENGTH_FILE)
        update_sector_wise_stock_pages()
        upload_paths.append(WEBSITE_ROOT / "market-data" / "sector-wise-stocks.json")
        upload_paths.append(Path("markets") / "sector")

    if mode in ["all", "momentum-scanner"]:
        update_bullish_bearish_momentum_scanner()
        upload_paths.append(MOMENTUM_SCANNER_FILE)

    if mode in ["all", "volume-surge"]:
        update_volume_surge_scanner()
        upload_paths.append(VOLUME_SURGE_FILE)

    if mode in ["all", "near-breakout"]:
        update_near_breakout_scanner()
        upload_paths.append(NEAR_BREAKOUT_FILE)

    print_upload_paths(upload_paths)


if __name__ == "__main__":
    main()
