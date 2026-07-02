"""
GenerateTechnicalAnalysisJson.py

Generates lightweight technical-analysis JSON cards for the Automation In Trade
homepage stock research search.

Output path:
  stock-research-data/technical-analysis/{SYMBOL}.json

Recommended run order:
  python GenerateMarketToolsJson.py --mode all
  python GenerateTechnicalAnalysisJson.py
  python GenerateStockResearchIndex.py

Notes:
- This script does not generate images.
- It uses daily Yahoo Finance OHLCV data through yfinance.
- It generates JSON cards and static /technical-analysis/{stock-slug}/ profile pages.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent
MARKET_DATA_DIR = ROOT / "market-data"
HIGH_LOW_DIR = MARKET_DATA_DIR / "52-week-high-low"
OUTPUT_DIR = ROOT / "stock-research-data" / "technical-analysis"

FREE_RESEARCH_INDICES = {"NIFTY 50", "NIFTY BANK", "BANK NIFTY"}


def is_free_research_stock(meta: StockMeta) -> bool:
    indices = {str(x or "").strip().upper() for x in getattr(meta, "indices", [])}
    return bool(indices & FREE_RESEARCH_INDICES)


def cleanup_premium_json(allowed_symbols: set[str]) -> None:
    if not OUTPUT_DIR.exists():
        return
    for path in OUTPUT_DIR.glob("*.json"):
        if safe_symbol(path.stem) not in allowed_symbols:
            try:
                path.unlink()
            except OSError:
                pass

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
DEFAULT_BATCH_SIZE = 80
REQUEST_SLEEP_SECONDS = 1.5


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


def rupee(value) -> str:
    num = clean_number(value)
    if num is None:
        return "—"
    return "₹" + f"{num:,.2f}"


def range_text(a, b) -> str:
    if clean_number(a) is None or clean_number(b) is None:
        return "—"
    return f"{rupee(a)} → {rupee(b)}"


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_stock_universe() -> Dict[str, StockMeta]:
    """Load symbols from market-data/52-week-high-low/*.json."""
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


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def flatten_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        # Single ticker download can sometimes still return a MultiIndex.
        if len(out.columns.get_level_values(0).unique()) == 1:
            out.columns = [str(c[-1] if c[-1] else c[0]).strip() for c in out.columns]
        else:
            out.columns = ["_".join(str(x) for x in c if x).strip() for c in out.columns]
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def extract_ticker_frame(batch_df: pd.DataFrame, ticker: str, single_ticker: bool = False) -> pd.DataFrame:
    """Return Open/High/Low/Close/Volume frame for one ticker from yfinance output."""
    if batch_df is None or batch_df.empty:
        return pd.DataFrame()

    if single_ticker or not isinstance(batch_df.columns, pd.MultiIndex):
        df = flatten_yfinance_columns(batch_df)
    else:
        if ticker not in batch_df.columns.get_level_values(0):
            return pd.DataFrame()
        df = batch_df[ticker].copy()
        df = flatten_yfinance_columns(df)

    rename = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "")
        if key in {"open", "1.open"}:
            rename[col] = "Open"
        elif key in {"high", "2.high"}:
            rename[col] = "High"
        elif key in {"low", "3.low"}:
            rename[col] = "Low"
        elif key in {"close", "4.close"}:
            rename[col] = "Close"
        elif key in {"adjclose", "adj_close", "adjclose"}:
            rename[col] = "Adj Close"
        elif key in {"volume", "5.volume"}:
            rename[col] = "Volume"
    df = df.rename(columns=rename)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame()
    df = df[required].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[df["Close"] > 0]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def last_float(series: pd.Series, default: Optional[float] = None) -> Optional[float]:
    try:
        val = series.dropna().iloc[-1]
        return float(val) if math.isfinite(float(val)) else default
    except Exception:
        return default


def classify_trend(close: float, ema9: Optional[float], ema21: Optional[float], ema50: Optional[float]) -> str:
    if ema9 is None or ema21 is None or ema50 is None:
        return "Insufficient Data"
    if close > ema9 > ema21 > ema50:
        return "Bullish"
    if close < ema9 < ema21 < ema50:
        return "Bearish"
    if close > ema21 and ema21 >= ema50:
        return "Positive"
    if close < ema21 and ema21 <= ema50:
        return "Weak"
    return "Sideways"


def classify_signal(trend: str, rsi: Optional[float], close: float, support: Optional[float], resistance: Optional[float]) -> str:
    if rsi is None:
        return "Data Watch"
    near_support = support is not None and abs(close - support) / max(close, 1) <= 0.025
    near_resistance = resistance is not None and abs(resistance - close) / max(close, 1) <= 0.025

    if trend in {"Bullish", "Positive"} and 45 <= rsi <= 68 and not near_resistance:
        return "Positive / Watch Zone"
    if trend in {"Bullish", "Positive"} and rsi > 70:
        return "Overbought / Avoid Chase"
    if trend in {"Weak", "Bearish"} and near_support and rsi < 45:
        return "Support Test / Caution"
    if trend in {"Weak", "Bearish"}:
        return "Weak / Wait Zone"
    if near_support:
        return "Support Watch"
    if near_resistance:
        return "Breakout Watch"
    return "Range / Wait for Confirmation"


def volume_label(df: pd.DataFrame) -> Tuple[str, Optional[float]]:
    if len(df) < 25:
        return "Volume: NA", None
    vol = df["Volume"].astype(float)
    mean20 = vol.rolling(20, min_periods=10).mean()
    std20 = vol.rolling(20, min_periods=10).std(ddof=0)
    z = last_float((vol - mean20) / std20.replace(0, np.nan))
    if z is None:
        return "Volume: NA", None
    if z >= 2:
        return f"Volume: Surge (Z: {z:.2f})", z
    if z >= 1:
        return f"Volume: Elevated (Z: {z:.2f})", z
    return f"Volume: Normal (Z: {z:.2f})", z


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> Tuple[Optional[float], Optional[float]]:
    use = df.tail(lookback)
    if use.empty:
        return None, None
    close = float(use["Close"].iloc[-1])
    below = use[use["Low"] < close]["Low"]
    above = use[use["High"] > close]["High"]
    support = float(below.tail(30).min()) if not below.empty else float(use["Low"].min())
    resistance = float(above.tail(30).max()) if not above.empty else float(use["High"].max())
    return support, resistance


def action_rows(signal: str, trend: str, support: Optional[float], resistance: Optional[float]) -> List[Dict]:
    if "Positive" in signal or trend == "Bullish":
        mood = "Positive setup; avoid chasing extended moves"
        risk = "Respect support if momentum weakens"
    elif "Weak" in signal or trend == "Bearish":
        mood = "Weak setup; wait for confirmation"
        risk = "Respect stop-loss if breakdown continues"
    elif "Breakout" in signal:
        mood = "Breakout watch near resistance"
        risk = "False breakout risk near resistance"
    elif "Support" in signal:
        mood = "Support watch; confirm before action"
        risk = "Breakdown below support can increase downside risk"
    else:
        mood = "Range-bound; wait for clear direction"
        risk = "Avoid overtrading inside range"

    return [
        {"label": "Chart Mood", "value": mood},
        {"label": "Risk Note", "value": risk},
        {"label": "Best Use", "value": "Technical zone reference"},
    ]


def technical_json_for_stock(meta: StockMeta, df: pd.DataFrame) -> Optional[Dict]:
    if df is None or len(df) < 60:
        return None
    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["RSI14"] = compute_rsi(df["Close"], 14)
    df["ATR14"] = compute_atr(df, 14)
    df["ADX14"] = compute_adx(df, 14)

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else close
    change_pct = ((close - prev_close) / prev_close * 100) if prev_close else (meta.change_pct or 0)
    ema9 = last_float(df["EMA9"])
    ema21 = last_float(df["EMA21"])
    ema50 = last_float(df["EMA50"])
    rsi = last_float(df["RSI14"])
    atr = last_float(df["ATR14"])
    adx = last_float(df["ADX14"])
    support, resistance = support_resistance(df, 60)
    vol_text, vol_z = volume_label(df)

    trend = classify_trend(close, ema9, ema21, ema50)
    signal = classify_signal(trend, rsi, close, support, resistance)

    if atr is not None and support is not None:
        buy_low = max(support, 0)
        buy_high = support + 0.45 * atr
        stop = max(support - 0.55 * atr, 0)
    else:
        buy_low = buy_high = stop = None

    target = resistance

    summary = "Technical analysis view with trend, RSI, volume, support/resistance and action zones rendered from JSON."

    metrics = [
        {"label": "Trend", "value": trend},
        {"label": "Signal", "value": signal},
        {"label": "1D Move", "value": round(change_pct, 2), "type": "percent"},
        {"label": "RSI", "value": f"{rsi:.2f}" if rsi is not None else "—"},
        {"label": "ADX", "value": f"{adx:.1f}" if adx is not None else "—"},
        {"label": "Volume", "value": vol_text.replace("Volume: ", "")},
    ]

    levels = [
        {"label": "Close", "value": close, "type": "price"},
        {"label": "EMA9", "value": ema9, "type": "price"},
        {"label": "EMA21", "value": ema21, "type": "price"},
        {"label": "EMA50", "value": ema50, "type": "price"},
        {"label": "Support", "value": support, "type": "price"},
        {"label": "Resistance", "value": resistance, "type": "price"},
        {"label": "Buy Zone", "value": range_text(buy_low, buy_high)},
        {"label": "Sell / Target", "value": rupee(target)},
        {"label": "Stop Loss", "value": rupee(stop)},
    ]

    payload = {
        "view": signal,
        "summary": summary,
        "symbol": meta.symbol,
        "stockName": meta.stock_name,
        "updatedAt": now_ist(),
        "metrics": metrics,
        "levels": levels,
        "rows": action_rows(signal, trend, support, resistance),
        "source": "GenerateTechnicalAnalysisJson.py",
        "sourceNote": "Educational technical research view only. Not investment advice.",
    }
    return payload


def write_json(symbol: str, payload: Dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{symbol}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def download_batch(tickers: List[str], period: str, interval: str) -> pd.DataFrame:
    yf = get_yfinance()
    return yf.download(
        tickers=" ".join(tickers),
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )


def parse_symbols_arg(value: str) -> List[str]:
    if not value:
        return []
    raw = re.split(r"[,\s]+", value.strip())
    return [safe_symbol(x) for x in raw if safe_symbol(x)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate technical-analysis JSON cards for stock research search.")
    parser.add_argument("--symbols", default="", help="Optional comma/space separated NSE symbols to generate, e.g. RELIANCE,TCS,M&M")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of symbols for testing.")
    parser.add_argument("--include-premium", action="store_true", help="Backward-compatible option. All stocks are generated by default now.")
    parser.add_argument("--free-only", action="store_true", help="Generate only NIFTY 50 and Bank Nifty stocks for quick/free-only runs.")
    parser.add_argument("--period", default=DEFAULT_PERIOD, help="yfinance period, default 1y")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help="yfinance interval, default 1d")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Symbols per yfinance batch download.")
    parser.add_argument("--sleep", type=float, default=REQUEST_SLEEP_SECONDS, help="Seconds to wait between batches.")
    parser.add_argument("--skip-pages", action="store_true", help="Skip static /technical-analysis/ profile page generation after JSON generation.")
    args = parser.parse_args()

    universe = load_stock_universe()
    selected = parse_symbols_arg(args.symbols)
    if selected:
        # Keep metadata if known; otherwise create basic metadata.
        stocks = {s: universe.get(s, StockMeta(symbol=s, stock_name=s, indices=[])) for s in selected}
    else:
        stocks = universe

    if args.free_only:
        stocks = {symbol: meta for symbol, meta in stocks.items() if is_free_research_stock(meta)}

    symbols = sorted(stocks.keys())
    if args.free_only:
        cleanup_premium_json(set(symbols))
    if args.limit and args.limit > 0:
        symbols = symbols[: args.limit]

    if not symbols:
        print("No symbols found. Run GenerateMarketToolsJson.py --mode all first, or pass --symbols RELIANCE,TCS")
        return 1

    print(f"Generating technical-analysis JSON for {len(symbols)} symbols")
    print(f"Output folder: {OUTPUT_DIR}")

    ok = 0
    failed: List[str] = []

    for batch_no, batch_symbols in enumerate(chunked(symbols, max(1, args.batch_size)), start=1):
        tickers = [yahoo_symbol(s) for s in batch_symbols]
        print(f"Batch {batch_no}: {len(batch_symbols)} symbols")
        try:
            batch_df = download_batch(tickers, args.period, args.interval)
        except Exception as exc:
            print(f"  Batch download failed: {exc}")
            batch_df = pd.DataFrame()

        for symbol, ticker in zip(batch_symbols, tickers):
            try:
                df = extract_ticker_frame(batch_df, ticker, single_ticker=(len(tickers) == 1))
                # Retry single symbol if it was missing from batch.
                if df.empty:
                    yf = get_yfinance()
                    single_df = yf.download(
                        ticker,
                        period=args.period,
                        interval=args.interval,
                        auto_adjust=False,
                        progress=False,
                        group_by="column",
                        threads=False,
                    )
                    df = extract_ticker_frame(single_df, ticker, single_ticker=True)

                payload = technical_json_for_stock(stocks[symbol], df)
                if not payload:
                    failed.append(symbol)
                    print(f"  SKIP {symbol}: insufficient OHLCV data")
                    continue
                write_json(symbol, payload)
                ok += 1
                print(f"  OK {symbol}")
            except Exception as exc:
                failed.append(symbol)
                print(f"  FAIL {symbol}: {exc}")

        if args.sleep > 0 and batch_no * args.batch_size < len(symbols):
            time.sleep(args.sleep)

    print(f"Completed technical JSON generation. Success={ok}, Failed={len(failed)}")
    if failed:
        preview = ", ".join(failed[:40])
        print(f"Failed/Skipped symbols: {preview}{' ...' if len(failed) > 40 else ''}")

    if ok and not args.skip_pages:
        import subprocess
        import sys
        page_script = ROOT / "GenerateTechnicalProfilePages.py"
        if page_script.exists():
            cmd = [sys.executable, str(page_script)]
            if selected:
                cmd += ["--symbols", ",".join(selected)]
            print("Generating static technical-analysis profile pages...")
            subprocess.run(cmd, check=True)
        else:
            print("Static profile page generation skipped: GenerateTechnicalProfilePages.py not found.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
