"""Shared, run-local Yahoo OHLCV cache for Automation In Trade generators.

Why this exists
---------------
Several JSON generators need the same daily OHLCV history. Downloading it again
for Volume Surge, Price Action and Technical Analysis is slow and increases the
chance of Yahoo/NSE rate-limit failures. This module downloads each symbol once,
stores it under .runtime-cache/, and lets every generator reuse the same frame.

The cache is intentionally git-ignored. GitHub Actions starts with a clean cache,
so data is fetched once per workflow run, while local same-day reruns can reuse it.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE_ROOT = ROOT / ".runtime-cache" / "ohlcv"
QUOTE_CACHE_ROOT = ROOT / ".runtime-cache" / "latest-quotes"
DEFAULT_MAX_AGE_HOURS = 8.0
DEFAULT_QUOTE_MAX_AGE_MINUTES = 30.0
QUOTE_OVERLAY_MAX_AGE_MINUTES = 360.0


def safe_symbol(value: str) -> str:
    return str(value or "").strip().upper().replace("/", "_").replace("\\", "_")


def yahoo_symbol(symbol: str) -> str:
    value = safe_symbol(symbol)
    if value.endswith(".NS") or value.endswith(".BO"):
        return value
    return f"{value}.NS"


def _cache_key(period: str, interval: str) -> str:
    raw = f"{period}_{interval}".lower()
    return re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-") or "default"


def cache_path(symbol: str, period: str = "1y", interval: str = "1d") -> Path:
    return CACHE_ROOT / _cache_key(period, interval) / f"{safe_symbol(symbol)}.csv"


def _meta_path(period: str, interval: str) -> Path:
    return CACHE_ROOT / _cache_key(period, interval) / "manifest.json"


def _hours_since_modified(path: Path) -> float:
    try:
        age_seconds = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        return max(0.0, age_seconds / 3600.0)
    except OSError:
        return math.inf


def _minutes_since_modified(path: Path) -> float:
    return _hours_since_modified(path) * 60.0


def latest_quote_path(symbol: str) -> Path:
    return QUOTE_CACHE_ROOT / f"{safe_symbol(symbol)}.json"


def load_latest_quote(
    symbol: str,
    max_age_minutes: Optional[float] = None,
) -> Dict[str, Any]:
    path = latest_quote_path(symbol)
    if not path.exists() or path.stat().st_size <= 20:
        return {}
    if max_age_minutes is not None and _minutes_since_modified(path) > max_age_minutes:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        close = pd.to_numeric(payload.get("close"), errors="coerce")
        if pd.isna(close) or float(close) <= 0:
            return {}
        return payload
    except Exception:
        return {}


def save_latest_quote(symbol: str, payload: Dict[str, Any]) -> Optional[Path]:
    if not isinstance(payload, dict):
        return None
    close = pd.to_numeric(payload.get("close"), errors="coerce")
    if pd.isna(close) or float(close) <= 0:
        return None
    path = latest_quote_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _index_as_local_dates(index: pd.Index) -> pd.DatetimeIndex:
    dt = pd.to_datetime(index, errors="coerce")
    if not isinstance(dt, pd.DatetimeIndex):
        dt = pd.DatetimeIndex(dt)
    dt = dt[~dt.isna()]
    if getattr(dt, "tz", None) is not None:
        try:
            dt = dt.tz_convert("Asia/Kolkata")
        except Exception:
            dt = dt.tz_convert(None)
    return dt


def latest_quote_from_intraday_frame(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    frame = normalize_ohlcv_frame(df)
    if frame.empty:
        return {}

    dt = _index_as_local_dates(frame.index)
    if len(dt) != len(frame.index):
        frame = frame.iloc[-len(dt):].copy()
    frame = frame.copy()
    frame.index = dt
    frame = frame.sort_index()

    date_series = pd.Series(frame.index.date, index=frame.index)
    unique_dates = list(dict.fromkeys(date_series.tolist()))
    if not unique_dates:
        return {}

    latest_date = unique_dates[-1]
    latest_session = frame[date_series == latest_date]
    if latest_session.empty:
        return {}

    previous_close = None
    if len(unique_dates) >= 2:
        previous_session = frame[date_series == unique_dates[-2]]
        if not previous_session.empty:
            previous_close = float(previous_session["Close"].iloc[-1])

    close = float(latest_session["Close"].iloc[-1])
    open_price = float(latest_session["Open"].iloc[0])
    high = float(latest_session["High"].max())
    low = float(latest_session["Low"].min())
    volume = float(latest_session["Volume"].fillna(0).sum())
    change_pct = ((close - previous_close) / previous_close * 100.0) if previous_close else None

    last_ts = latest_session.index[-1]
    try:
        timestamp_iso = last_ts.isoformat()
    except Exception:
        timestamp_iso = str(last_ts)

    return {
        "symbol": safe_symbol(symbol),
        "marketDate": str(latest_date),
        "marketTimestamp": timestamp_iso,
        "open": round(open_price, 6),
        "high": round(high, 6),
        "low": round(low, 6),
        "close": round(close, 6),
        "previousClose": round(previous_close, 6) if previous_close else None,
        "changePct": round(change_pct, 6) if change_pct is not None else None,
        "volume": round(volume, 6),
        "interval": "5m",
        "source": "Yahoo intraday batch",
        "fetchedAtUtc": datetime.now(timezone.utc).isoformat(),
    }


def overlay_latest_quote(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_ohlcv_frame(df)
    if frame.empty:
        return frame

    quote = load_latest_quote(symbol, max_age_minutes=QUOTE_OVERLAY_MAX_AGE_MINUTES)
    if not quote:
        return frame

    try:
        market_date = pd.Timestamp(str(quote.get("marketDate"))).normalize()
        existing_dates = pd.to_datetime(frame.index, errors="coerce")
        if isinstance(existing_dates, pd.DatetimeIndex) and existing_dates.tz is not None:
            existing_dates = existing_dates.tz_convert(None)
        last_date = existing_dates[-1].normalize()
    except Exception:
        return frame

    if market_date < last_date:
        return frame

    row = {
        "Open": pd.to_numeric(quote.get("open"), errors="coerce"),
        "High": pd.to_numeric(quote.get("high"), errors="coerce"),
        "Low": pd.to_numeric(quote.get("low"), errors="coerce"),
        "Close": pd.to_numeric(quote.get("close"), errors="coerce"),
        "Volume": pd.to_numeric(quote.get("volume"), errors="coerce"),
    }
    if any(pd.isna(row[key]) for key in ["Open", "High", "Low", "Close"]):
        return frame

    out = frame.copy()
    out_index = pd.to_datetime(out.index, errors="coerce")
    if isinstance(out_index, pd.DatetimeIndex) and out_index.tz is not None:
        out_index = out_index.tz_convert(None)
    out.index = out_index

    same_date_mask = out.index.normalize() == market_date
    if same_date_mask.any():
        matching = out.index[same_date_mask]
        target_index = matching[-1]
        for key, value in row.items():
            out.loc[target_index, key] = value
    else:
        out.loc[market_date, list(row.keys())] = list(row.values())

    out = normalize_ohlcv_frame(out)
    out.attrs["latest_quote_overlay"] = True
    out.attrs["latest_quote"] = quote
    return out


def is_cache_fresh(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> bool:
    path = cache_path(symbol, period, interval)
    return path.exists() and path.stat().st_size > 50 and _hours_since_modified(path) <= max_age_hours


def normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    rename = {}
    for col in out.columns:
        key = str(col).strip().lower().replace(" ", "")
        if key in {"open", "1.open"}:
            rename[col] = "Open"
        elif key in {"high", "2.high"}:
            rename[col] = "High"
        elif key in {"low", "3.low"}:
            rename[col] = "Low"
        elif key in {"close", "4.close", "adjclose", "adj_close"}:
            # Prefer the true Close when both Close and Adj Close are present.
            if key in {"close", "4.close"} or "Close" not in rename.values():
                rename[col] = "Close"
        elif key in {"volume", "5.volume"}:
            rename[col] = "Volume"

    out = out.rename(columns=rename)
    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(col not in out.columns for col in required):
        return pd.DataFrame()

    out = out[required].apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    out = out[out["Close"] > 0]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def extract_ticker_frame(batch_df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Extract one ticker from yfinance output across old/new column layouts."""
    if batch_df is None or batch_df.empty:
        return pd.DataFrame()

    ticker = str(ticker)
    df = None

    if isinstance(batch_df.columns, pd.MultiIndex):
        level0 = {str(x) for x in batch_df.columns.get_level_values(0)}
        level1 = {str(x) for x in batch_df.columns.get_level_values(1)} if batch_df.columns.nlevels > 1 else set()

        try:
            if ticker in level0:
                df = batch_df[ticker].copy()
            elif ticker in level1:
                df = batch_df.xs(ticker, axis=1, level=1).copy()
            elif len(level1) == 1 and any(x in level0 for x in {"Open", "High", "Low", "Close", "Volume"}):
                df = batch_df.droplevel(1, axis=1).copy()
            elif len(level0) == 1:
                df = batch_df.droplevel(0, axis=1).copy()
        except Exception:
            df = None
    else:
        df = batch_df.copy()

    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        # A final defensive flattening for unexpected yfinance layouts.
        df.columns = [next((str(x) for x in col if str(x) in {"Open", "High", "Low", "Close", "Volume"}), str(col[0])) for col in df.columns]

    return normalize_ohlcv_frame(df)


def save_cached_frame(
    symbol: str,
    df: pd.DataFrame,
    period: str = "1y",
    interval: str = "1d",
) -> Optional[Path]:
    frame = normalize_ohlcv_frame(df)
    if frame.empty:
        return None

    path = cache_path(symbol, period, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=True, index_label="Date")
    return path


def load_cached_frame(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    max_age_hours: Optional[float] = None,
) -> pd.DataFrame:
    path = cache_path(symbol, period, interval)
    if not path.exists() or path.stat().st_size <= 50:
        return pd.DataFrame()
    if max_age_hours is not None and _hours_since_modified(path) > max_age_hours:
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        return overlay_latest_quote(symbol, normalize_ohlcv_frame(df))
    except Exception:
        return pd.DataFrame()


def _chunked(items: List[str], size: int) -> Iterable[List[str]]:
    size = max(1, int(size or 1))
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _download_batch(symbols: List[str], period: str, interval: str) -> Dict[str, pd.DataFrame]:
    import yfinance as yf

    tickers = [yahoo_symbol(symbol) for symbol in symbols]
    raw = yf.download(
        tickers=" ".join(tickers),
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
        timeout=20,
    )

    frames: Dict[str, pd.DataFrame] = {}
    for symbol, ticker in zip(symbols, tickers):
        frame = extract_ticker_frame(raw, ticker)
        if not frame.empty:
            frames[safe_symbol(symbol)] = frame
    return frames


def _download_latest_quote_batch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    import yfinance as yf

    tickers = [yahoo_symbol(symbol) for symbol in symbols]
    raw = yf.download(
        tickers=" ".join(tickers),
        period="5d",
        interval="5m",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
        prepost=False,
        timeout=20,
    )

    quotes: Dict[str, Dict[str, Any]] = {}
    for symbol, ticker in zip(symbols, tickers):
        frame = extract_ticker_frame(raw, ticker)
        payload = latest_quote_from_intraday_frame(symbol, frame)
        if payload:
            quotes[safe_symbol(symbol)] = payload
    return quotes


def _print_latest_quote_date_summary(quotes: Dict[str, Dict[str, Any]]) -> None:
    dates = sorted({str(payload.get("marketDate")) for payload in quotes.values() if payload.get("marketDate")})
    if not dates:
        return
    if len(dates) == 1:
        print(f"Shared latest-price market date: {dates[0]} ({len(quotes)} symbols available).")
    else:
        preview = ", ".join(dates[-4:])
        print(f"Shared latest-price market dates: {preview} ({len(quotes)} symbols available).")


def ensure_latest_quote_cache(
    symbols: Iterable[str],
    batch_size: int = 40,
    sleep_seconds: float = 0.4,
    max_age_minutes: float = DEFAULT_QUOTE_MAX_AGE_MINUTES,
    force_refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    ordered: List[str] = []
    seen = set()
    for value in symbols:
        symbol = safe_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)

    quotes: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for symbol in ordered:
        if not force_refresh:
            payload = load_latest_quote(symbol, max_age_minutes=max_age_minutes)
            if payload:
                quotes[symbol] = payload
                continue
        missing.append(symbol)

    if not missing:
        if ordered:
            print(f"Shared latest-price cache: reused {len(ordered)}/{len(ordered)} symbols.")
            _print_latest_quote_date_summary(quotes)
        return quotes

    print(
        f"Shared latest-price cache: {len(quotes)} reused, {len(missing)} need intraday download."
    )

    failed: List[str] = []
    for batch_no, batch in enumerate(_chunked(missing, batch_size), start=1):
        try:
            batch_quotes = _download_latest_quote_batch(batch)
        except Exception as exc:
            print(f"  Latest-price batch {batch_no} failed ({len(batch)} symbols): {exc}")
            batch_quotes = {}
        for symbol, payload in batch_quotes.items():
            if save_latest_quote(symbol, payload):
                quotes[symbol] = payload
        failed.extend(symbol for symbol in batch if symbol not in batch_quotes)
        print(
            f"  Latest-price batch {batch_no}: downloaded {len(batch_quotes)}/{len(batch)}; "
            f"total available {len(quotes)}."
        )
        if sleep_seconds > 0 and batch_no * batch_size < len(missing):
            time.sleep(sleep_seconds)

    retry_symbols = list(dict.fromkeys(failed))
    if retry_symbols:
        retry_size = min(8, max(2, int(batch_size or 8)))
        recovered = 0
        still_missing: List[str] = []
        print(f"Shared latest-price cache: retrying {len(retry_symbols)} symbols in groups of {retry_size}.")
        for batch in _chunked(retry_symbols, retry_size):
            try:
                batch_quotes = _download_latest_quote_batch(batch)
            except Exception as exc:
                print(f"  Latest-price retry failed ({len(batch)} symbols): {exc}")
                batch_quotes = {}
            for symbol, payload in batch_quotes.items():
                if save_latest_quote(symbol, payload):
                    quotes[symbol] = payload
                    recovered += 1
            still_missing.extend(symbol for symbol in batch if symbol not in batch_quotes)
            if sleep_seconds > 0:
                time.sleep(min(sleep_seconds, 0.4))
        if recovered:
            print(f"Shared latest-price cache: recovered {recovered} symbols on retry.")
        if still_missing:
            preview = ", ".join(still_missing[:30])
            suffix = " ..." if len(still_missing) > 30 else ""
            print(f"Latest intraday price unavailable for {len(still_missing)} symbols: {preview}{suffix}")

    _print_latest_quote_date_summary(quotes)
    return quotes


def _write_manifest(period: str, interval: str, requested: int, downloaded: int, available: int) -> None:
    path = _meta_path(period, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "interval": interval,
        "requestedSymbols": requested,
        "downloadedSymbols": downloaded,
        "availableSymbols": available,
        "note": "Run-local shared OHLCV cache reused by market, price-action and technical generators.",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_ohlcv_cache(
    symbols: Iterable[str],
    period: str = "1y",
    interval: str = "1d",
    batch_size: int = 80,
    sleep_seconds: float = 0.5,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    force_refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Return OHLCV frames, downloading only symbols not already fresh.

    Failed large batches are retried in small groups, never in a slow
    one-request-per-symbol loop. This keeps GitHub Actions runtime bounded.
    """
    ordered: List[str] = []
    seen = set()
    for value in symbols:
        symbol = safe_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)

    frames: Dict[str, pd.DataFrame] = {}
    missing: List[str] = []

    for symbol in ordered:
        if not force_refresh:
            frame = load_cached_frame(symbol, period, interval, max_age_hours=max_age_hours)
            if not frame.empty:
                frames[symbol] = frame
                continue
        missing.append(symbol)

    if not missing:
        if ordered:
            print(f"Shared OHLCV cache: reused {len(ordered)}/{len(ordered)} symbols.")
        return frames

    print(
        f"Shared OHLCV cache: {len(frames)} reused, {len(missing)} need download "
        f"({period}/{interval})."
    )

    downloaded_count = 0
    failed_symbols: List[str] = []

    for batch_no, batch in enumerate(_chunked(missing, batch_size), start=1):
        try:
            batch_frames = _download_batch(batch, period, interval)
        except Exception as exc:
            print(f"  Cache batch {batch_no} failed ({len(batch)} symbols): {exc}")
            batch_frames = {}

        for symbol, frame in batch_frames.items():
            if save_cached_frame(symbol, frame, period, interval):
                frames[symbol] = frame
                downloaded_count += 1

        batch_missing = [symbol for symbol in batch if symbol not in batch_frames]
        failed_symbols.extend(batch_missing)
        print(
            f"  Cache batch {batch_no}: downloaded {len(batch_frames)}/{len(batch)}; "
            f"total available {len(frames)}."
        )
        if sleep_seconds > 0 and batch_no * batch_size < len(missing):
            time.sleep(sleep_seconds)

    # Retry missing symbols in small batches. This is much faster and safer than
    # making an individual Ticker.history request for every failed symbol.
    retry_symbols = list(dict.fromkeys(failed_symbols))
    if retry_symbols:
        recovered = 0
        still_missing: List[str] = []
        retry_size = min(10, max(2, int(batch_size or 10)))
        print(f"Shared OHLCV cache: retrying {len(retry_symbols)} missing symbols in groups of {retry_size}.")
        for batch in _chunked(retry_symbols, retry_size):
            try:
                batch_frames = _download_batch(batch, period, interval)
            except Exception as exc:
                print(f"  Small retry batch failed ({len(batch)} symbols): {exc}")
                batch_frames = {}
            for symbol, frame in batch_frames.items():
                if save_cached_frame(symbol, frame, period, interval):
                    frames[symbol] = frame
                    recovered += 1
                    downloaded_count += 1
            still_missing.extend(symbol for symbol in batch if symbol not in batch_frames)
            if sleep_seconds > 0:
                time.sleep(min(sleep_seconds, 0.5))
        if recovered:
            print(f"Shared OHLCV cache: recovered {recovered} symbols on retry.")
        if still_missing:
            preview = ", ".join(still_missing[:30])
            print(f"Shared OHLCV cache unavailable for {len(still_missing)} symbols: {preview}{' ...' if len(still_missing) > 30 else ''}")

    _write_manifest(period, interval, len(ordered), downloaded_count, len(frames))
    return frames
