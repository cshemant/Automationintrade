"""
GenerateResultsJson.py

Generates lightweight quarterly-results JSON cards for the Automation In Trade
homepage stock research search.

Output path:
  stock-research-data/results/{SYMBOL}.json

Recommended run order:
  python GenerateMarketToolsJson.py --mode all
  python GenerateResultsJson.py
  python GenerateStockResearchIndex.py

Notes:
- This script does not generate images.
- It uses Yahoo Finance quarterly income statement data through yfinance.
- When full yearly comparison data is unavailable, it still generates a basic
  result card from the latest available quarters.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent
MARKET_DATA_DIR = ROOT / "market-data"
HIGH_LOW_DIR = MARKET_DATA_DIR / "52-week-high-low"
OUTPUT_DIR = ROOT / "stock-research-data" / "results"


def get_yfinance():
    try:
        import yfinance as yf
        return yf
    except Exception as exc:
        raise RuntimeError(
            "yfinance is required. Install dependencies with: pip install -r requirements.txt"
        ) from exc


@dataclass
class StockMeta:
    symbol: str
    stock_name: str
    indices: List[str]
    cmp: Optional[float] = None
    change_pct: Optional[float] = None
    updated_at: str = ""


def now_ist() -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %H:%M IST")
    return datetime.now().strftime("%d-%b-%Y %H:%M IST")


def safe_symbol(value: str) -> str:
    return str(value or "").strip().upper().replace("/", "_").replace("\\", "_")


def yahoo_symbol(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if not s:
        return s
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def clean_number(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "—", "-"}:
        return None
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return None


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    c = clean_number(current)
    p = clean_number(previous)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p) * 100.0


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    a_num = clean_number(a)
    b_num = clean_number(b)
    if a_num is None or b_num in (None, 0):
        return None
    return a_num / b_num


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_stock_universe() -> Dict[str, StockMeta]:
    stocks: Dict[str, StockMeta] = {}
    if not HIGH_LOW_DIR.exists():
        return stocks

    for path in sorted(HIGH_LOW_DIR.glob("*.json")):
        data = load_json(path)
        if not data:
            continue
        index_name = data.get("indexName") or path.stem
        updated_at = data.get("updatedAt", "")
        for row in data.get("stocks", []):
            symbol = safe_symbol(row.get("symbol"))
            if not symbol:
                continue
            item = stocks.get(symbol)
            if item is None:
                item = StockMeta(
                    symbol=symbol,
                    stock_name=row.get("stockName") or symbol,
                    indices=[],
                    cmp=clean_number(row.get("cmp")),
                    change_pct=clean_number(row.get("changePct")),
                    updated_at=updated_at,
                )
                stocks[symbol] = item
            if row.get("stockName"):
                item.stock_name = row.get("stockName")
            if index_name not in item.indices:
                item.indices.append(index_name)
            if row.get("cmp") is not None:
                item.cmp = clean_number(row.get("cmp"))
            if row.get("changePct") is not None:
                item.change_pct = clean_number(row.get("changePct"))
            if updated_at:
                item.updated_at = updated_at
    return stocks


def parse_symbols_arg(value: str) -> List[str]:
    if not value:
        return []
    raw = re.split(r"[,\s]+", value.strip())
    return [safe_symbol(x) for x in raw if safe_symbol(x)]


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.index = [str(x).strip().lower() for x in out.index]
    return out


def get_first_matching(df: pd.DataFrame, candidates: List[str]) -> Optional[pd.Series]:
    if df.empty:
        return None
    normalized = {idx: idx.lower() for idx in df.index}
    for idx in df.index:
        idx_low = normalized[idx]
        for cand in candidates:
            cand_low = cand.lower()
            if idx_low == cand_low or cand_low in idx_low:
                return df.loc[idx]
    return None


def latest_cols(df: pd.DataFrame) -> List:
    if df is None or df.empty:
        return []
    cols = list(df.columns)
    try:
        cols = sorted(cols)
    except Exception:
        pass
    return cols


def extract_result_data(symbol: str) -> Optional[Dict]:
    yf = get_yfinance()
    ticker = yf.Ticker(yahoo_symbol(symbol))

    df = None
    for attr in ["quarterly_income_stmt", "quarterly_financials"]:
        try:
            temp = getattr(ticker, attr)
            if temp is not None and not temp.empty:
                df = normalize_index(temp)
                break
        except Exception:
            continue

    if df is None or df.empty:
        return None

    cols = latest_cols(df)
    if len(cols) < 2:
        return None

    revenue_row = get_first_matching(df, ["total revenue", "revenue", "sales", "operating revenue"])
    profit_row = get_first_matching(df, ["net income", "net profit", "netincome", "net income common stockholders"])
    operating_row = get_first_matching(df, ["operating income", "ebit", "pretax income"])
    eps_row = get_first_matching(df, ["diluted eps", "basic eps", "eps"])

    if revenue_row is None or profit_row is None:
        return None

    def val(row: Optional[pd.Series], idx: int) -> Optional[float]:
        if row is None:
            return None
        if idx >= len(cols):
            return None
        return clean_number(row.get(cols[idx]))

    current_rev = val(revenue_row, -1)
    prev_rev = val(revenue_row, -2)
    yoy_rev_base = val(revenue_row, -5) if len(cols) >= 5 else None
    current_profit = val(profit_row, -1)
    prev_profit = val(profit_row, -2)
    yoy_profit_base = val(profit_row, -5) if len(cols) >= 5 else None
    current_op = val(operating_row, -1)
    prev_op = val(operating_row, -2)
    current_eps = val(eps_row, -1)
    prev_eps = val(eps_row, -2)

    revenue_qoq = pct_change(current_rev, prev_rev)
    revenue_yoy = pct_change(current_rev, yoy_rev_base)
    profit_qoq = pct_change(current_profit, prev_profit)
    profit_yoy = pct_change(current_profit, yoy_profit_base)
    eps_qoq = pct_change(current_eps, prev_eps)

    margin_current = None
    margin_prev = None
    if current_op is not None and current_rev not in (None, 0):
        margin_current = current_op / current_rev * 100.0
    elif current_profit is not None and current_rev not in (None, 0):
        margin_current = current_profit / current_rev * 100.0
    if prev_op is not None and prev_rev not in (None, 0):
        margin_prev = prev_op / prev_rev * 100.0
    elif prev_profit is not None and prev_rev not in (None, 0):
        margin_prev = prev_profit / prev_rev * 100.0

    margin_delta = None
    if margin_current is not None and margin_prev is not None:
        margin_delta = margin_current - margin_prev

    latest_quarter = cols[-1]
    try:
        latest_quarter_text = pd.to_datetime(latest_quarter).strftime("%b %Y")
    except Exception:
        latest_quarter_text = str(latest_quarter)

    return {
        "latestQuarter": latest_quarter_text,
        "revenueQoQ": revenue_qoq,
        "revenueYoY": revenue_yoy,
        "profitQoQ": profit_qoq,
        "profitYoY": profit_yoy,
        "epsQoQ": eps_qoq,
        "marginCurrent": margin_current,
        "marginDelta": margin_delta,
        "revenueCurrent": current_rev,
        "profitCurrent": current_profit,
        "epsCurrent": current_eps,
    }


def bounded_score(value: Optional[float], lo: float, hi: float) -> Optional[float]:
    if value is None:
        return None
    if hi <= lo:
        return None
    clipped = max(lo, min(hi, float(value)))
    return (clipped - lo) / (hi - lo) * 100.0


def margin_view(margin: Optional[float], delta: Optional[float]) -> str:
    if margin is None:
        return "Margin NA"
    if margin >= 20 and (delta is None or delta >= 0):
        return "Strong"
    if margin >= 12 and (delta is None or delta >= -1):
        return "Stable"
    if delta is not None and delta < -1.5:
        return "Weakening"
    return "Watch"


def trend_text(value: Optional[float], good: float = 0) -> str:
    if value is None:
        return "NA"
    if value >= good + 10:
        return "Strong"
    if value >= good:
        return "Positive"
    if value >= good - 5:
        return "Stable"
    return "Weak"


def reaction_risk(score: float) -> str:
    if score >= 75:
        return "Low"
    if score >= 55:
        return "Medium"
    return "High"


def grade_from_score(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 72:
        return "Very Good"
    if score >= 58:
        return "Good"
    if score >= 45:
        return "Average"
    return "Poor"


def view_from_score(score: float) -> str:
    if score >= 72:
        return "Strong Result"
    if score >= 52:
        return "Mixed Result"
    return "Weak Result"


def result_json_for_stock(meta: StockMeta, raw: Dict) -> Optional[Dict]:
    if not raw:
        return None

    components = []
    for value, lo, hi in [
        (raw.get("revenueQoQ"), -10, 20),
        (raw.get("revenueYoY"), -15, 30),
        (raw.get("profitQoQ"), -20, 30),
        (raw.get("profitYoY"), -25, 40),
        (raw.get("epsQoQ"), -20, 25),
        (raw.get("marginCurrent"), 4, 28),
        (raw.get("marginDelta"), -3, 3),
    ]:
        sc = bounded_score(value, lo, hi)
        if sc is not None:
            components.append(sc)

    if not components:
        return None

    score = round(sum(components) / len(components))
    grade = grade_from_score(score)
    view = view_from_score(score)
    confidence = min(95, 45 + len(components) * 7)

    revenue_trend = trend_text(raw.get("revenueQoQ"), 0)
    profit_trend = trend_text(raw.get("profitQoQ"), 0)
    margin_state = margin_view(raw.get("marginCurrent"), raw.get("marginDelta"))
    risk = reaction_risk(score)

    final_view = {
        "Excellent": "Very strong result quality",
        "Very Good": "Good result quality with positive bias",
        "Good": "Good but not aggressive",
        "Average": "Mixed quarter; wait for market reaction",
        "Poor": "Weak result quality; high reaction risk",
    }.get(grade, "Mixed result quality")

    payload = {
        "view": view,
        "grade": grade,
        "score": score,
        "confidence": confidence,
        "summary": f"Quarterly result scorecard rendered from JSON values for {raw.get('latestQuarter', 'latest quarter')}: revenue, profit, margin, and reaction risk.",
        "symbol": meta.symbol,
        "stockName": meta.stock_name,
        "updatedAt": now_ist(),
        "metrics": [
            {"label": "Revenue QoQ", "value": raw.get("revenueQoQ"), "type": "percent"},
            {"label": "Profit YoY", "value": raw.get("profitYoY"), "type": "percent"},
            {"label": "Margin View", "value": margin_state},
            {"label": "Reaction Risk", "value": risk},
        ],
        "rows": [
            {"label": "Latest Quarter", "value": raw.get("latestQuarter", "Latest")},
            {"label": "Revenue Trend", "value": revenue_trend},
            {"label": "Profit Trend", "value": profit_trend},
            {"label": "Margin Trend", "value": margin_state},
            {"label": "Final View", "value": final_view},
        ],
        "note": "Use this as a result-quality view, not as buy/sell advice.",
        "source": "GenerateResultsJson.py",
    }
    return payload


def write_json(symbol: str, payload: Dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{symbol}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate results JSON cards for stock research search.")
    parser.add_argument("--symbols", default="", help="Optional comma/space separated NSE symbols to generate, e.g. RELIANCE,TCS,M&M")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of symbols for testing.")
    args = parser.parse_args()

    universe = load_stock_universe()
    selected = parse_symbols_arg(args.symbols)
    if selected:
        stocks = {s: universe.get(s, StockMeta(symbol=s, stock_name=s, indices=[])) for s in selected}
    else:
        stocks = universe

    symbols = sorted(stocks.keys())
    if args.limit and args.limit > 0:
        symbols = symbols[: args.limit]

    if not symbols:
        print("No symbols found. Run GenerateMarketToolsJson.py --mode all first, or pass --symbols RELIANCE,TCS")
        return 1

    print(f"Generating results JSON for {len(symbols)} symbols")
    print(f"Output folder: {OUTPUT_DIR}")

    ok = 0
    failed: List[str] = []

    for symbol in symbols:
        try:
            raw = extract_result_data(symbol)
            payload = result_json_for_stock(stocks[symbol], raw)
            if not payload:
                failed.append(symbol)
                print(f"  SKIP {symbol}: result data unavailable")
                continue
            write_json(symbol, payload)
            ok += 1
            print(f"  OK {symbol}")
        except Exception as exc:
            failed.append(symbol)
            print(f"  FAIL {symbol}: {exc}")

    print(f"Completed results JSON generation. Success={ok}, Failed={len(failed)}")
    if failed:
        preview = ", ".join(failed[:40])
        print(f"Failed/Skipped symbols: {preview}{' ...' if len(failed) > 40 else ''}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
