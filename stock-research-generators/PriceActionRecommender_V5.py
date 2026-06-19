import argparse
from html import parser
import sys
import os
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

import numpy as np
import pandas as pd

# --- Image generation (Price Action Image) ---
# Uses matplotlib (Agg) to render a branded JPEG summary per symbol when enabled.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


try:
    import yfinance as yf
except Exception as e:
    print("❌ Please install yfinance first: pip install yfinance", file=sys.stderr)
    raise
# === IST timestamp helper for filenames ===
from datetime import datetime
try:
    from zoneinfo import ZoneInfo  
except Exception:
    ZoneInfo = None

# =========================================
# .env loader (no external dependency)
# =========================================
def _parse_bool(v: str, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def _parse_int(v: str, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _parse_float(v: str, default: float) -> float:
    try:
        return float(str(v).strip())
    except Exception:
        return default

def load_stock_list(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(path)
    if ext in [".csv"]:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported stock_file type: {ext}. Use .xlsx/.xls/.csv")

def load_dotenv_file(path: str) -> dict:
    """Lightweight .env reader: KEY=VALUE, supports quotes, ignores # comments and blank lines."""
    env = {}
    if not path:
        return env
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            # remove inline comments for unquoted values: KEY=value  # comment
            if "#" in v and not (v.startswith('"') or v.startswith("'")):
                v = v.split("#", 1)[0].strip()

            # strip optional quotes
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            env[k] = v
    return env

def _env_default(env: dict, key: str, fallback):
    v = env.get(key)
    return fallback if v is None or str(v).strip() == "" else v

# =========================================
# Data classes
# =========================================
@dataclass
class Levels:
    trend: str
    close: float
    ema20: float
    ema50: float
    atr: Optional[float]
    support: Optional[float]
    resistance: Optional[float]
    buy_zone_low: Optional[float]
    buy_zone_high: Optional[float]
    sell_zone_low: Optional[float]
    sell_zone_high: Optional[float]
    stop_loss: Optional[float]
    rr_target_1: Optional[float]
    rr_target_2: Optional[float]

@dataclass
class VolumeAlert:
    date: pd.Timestamp
    symbol: str
    close: float
    volume: float
    zscore: float
    direction: str
    action: str

@dataclass
class Position:
    Symbol: str
    Side: str            # "LONG" (sample here)
    Status: str          # "OPEN" or "FLAT"
    Entry: float
    ATR_Entry: float
    Stop: float
    T1: float
    T2: float
    Hit_T1: int          # 0/1
    Hit_T2: int          # 0/1
    BarsSinceEntry: int
    CreatedAt: str
    LastUpdate: str

# =========================================
# Helpers
# =========================================

def to_yahoo_symbol(symbol: str, segment: Optional[str]) -> str:
    seg = (segment or "").upper()
    if seg.startswith("NSE"):
        return f"{symbol}.NS"
    if seg.startswith("BSE"):
        return f"{symbol}.BO"
    return symbol

def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window).mean()

def find_pivots(series: pd.Series, window: int = 5) -> Tuple[List[int], List[int]]:
    lows, highs = [], []
    for i in range(window, len(series) - window):
        left = series[i - window:i]
        right = series[i + 1:i + 1 + window]
        if series.iloc[i] <= left.min() and series.iloc[i] <= right.min():
            lows.append(i)
        if series.iloc[i] >= left.max() and series.iloc[i] >= right.max():
            highs.append(i)
    return lows, highs

def nearest_levels(df: pd.DataFrame, sr_window: int = 5) -> Tuple[Optional[float], Optional[float]]:
    close_series = df['Close'].copy()
    lows_idx, highs_idx = find_pivots(close_series, window=sr_window)
    piv_lows = close_series.iloc[lows_idx].sort_values(ascending=True).values
    piv_highs = close_series.iloc[highs_idx].sort_values(ascending=True).values
    last_close = close_series.iloc[-1]
    support = max([lv for lv in piv_lows if lv < last_close], default=None)
    resistance = min([hv for hv in piv_highs if hv > last_close], default=None)
    return support, resistance

def derive_levels(df: pd.DataFrame, lookback_days: int, atr_window: int, sr_window: int, risk_reward: float) -> Levels:
    use = df.tail(lookback_days).copy()
    use['EMA20'] = use['Close'].ewm(span=20, adjust=False).mean()
    use['EMA50'] = use['Close'].ewm(span=50, adjust=False).mean()
    use['ATR'] = compute_atr(use, window=atr_window)
    close = float(use['Close'].iloc[-1])
    ema20 = float(use['EMA20'].iloc[-1])
    ema50 = float(use['EMA50'].iloc[-1])
    atr_last = use['ATR'].iloc[-1]
    atr = float(atr_last) if pd.notna(atr_last) else None
    trend = "Uptrend" if ema20 > ema50 else ("Downtrend" if ema20 < ema50 else "Sideways")
    support, resistance = nearest_levels(use, sr_window)

    buy_zone_low = buy_zone_high = sell_zone_low = sell_zone_high = stop_loss = rr_t1 = rr_t2 = None
    if atr is not None:
        if support is not None:
            buy_zone_low = support + 0.1 * atr
            buy_zone_high = support + 0.6 * atr
            stop_loss = max(support - 1.0 * atr, 0)
        if resistance is not None:
            sell_zone_low = resistance - 0.6 * atr
            sell_zone_high = resistance - 0.1 * atr
        if trend == "Uptrend":
            rr_t1 = close + risk_reward * atr
            rr_t2 = close + (risk_reward + 1.0) * atr
        elif trend == "Downtrend":
            rr_t1 = max(close - risk_reward * atr, 0)
            rr_t2 = max(close - (risk_reward + 1.0) * atr, 0)

    return Levels(trend, close, ema20, ema50, atr, support, resistance,
                  buy_zone_low, buy_zone_high, sell_zone_low, sell_zone_high,
                  stop_loss, rr_t1, rr_t2)

def unusual_volume_alerts(df: pd.DataFrame, lookback_days: int, z: float, symbol: str) -> List[VolumeAlert]:
    use = df.tail(lookback_days).copy()
    use['VolMean20'] = use['Volume'].rolling(20, min_periods=10).mean()
    use['VolStd20'] = use['Volume'].rolling(20, min_periods=10).std(ddof=0)
    use['VolZ'] = (use['Volume'] - use['VolMean20']) / use['VolStd20']

    alerts: List[VolumeAlert] = []
    ema20_series = use['Close'].ewm(span=20, adjust=False).mean()
    for i in range(len(use)):
        row = use.iloc[i]
        zsc = row['VolZ']
        if pd.notna(zsc) and zsc >= z:
            direction = "up" if row['Close'] > row['Open'] else "down"
            ema20_ctx = ema20_series.iloc[i]
            if direction == "up" and row['Close'] >= ema20_ctx:
                action = "Momentum Add-on / Trail Stops Tighter"
            elif direction == "down" and row['Close'] < ema20_ctx:
                action = "Avoid Averaging Now; Wait for Stabilization"
            elif direction == "down" and row['Close'] >= ema20_ctx:
                action = "Cautious Averaging Only if Support Holds"
            else:
                action = "Review"
            alerts.append(VolumeAlert(row.name, symbol, float(row['Close']), int(row['Volume']),
                                      float(zsc), direction, action))
    return alerts

# --- NEW: robust column coercion ---
def _clean_key(s: str) -> str:
    # keep letters only to match variants like "1. open", "Open*"
    return ''.join(ch for ch in s.lower() if ch.isalpha())

def coerce_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename any reasonable OHLCV variants to standard Open/High/Low/Close/Volume."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join([c for c in tup if c]).strip() for tup in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]

    # Build mapping by fuzzy keys
    mapping = {}
    want = {
        "open": ["open", "1open", "openprice", "o"],
        "high": ["high", "2high", "h"],
        "low":  ["low", "3low", "l"],
        "close":["close", "4close", "price", "c"],
        "volume":["volume", "vol", "v"],
    }

    lower_keys = {_clean_key(c): c for c in df.columns}
    for target, candidates in want.items():
        found = None
        for cand in candidates:
            if cand in lower_keys:
                found = lower_keys[cand]
                break
        if found is None:
            # try startswith fallback (e.g., "open_x", "open*")
            for k_clean, orig in lower_keys.items():
                if k_clean.startswith(target):
                    found = orig
                    break
        if found:
            mapping[found] = target.capitalize()

    renamed = df.rename(columns=mapping)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in renamed.columns]
    if missing:
        raise ValueError(f"Missing required columns after coercion: {missing}. Raw columns: {list(df.columns)}")

    # Clean index
    renamed = renamed[~renamed.index.duplicated(keep='last')].sort_index()
    # Drop bad rows
    renamed = renamed.dropna(subset=required)

    return renamed

def compute_adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    Standard Wilder ADX.
    Requires: High, Low, Close.
    Returns ADX series.
    """
    high = df["High"].astype(float)
    low  = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move   = high.diff()
    down_move = (-low.diff())

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing = EMA with alpha=1/window (adjust=False)
    atr = tr.ewm(alpha=1/window, adjust=False).mean()
    plus_dm_sm  = pd.Series(plus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    minus_dm_sm = pd.Series(minus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()

    plus_di  = 100 * (plus_dm_sm / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm_sm / atr.replace(0, np.nan))

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/window, adjust=False).mean()
    return adx


def _pick_last_two_pivots(df: pd.DataFrame, kind: str, sr_window: int = 5) -> list:
    """
    Returns last two pivot values based on Close pivots (same pivot style as your code).
    kind: 'high' or 'low'
    """
    close_series = df["Close"].copy()
    lows_idx, highs_idx = find_pivots(close_series, window=sr_window)

    idxs = highs_idx if kind == "high" else lows_idx
    if len(idxs) < 2:
        return []
    vals = close_series.iloc[idxs].values.tolist()
    return vals[-2:]


def structure_alignment(df: pd.DataFrame, sr_window: int = 5) -> str:
    """
    Simple but realistic market-structure label:
      - Uptrend structure: Higher High + Higher Low
      - Downtrend structure: Lower High + Lower Low
      - Otherwise: Range/Mixed
    """
    highs = _pick_last_two_pivots(df, "high", sr_window=sr_window)
    lows  = _pick_last_two_pivots(df, "low",  sr_window=sr_window)

    if len(highs) < 2 or len(lows) < 2:
        return "Structure: Insufficient pivots"

    hh = highs[-1] > highs[-2]
    hl = lows[-1]  > lows[-2]
    lh = highs[-1] < highs[-2]
    ll = lows[-1]  < lows[-2]

    if hh and hl:
        return "Structure: HH-HL (Bullish)"
    if lh and ll:
        return "Structure: LH-LL (Bearish)"
    return "Structure: Mixed/Range"


def volatility_regime(df: pd.DataFrame, atr_window: int = 14) -> str:
    """
    Classifies volatility regime using:
      - ATR vs its 30-bar mean
      - ATR slope over last 5 bars
    """
    atr = compute_atr(df, window=atr_window)
    if atr is None or atr.dropna().empty:
        return "Volatility: NA"

    atr_now = float(atr.iloc[-1])
    atr_ma30 = float(atr.rolling(30, min_periods=10).mean().iloc[-1]) if len(atr) >= 10 else atr_now

    # slope proxy: change vs 5 bars ago
    if len(atr.dropna()) >= 6:
        atr_prev5 = float(atr.dropna().iloc[-6])
        slope = (atr_now - atr_prev5) / max(atr_prev5, 1e-9)
    else:
        slope = 0.0

    rel = (atr_now - atr_ma30) / max(atr_ma30, 1e-9)

    # regime thresholds tuned to be stable (avoid noisy flips)
    if rel > 0.10 and slope > 0.03:
        return "Volatility: Expanding"
    if rel < -0.10 and slope < -0.03:
        return "Volatility: Contracting"
    return "Volatility: Stable"


def volume_confirmation(df: pd.DataFrame, symbol: str, lookback_days: int = 60, z_thresh: float = 2.0) -> tuple:
    """
    Returns (Volume Confirmation label, Latest Vol ZScore).
    Uses your existing Z-score logic and also checks candle direction + EMA20 context.
    """
    use = df.tail(lookback_days).copy()
    use["EMA20"] = use["Close"].ewm(span=20, adjust=False).mean()

    use["VolMean20"] = use["Volume"].rolling(20, min_periods=10).mean()
    use["VolStd20"]  = use["Volume"].rolling(20, min_periods=10).std(ddof=0)
    use["VolZ"]      = (use["Volume"] - use["VolMean20"]) / use["VolStd20"]

    if use.dropna(subset=["VolZ"]).empty:
        return ("Volume: NA", None)

    last = use.iloc[-1]
    volz = float(last["VolZ"]) if pd.notna(last["VolZ"]) else None

    # candle direction
    is_up = float(last["Close"]) >= float(last["Open"])
    above_ema20 = float(last["Close"]) >= float(last["EMA20"]) if pd.notna(last["EMA20"]) else None

    if volz is None:
        return ("Volume: NA", None)

    if volz >= z_thresh:
        # High participation day → confirm move if it aligns with EMA context
        if is_up and above_ema20 is True:
            return ("Volume: Confirmed (Up)", volz)
        if (not is_up) and above_ema20 is False:
            return ("Volume: Confirmed (Down)", volz)
        return ("Volume: Spike (Mixed)", volz)

    # No spike: still useful to label
    if volz >= 1.0:
        return ("Volume: Elevated", volz)
    return ("Volume: Normal", volz)


def adx_strength_label(adx_value: Optional[float]) -> str:
    """
    Standard ADX interpretation.
    """
    if adx_value is None or (isinstance(adx_value, float) and pd.isna(adx_value)):
        return "ADX: NA"

    v = float(adx_value)
    if v >= 30:
        return f"ADX: {v:.1f} (Strong)"
    if v >= 20:
        return f"ADX: {v:.1f} (Moderate)"
    return f"ADX: {v:.1f} (Weak)"

# =========================================
# Core
# =========================================
def analyze_symbol(yahoo_symbol: str, lookback_days: int, volume_z: float, atr_window: int, sr_window: int,
                   risk_reward: float, data_period: str, data_interval: str) -> Dict:
    print(f"[INFO] Downloading {yahoo_symbol} period={data_period} interval={data_interval}")

    data = yf.download(
        yahoo_symbol,
        period=data_period,
        interval=data_interval,
        auto_adjust=False,
        progress=False,
        group_by="column",
        threads=False
    )

    if data is None or data.empty:
        raise ValueError(f"No data returned for {yahoo_symbol}. Check ticker or connectivity.")

    data = coerce_ohlcv_columns(data)

    # --- Core existing levels ---
    lvls = derive_levels(data, lookback_days, atr_window, sr_window, risk_reward)
    alerts = unusual_volume_alerts(data, lookback_days, z=volume_z, symbol=yahoo_symbol)

    # =========================================================
    # ✅ NEW 5 LAYERS
    # 1) Trend Direction -> lvls.trend (already)
    # 2) Trend Strength (ADX)
    # 3) Structure Alignment
    # 4) Volatility Regime
    # 5) Volume Confirmation
    # =========================================================
    use = data.tail(max(lookback_days, 60)).copy()

    # ADX
    adx_series = compute_adx(use, window=14)
    adx_val = float(adx_series.iloc[-1]) if (adx_series is not None and not adx_series.dropna().empty and pd.notna(adx_series.iloc[-1])) else None
    adx_text = adx_strength_label(adx_val)

    # Structure
    structure_text = structure_alignment(use, sr_window=sr_window)

    # Volatility regime
    vol_regime_text = volatility_regime(use, atr_window=atr_window)

    # Volume confirmation
    vol_conf_text, volz_val = volume_confirmation(use, symbol=yahoo_symbol, lookback_days=max(lookback_days, 60), z_thresh=volume_z)

    summary = {
        "Symbol": yahoo_symbol,
        "AsOfDate": pd.to_datetime(data.index[-1]).date().isoformat(),

        # Existing
        "Trend": lvls.trend,
        "Close": round(lvls.close, 2),
        "EMA20": round(lvls.ema20, 2),
        "EMA50": round(lvls.ema50, 2),
        "ATR": None if lvls.atr is None else round(lvls.atr, 2),
        "ATR%": round((lvls.atr / lvls.close) * 100, 2) if lvls.atr else None,
        "Support": None if lvls.support is None else round(lvls.support, 2),
        "Resistance": None if lvls.resistance is None else round(lvls.resistance, 2),
        "BuyZoneLow": None if lvls.buy_zone_low is None else round(lvls.buy_zone_low, 2),
        "BuyZoneHigh": None if lvls.buy_zone_high is None else round(lvls.buy_zone_high, 2),
        "SellZoneLow": None if lvls.sell_zone_low is None else round(lvls.sell_zone_low, 2),
        "SellZoneHigh": None if lvls.sell_zone_high is None else round(lvls.sell_zone_high, 2),
        "StopLoss": None if lvls.stop_loss is None else round(lvls.stop_loss, 2),
        "Target1": None if lvls.rr_target_1 is None else round(lvls.rr_target_1, 2),
        "Target2": None if lvls.rr_target_2 is None else round(lvls.rr_target_2, 2),

        # ✅ NEW 5 layers (added to Summary)
        "ADX": None if adx_val is None else round(adx_val, 2),
        "ADX_Label": adx_text,
        "Structure": structure_text,
        "VolatilityRegime": vol_regime_text,
        "VolumeConfirmation": vol_conf_text,
        "VolumeZ": None if volz_val is None else round(float(volz_val), 2),
    }

    return {"summary": summary, "alerts": alerts}


def _ist_dd_mm_yyyy():
    """Return date like DD_MM_YYYY in Asia/Kolkata timezone (fallback: local date)."""
    if ZoneInfo is not None:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    else:
        now = datetime.now()
    return now.strftime("%d_%m_%Y")

def _fmt(v):
    if v is None or (isinstance(v, float) and (pd.isna(v) or np.isinf(v))):
        return "NA"
    try:
        if isinstance(v, (int, np.integer)):
            return f"{int(v)}"
        fv = float(v)
        if abs(fv) < 0.0005:
            fv = 0.0
        return f"{fv:,.2f}"
    except Exception:
        return str(v)



# =========================================================
# NSEIndicesImageGenerator.py STYLE IMAGE CONFIG + RENDERER
# =========================================================
# These buttons intentionally follow the same tone/format structure used in
# NSEIndicesImageGenerator.py: navy gradient, rounded white card, colored banner,
# table header, soft row separators, and bottom brand handle.

PRICE_ACTION_TITLE_PREFIX = "Price Action"
PRICE_ACTION_BRAND_HANDLE = "automationintrade"
SYMBOL_MAPPING = r"../../../../AllIndexList/TopConstituentsByWeightage/"

_SYMBOL_NAME_CACHE: Optional[Dict[str, str]] = None


def _normalize_symbol_for_lookup(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        s = s.rsplit(".", 1)[0]
    return s


def _format_stock_display_name(name: str) -> str:
    raw = " ".join(str(name or "").strip().split())
    return raw.title() if raw else ""


def _load_symbol_name_cache(mapping_dir: str = SYMBOL_MAPPING) -> Dict[str, str]:
    global _SYMBOL_NAME_CACHE
    if _SYMBOL_NAME_CACHE is not None:
        return _SYMBOL_NAME_CACHE

    cache: Dict[str, str] = {}
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        resolved_dir = mapping_dir if os.path.isabs(mapping_dir) else os.path.abspath(os.path.join(base_dir, mapping_dir))
        if os.path.isdir(resolved_dir):
            for fname in os.listdir(resolved_dir):
                fpath = os.path.join(resolved_dir, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext not in {".xlsx", ".xls", ".csv"}:
                    continue
                try:
                    if ext == ".csv":
                        mdf = pd.read_csv(fpath)
                    else:
                        mdf = pd.read_excel(fpath)
                    if not {"Symbol", "Stock"}.issubset(mdf.columns):
                        continue
                    sub = mdf[["Symbol", "Stock"]].dropna(subset=["Symbol", "Stock"])
                    for _, row in sub.iterrows():
                        sym = _normalize_symbol_for_lookup(row.get("Symbol"))
                        stock_name = _format_stock_display_name(row.get("Stock"))
                        if sym and stock_name and sym not in cache:
                            cache[sym] = stock_name
                except Exception:
                    continue
    except Exception:
        pass

    _SYMBOL_NAME_CACHE = cache
    return cache


def _resolve_stock_display_name(raw_symbol: str, yahoo_symbol: Optional[str] = None, stock_name_hint: Optional[str] = None) -> str:
    # 1) direct hint from input stock file
    hint = _format_stock_display_name(stock_name_hint)
    if hint:
        return hint

    # 2) offline Excel / CSV fallback mapping
    lookup_symbol = _normalize_symbol_for_lookup(raw_symbol)
    cache = _load_symbol_name_cache(SYMBOL_MAPPING)
    if lookup_symbol in cache:
        return cache[lookup_symbol]

    # 3) optional online lookup via yfinance if available
    ticker_candidates = [yahoo_symbol, raw_symbol]
    for ticker_symbol in ticker_candidates:
        if not ticker_symbol:
            continue
        try:
            tk = yf.Ticker(str(ticker_symbol))
            info = tk.info or {}
            for key in ("longName", "shortName", "displayName", "name"):
                val = _format_stock_display_name(info.get(key))
                if val:
                    return val
        except Exception:
            pass

    # 4) final fallback: keep symbol readable
    return _format_stock_display_name(lookup_symbol) or str(raw_symbol).strip()

GENERATE_GENERAL_IMAGE = True
GENERATE_INSTAGRAM_IMAGE = True
GENERATE_STANDARD_IMAGE = True
GENERATE_REELS_IMAGE = True

GENERAL_IMAGE_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/General/{SYMBOL}.jpeg"
INSTAGRAM_IMAGE_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/Instagram/{SYMBOL}.jpeg"
STANDARD_IMAGE_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/Standard/{SYMBOL}.jpeg"
REELS_IMAGE_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/Reels/{SYMBOL}.jpeg"

PRICE_ACTION_SHOW_DISCLAIMER = True
PRICE_ACTION_DISCLAIMER_TEXT = "Disclaimer: Data-based estimate only. Not investment advice."

# ---------------- GENERAL IMAGE BUTTONS ----------------
GENERAL_FIG_W = 7.5
GENERAL_FIG_H = 10.70
GENERAL_DPI = 160
GENERAL_TITLE_Y = 105
GENERAL_SUBTITLE_Y_OFFSET = 82
GENERAL_CARD_TOP = 245
GENERAL_CARD_SIDE_PAD = 78
GENERAL_CARD_INNER_PAD = 34
GENERAL_CARD_BOTTOM_MARGIN = 165
GENERAL_BANNER_H = 92
GENERAL_GAP_AFTER_BANNER = 24
GENERAL_HEADER_H = 74
GENERAL_ROW_H = 58
GENERAL_TITLE_FONT_SIZE = 68
GENERAL_SUBTITLE_FONT_SIZE = 28
GENERAL_BANNER_FONT_SIZE = 44
GENERAL_HEADER_FONT_SIZE =34
GENERAL_CELL_FONT_SIZE = 34
GENERAL_CELL_BOLD_FONT_SIZE = 34
GENERAL_FOOTER_FONT_SIZE = 36
GENERAL_HANDLE_Y = -135
GENERAL_CARD_BOTTOM_EXTRA = 0
GENERAL_DISCLAIMER_FONT_SIZE = 26
GENERAL_DISCLAIMER_GAP_ABOVE = 18
GENERAL_DISCLAIMER_BOTTOM_PAD = 16

# ---------------- INSTAGRAM IMAGE BUTTONS ----------------
INSTAGRAM_FIG_W = 8.0
INSTAGRAM_FIG_H = 10.0
INSTAGRAM_DPI = 160
INSTAGRAM_TITLE_Y = 90
INSTAGRAM_SUBTITLE_Y_OFFSET = 82
INSTAGRAM_CARD_TOP = 225
INSTAGRAM_CARD_SIDE_PAD = 70
INSTAGRAM_CARD_INNER_PAD = 30
INSTAGRAM_CARD_BOTTOM_MARGIN = 155
INSTAGRAM_BANNER_H = 88
INSTAGRAM_GAP_AFTER_BANNER = 22
INSTAGRAM_HEADER_H = 70
INSTAGRAM_ROW_H = 53
INSTAGRAM_TITLE_FONT_SIZE = 66
INSTAGRAM_SUBTITLE_FONT_SIZE = 28
INSTAGRAM_BANNER_FONT_SIZE = 42
INSTAGRAM_HEADER_FONT_SIZE = 34
INSTAGRAM_CELL_FONT_SIZE = 32
INSTAGRAM_CELL_BOLD_FONT_SIZE = 32
INSTAGRAM_FOOTER_FONT_SIZE = 36
INSTAGRAM_HANDLE_Y = -130
INSTAGRAM_CARD_BOTTOM_EXTRA = 0
INSTAGRAM_DISCLAIMER_FONT_SIZE = 28
INSTAGRAM_DISCLAIMER_GAP_ABOVE = 16
INSTAGRAM_DISCLAIMER_BOTTOM_PAD = 14

# ---------------- STANDARD IMAGE BUTTONS ----------------
STANDARD_FIG_W = 16.0
STANDARD_FIG_H = 9.0
STANDARD_DPI = 100
STANDARD_TITLE_Y = 70
STANDARD_SUBTITLE_Y_OFFSET = 48
STANDARD_CARD_TOP = 165
STANDARD_CARD_SIDE_PAD = 95
STANDARD_CARD_INNER_PAD = 26
STANDARD_CARD_BOTTOM_MARGIN = 80
STANDARD_BANNER_H = 72
STANDARD_GAP_AFTER_BANNER = 16
STANDARD_HEADER_H = 50
STANDARD_ROW_H = 31
STANDARD_TITLE_FONT_SIZE = 50
STANDARD_SUBTITLE_FONT_SIZE = 21
STANDARD_BANNER_FONT_SIZE = 30
STANDARD_HEADER_FONT_SIZE = 20
STANDARD_CELL_FONT_SIZE = 17
STANDARD_CELL_BOLD_FONT_SIZE = 17
STANDARD_FOOTER_FONT_SIZE = 25
STANDARD_HANDLE_Y = -55
STANDARD_CARD_BOTTOM_EXTRA = 0
STANDARD_DISCLAIMER_FONT_SIZE = 13
STANDARD_DISCLAIMER_GAP_ABOVE = 12
STANDARD_DISCLAIMER_BOTTOM_PAD = 14

# ---------------- REELS IMAGE BUTTONS ----------------
REELS_FIG_W = 10.0
REELS_FIG_H = 15.0
REELS_DPI = 120
REELS_TITLE_Y = 120
REELS_SUBTITLE_Y_OFFSET = 96
REELS_CARD_TOP = 255
REELS_CARD_SIDE_PAD = 72
REELS_CARD_INNER_PAD = 30
REELS_CARD_BOTTOM_MARGIN = 140
REELS_BANNER_H = 96
REELS_GAP_AFTER_BANNER = 24
REELS_HEADER_H = 78
REELS_ROW_H = 65
REELS_TITLE_FONT_SIZE = 68
REELS_SUBTITLE_FONT_SIZE = 30
REELS_BANNER_FONT_SIZE = 42
REELS_HEADER_FONT_SIZE = 32
REELS_CELL_FONT_SIZE = 32
REELS_CELL_BOLD_FONT_SIZE = 32
REELS_FOOTER_FONT_SIZE = 34
REELS_HANDLE_Y = -95
REELS_CARD_BOTTOM_EXTRA = 0
REELS_DISCLAIMER_FONT_SIZE = 18
REELS_DISCLAIMER_GAP_ABOVE = 18
REELS_DISCLAIMER_BOTTOM_PAD = 18


def _price_action_safe_symbol(symbol: str) -> str:
    return str(symbol).strip().replace("/", "_").replace("\\", "_").replace(" ", "_") or "SYMBOL"


def _price_action_output_path(template: str, summary: Dict) -> str:
    symbol = _price_action_safe_symbol(summary.get("Symbol", "SYMBOL"))
    out_path = template.replace("{DATE_FOLDER}", _ist_dd_mm_yyyy()).replace("{SYMBOL}", symbol)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return out_path


def _pa_layout(image_mode: str = "general") -> dict:
    mode = str(image_mode or "general").strip().lower()
    if mode == "instagram":
        return {
            "size": (int(INSTAGRAM_FIG_W * INSTAGRAM_DPI), int(INSTAGRAM_FIG_H * INSTAGRAM_DPI)),
            "title_y": INSTAGRAM_TITLE_Y,
            "subtitle_y_offset": INSTAGRAM_SUBTITLE_Y_OFFSET,
            "card_top": INSTAGRAM_CARD_TOP,
            "card_side_pad": INSTAGRAM_CARD_SIDE_PAD,
            "card_inner_pad": INSTAGRAM_CARD_INNER_PAD,
            "card_bottom_margin": INSTAGRAM_CARD_BOTTOM_MARGIN,
            "banner_h": INSTAGRAM_BANNER_H,
            "gap_after_banner": INSTAGRAM_GAP_AFTER_BANNER,
            "header_h": INSTAGRAM_HEADER_H,
            "row_h": INSTAGRAM_ROW_H,
            "title_font_size": INSTAGRAM_TITLE_FONT_SIZE,
            "subtitle_font_size": INSTAGRAM_SUBTITLE_FONT_SIZE,
            "banner_font_size": INSTAGRAM_BANNER_FONT_SIZE,
            "header_font_size": INSTAGRAM_HEADER_FONT_SIZE,
            "cell_font_size": INSTAGRAM_CELL_FONT_SIZE,
            "cell_bold_font_size": INSTAGRAM_CELL_BOLD_FONT_SIZE,
            "footer_font_size": INSTAGRAM_FOOTER_FONT_SIZE,
            "handle_y": INSTAGRAM_HANDLE_Y,
            "card_bottom_extra": INSTAGRAM_CARD_BOTTOM_EXTRA,
            "disclaimer_font_size": INSTAGRAM_DISCLAIMER_FONT_SIZE,
            "disclaimer_gap_above": INSTAGRAM_DISCLAIMER_GAP_ABOVE,
            "disclaimer_bottom_pad": INSTAGRAM_DISCLAIMER_BOTTOM_PAD,
        }
    if mode == "standard":
        return {
            "size": (int(STANDARD_FIG_W * STANDARD_DPI), int(STANDARD_FIG_H * STANDARD_DPI)),
            "title_y": STANDARD_TITLE_Y,
            "subtitle_y_offset": STANDARD_SUBTITLE_Y_OFFSET,
            "card_top": STANDARD_CARD_TOP,
            "card_side_pad": STANDARD_CARD_SIDE_PAD,
            "card_inner_pad": STANDARD_CARD_INNER_PAD,
            "card_bottom_margin": STANDARD_CARD_BOTTOM_MARGIN,
            "banner_h": STANDARD_BANNER_H,
            "gap_after_banner": STANDARD_GAP_AFTER_BANNER,
            "header_h": STANDARD_HEADER_H,
            "row_h": STANDARD_ROW_H,
            "title_font_size": STANDARD_TITLE_FONT_SIZE,
            "subtitle_font_size": STANDARD_SUBTITLE_FONT_SIZE,
            "banner_font_size": STANDARD_BANNER_FONT_SIZE,
            "header_font_size": STANDARD_HEADER_FONT_SIZE,
            "cell_font_size": STANDARD_CELL_FONT_SIZE,
            "cell_bold_font_size": STANDARD_CELL_BOLD_FONT_SIZE,
            "footer_font_size": STANDARD_FOOTER_FONT_SIZE,
            "handle_y": STANDARD_HANDLE_Y,
            "card_bottom_extra": STANDARD_CARD_BOTTOM_EXTRA,
            "disclaimer_font_size": STANDARD_DISCLAIMER_FONT_SIZE,
            "disclaimer_gap_above": STANDARD_DISCLAIMER_GAP_ABOVE,
            "disclaimer_bottom_pad": STANDARD_DISCLAIMER_BOTTOM_PAD,
        }
    if mode == "reels":
        return {
            "size": (int(REELS_FIG_W * REELS_DPI), int(REELS_FIG_H * REELS_DPI)),
            "title_y": REELS_TITLE_Y,
            "subtitle_y_offset": REELS_SUBTITLE_Y_OFFSET,
            "card_top": REELS_CARD_TOP,
            "card_side_pad": REELS_CARD_SIDE_PAD,
            "card_inner_pad": REELS_CARD_INNER_PAD,
            "card_bottom_margin": REELS_CARD_BOTTOM_MARGIN,
            "banner_h": REELS_BANNER_H,
            "gap_after_banner": REELS_GAP_AFTER_BANNER,
            "header_h": REELS_HEADER_H,
            "row_h": REELS_ROW_H,
            "title_font_size": REELS_TITLE_FONT_SIZE,
            "subtitle_font_size": REELS_SUBTITLE_FONT_SIZE,
            "banner_font_size": REELS_BANNER_FONT_SIZE,
            "header_font_size": REELS_HEADER_FONT_SIZE,
            "cell_font_size": REELS_CELL_FONT_SIZE,
            "cell_bold_font_size": REELS_CELL_BOLD_FONT_SIZE,
            "footer_font_size": REELS_FOOTER_FONT_SIZE,
            "handle_y": REELS_HANDLE_Y,
            "card_bottom_extra": REELS_CARD_BOTTOM_EXTRA,
            "disclaimer_font_size": REELS_DISCLAIMER_FONT_SIZE,
            "disclaimer_gap_above": REELS_DISCLAIMER_GAP_ABOVE,
            "disclaimer_bottom_pad": REELS_DISCLAIMER_BOTTOM_PAD,
        }
    return {
        "size": (int(GENERAL_FIG_W * GENERAL_DPI), int(GENERAL_FIG_H * GENERAL_DPI)),
        "title_y": GENERAL_TITLE_Y,
        "subtitle_y_offset": GENERAL_SUBTITLE_Y_OFFSET,
        "card_top": GENERAL_CARD_TOP,
        "card_side_pad": GENERAL_CARD_SIDE_PAD,
        "card_inner_pad": GENERAL_CARD_INNER_PAD,
        "card_bottom_margin": GENERAL_CARD_BOTTOM_MARGIN,
        "banner_h": GENERAL_BANNER_H,
        "gap_after_banner": GENERAL_GAP_AFTER_BANNER,
        "header_h": GENERAL_HEADER_H,
        "row_h": GENERAL_ROW_H,
        "title_font_size": GENERAL_TITLE_FONT_SIZE,
        "subtitle_font_size": GENERAL_SUBTITLE_FONT_SIZE,
        "banner_font_size": GENERAL_BANNER_FONT_SIZE,
        "header_font_size": GENERAL_HEADER_FONT_SIZE,
        "cell_font_size": GENERAL_CELL_FONT_SIZE,
        "cell_bold_font_size": GENERAL_CELL_BOLD_FONT_SIZE,
        "footer_font_size": GENERAL_FOOTER_FONT_SIZE,
        "handle_y": GENERAL_HANDLE_Y,
        "card_bottom_extra": GENERAL_CARD_BOTTOM_EXTRA,
        "disclaimer_font_size": GENERAL_DISCLAIMER_FONT_SIZE,
        "disclaimer_gap_above": GENERAL_DISCLAIMER_GAP_ABOVE,
        "disclaimer_bottom_pad": GENERAL_DISCLAIMER_BOTTOM_PAD,
    }


def _pa_load_font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = []
    win_dir = r"C:\Windows\Fonts"
    if os.path.isdir(win_dir):
        candidates += [
            os.path.join(win_dir, "calibrib.ttf" if bold else "calibri.ttf"),
            os.path.join(win_dir, "arialbd.ttf" if bold else "arial.ttf"),
            os.path.join(win_dir, "seguisb.ttf" if bold else "segoeui.ttf"),
        ]
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for fp in candidates:
        try:
            if fp and os.path.exists(fp):
                return ImageFont.truetype(fp, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _pa_center(draw, W, text, y, font, fill):
    text = str(text)
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill)


def _pa_text_height(draw, text, font) -> int:
    """Return rendered text height for accurate vertical centering."""
    try:
        bbox = draw.textbbox((0, 0), str(text), font=font)
        return max(1, bbox[3] - bbox[1])
    except Exception:
        return max(1, getattr(font, "size", 16))


def _pa_wrap_text(draw, text: str, font, max_width: int):
    text = "" if text is None else str(text)
    if not text:
        return [""]
    words = text.split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines or [text]


def _pa_draw_vertical_gradient(img, top_color=(10, 28, 52), bottom_color=(6, 16, 32)):
    from PIL import Image
    w, h = img.size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    tr, tg, tb = top_color
    br, bg, bb = bottom_color
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(tr + (br - tr) * t)
        g = int(tg + (bg - tg) * t)
        b = int(tb + (bb - tb) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    img.paste(grad, (0, 0))


def _pa_add_vignette(img, strength=0.40):
    from PIL import Image, ImageDraw, ImageFilter
    w, h = img.size
    vignette = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(vignette)
    margin = int(min(w, h) * 0.08)
    draw.ellipse([margin, margin, w - margin, h - margin], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=int(min(w, h) * 0.07)))
    inv = Image.eval(vignette, lambda p: 255 - p)
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    img.paste(overlay, (0, 0), Image.eval(inv, lambda p: int(p * strength)))


def _pa_rounded_shadow_card(base_img, box, radius=30, shadow_offset=(0, 14), shadow_blur=22,
                            shadow_color=(0, 0, 0, 125), fill=(255, 255, 255),
                            outline=(26, 52, 82), outline_w=3):
    from PIL import Image, ImageDraw, ImageFilter
    l, t, r, b = box
    w, h = r - l, b - t
    shadow = Image.new("RGBA", (w + shadow_blur * 4, h + shadow_blur * 4), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([shadow_blur * 2, shadow_blur * 2, shadow_blur * 2 + w, shadow_blur * 2 + h],
                         radius=radius, fill=shadow_color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    sx = l + shadow_offset[0] - shadow_blur * 2
    sy = t + shadow_offset[1] - shadow_blur * 2
    base_img.paste(shadow, (sx, sy), shadow)

    card_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_layer)
    cd.rounded_rectangle([l, t, r, b], radius=radius, fill=fill)

    highlight = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rectangle([l + 2, t + 2, r - 2, t + 18], fill=(255, 255, 255, 150))
    mask = Image.new("L", base_img.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([l, t, r, b], radius=radius, fill=255)
    clipped = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    clipped.paste(highlight, (0, 0), mask)
    card_layer = Image.alpha_composite(card_layer, clipped)

    cd = ImageDraw.Draw(card_layer)
    cd.rounded_rectangle([l, t, r, b], radius=radius, outline=outline, width=outline_w)
    cd.rounded_rectangle([l + 6, t + 6, r - 6, b - 6], radius=max(4, radius - 6), outline=(210, 220, 232), width=2)
    base_img.paste(card_layer, (0, 0), card_layer)


def _price_action_rows(summary: Dict):
    return [
        ("Trend", summary.get("Trend")),
        ("Trend Strength (ADX)", summary.get("ADX_Label", summary.get("ADX"))),
        ("Structure Alignment", summary.get("Structure")),
        ("Volatility Regime", summary.get("VolatilityRegime")),
        ("Volume Confirmation", f"{summary.get('VolumeConfirmation')} (Z: {_fmt(summary.get('VolumeZ'))})"),
        ("Close", summary.get("Close")),
        ("EMA20", summary.get("EMA20")),
        ("EMA50", summary.get("EMA50")),
        ("ATR", summary.get("ATR")),
        ("ATR%", summary.get("ATR%")),
        ("Support", summary.get("Support")),
        ("Resistance", summary.get("Resistance")),
        ("Buy Zone", f"{_fmt(summary.get('BuyZoneLow'))} → {_fmt(summary.get('BuyZoneHigh'))}"),
        ("Sell Zone", f"{_fmt(summary.get('SellZoneLow'))} → {_fmt(summary.get('SellZoneHigh'))}"),
        ("StopLoss", summary.get("StopLoss")),
        ("Target 1", summary.get("Target1")),
        ("Target 2", summary.get("Target2")),
    ]


def _pa_banner_color(verdict: str):
    v = str(verdict or "").strip().upper()
    if v == "UPTREND":
        return (46, 139, 87)
    if v == "DOWNTREND":
        return (190, 57, 43)
    return (180, 128, 34)


def _pa_value_color(label: str):
    if label == "StopLoss":
        return (200, 35, 35)
    if label in {"Target 1", "Target 2"}:
        return (20, 130, 75)
    if label in {"Support", "Buy Zone"}:
        return (20, 120, 75)
    if label in {"Resistance", "Sell Zone"}:
        return (190, 55, 45)
    return (20, 30, 50)


def generate_price_action_image(summary: Dict, out_path: str,
                                slogan: str = "Smart Trading. Zero Emotion. Full Automation.",
                                image_mode: str = "general") -> None:
    """
    Render one Price Action image in the same premium tone/format as
    NSEIndicesImageGenerator.py. Use image_mode: general, instagram, standard, reels.
    """
    from PIL import Image, ImageDraw

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    cfg = _pa_layout(image_mode)
    W, H = cfg["size"]
    img = Image.new("RGB", (W, H), (10, 24, 45))
    _pa_draw_vertical_gradient(img, top_color=(10, 28, 52), bottom_color=(6, 16, 32))
    _pa_add_vignette(img, strength=0.40)
    draw = ImageDraw.Draw(img)

    symbol = _price_action_safe_symbol(summary.get("Symbol", "SYMBOL"))
    display_name = _format_stock_display_name(summary.get("DisplayName", "")) or _format_stock_display_name(summary.get("Symbol", "SYMBOL"))
    as_of = str(summary.get("AsOfDate", "NA"))
    verdict = str(summary.get("Verdict", summary.get("Trend", "NA"))).upper()

    f_title = _pa_load_font(cfg["title_font_size"], bold=True)
    f_subtitle = _pa_load_font(cfg["subtitle_font_size"], bold=True)
    f_banner = _pa_load_font(cfg["banner_font_size"], bold=True)
    f_header = _pa_load_font(cfg["header_font_size"], bold=True)
    f_cell = _pa_load_font(cfg["cell_font_size"], bold=False)
    f_cell_b = _pa_load_font(cfg["cell_bold_font_size"], bold=True)
    f_footer = _pa_load_font(cfg["footer_font_size"], bold=True)
    f_disclaimer = _pa_load_font(cfg["disclaimer_font_size"], bold=True)

    title_text = display_name
    _pa_center(draw, W, title_text, cfg["title_y"], f_title, (243, 198, 65))
    _pa_center(draw, W, f"As of: {as_of}  |  Price Action Insights", cfg["title_y"] + cfg["subtitle_y_offset"], f_subtitle, (210, 220, 235))

    pad = cfg["card_side_pad"]
    inner_pad = cfg["card_inner_pad"]
    card_top = cfg["card_top"]
    max_card_bottom = H - cfg["card_bottom_margin"]
    table_top = (card_top + inner_pad) + cfg["banner_h"] + cfg["gap_after_banner"]
    table_rows_top = table_top + cfg["header_h"]
    rows = _price_action_rows(summary)
    row_h = cfg["row_h"]
    disclaimer_text = PRICE_ACTION_DISCLAIMER_TEXT if PRICE_ACTION_SHOW_DISCLAIMER else ""
    disclaimer_text_h = _pa_text_height(draw, disclaimer_text, f_disclaimer) if disclaimer_text else 0
    disclaimer_block_h = 0
    if disclaimer_text:
        disclaimer_block_h = cfg["disclaimer_gap_above"] + disclaimer_text_h + cfg["disclaimer_bottom_pad"]
    dynamic_card_bottom = table_rows_top + (len(rows) * row_h) + inner_pad + disclaimer_block_h + cfg.get("card_bottom_extra", 0)
    card_bottom = min(dynamic_card_bottom, max_card_bottom)

    # If the selected mode is too short for all rows, compress row height slightly instead of clipping.
    available_rows_h = max(1, (max_card_bottom - inner_pad - disclaimer_block_h) - table_rows_top)
    if len(rows) * row_h > available_rows_h:
        row_h = max(22, int(available_rows_h / max(len(rows), 1)))
        dynamic_card_bottom = table_rows_top + (len(rows) * row_h) + inner_pad + disclaimer_block_h
        card_bottom = min(dynamic_card_bottom, max_card_bottom)

    card_left, card_right = pad, W - pad
    _pa_rounded_shadow_card(
        img,
        [card_left, card_top, card_right, card_bottom],
        radius=30,
        shadow_offset=(0, 14),
        shadow_blur=22,
        shadow_color=(0, 0, 0, 125),
        fill=(255, 255, 255),
        outline=(26, 52, 82),
        outline_w=3,
    )
    draw = ImageDraw.Draw(img)

    inner_left = card_left + inner_pad
    inner_right = card_right - inner_pad
    inner_top = card_top + inner_pad
    table_w = inner_right - inner_left

    banner_color = _pa_banner_color(verdict)
    banner_text = f"CURRENT TREND: {verdict}"
    pill_l, pill_r = inner_left, inner_right
    pill_t, pill_b = inner_top, inner_top + cfg["banner_h"]
    draw.rounded_rectangle([pill_l, pill_t, pill_r, pill_b], radius=26, fill=banner_color)
    tw = draw.textlength(banner_text, font=f_banner)
    try:
        bbox = draw.textbbox((0, 0), banner_text, font=f_banner)
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_h = f_banner.size
    draw.text((pill_l + (pill_r - pill_l - tw) / 2, pill_t + ((cfg["banner_h"] - text_h) / 2) - 2),
              banner_text, font=f_banner, fill=(255, 255, 255))

    HEADER_BG = (220, 228, 240)
    GRID = (228, 233, 240)
    ROW_ALT = (246, 248, 252)
    TXT = (20, 30, 50)

    # Table header
    param_w = int(table_w * 0.43)
    x0 = inner_left
    x1 = inner_left + param_w
    x2 = inner_right
    draw.rectangle([x0, table_top, x2, table_top + cfg["header_h"]], fill=HEADER_BG)
    draw.line([x1, table_top, x1, table_top + cfg["header_h"]], fill=GRID, width=2)
    header_text_h = _pa_text_height(draw, "Parameter", f_header)
    header_y = table_top + (cfg["header_h"] - header_text_h) / 2
    draw.text((x0 + 14, header_y), "Parameter", font=f_header, fill=TXT)
    draw.text((x1 + 14, header_y), "Value", font=f_header, fill=TXT)

    # Table rows
    y = table_rows_top
    for i, (label, value) in enumerate(rows):
        fill = ROW_ALT if i % 2 else (255, 255, 255)
        draw.rectangle([x0, y, x2, y + row_h], fill=fill)
        draw.line([x0, y, x2, y], fill=GRID, width=2)
        draw.line([x1, y, x1, y + row_h], fill=GRID, width=2)

        label_font = f_cell
        value_font = f_cell_b if label in {"StopLoss", "Target 1", "Target 2"} else f_cell
        value_text = value if label in {"Buy Zone", "Sell Zone", "Trend Strength (ADX)", "Structure Alignment", "Volatility Regime", "Volume Confirmation", "Trend"} else _fmt(value)
        value_text = "" if value_text is None else str(value_text)

        label_text_h = _pa_text_height(draw, str(label), label_font)
        label_y = y + (row_h - label_text_h) / 2
        draw.text((x0 + 14, label_y), str(label), font=label_font, fill=TXT)

        max_value_w = max(50, (x2 - x1) - 28)
        lines = _pa_wrap_text(draw, value_text, value_font, max_value_w)
        if len(lines) > 2:
            lines = lines[:2]
            while draw.textlength(lines[-1] + "…", font=value_font) > max_value_w and len(lines[-1]) > 1:
                lines[-1] = lines[-1][:-1]
            lines[-1] = lines[-1] + "…"
        if not lines:
            lines = [""]
        line_heights = [_pa_text_height(draw, ln if ln else "Ag", value_font) for ln in lines]
        line_gap = max(2, int(row_h * 0.06))
        total_h = sum(line_heights) + (line_gap * (len(lines) - 1))
        yy = y + (row_h - total_h) / 2
        for ln, ln_h in zip(lines, line_heights):
            draw.text((x1 + 14, yy), ln, font=value_font, fill=_pa_value_color(label))
            yy += ln_h + line_gap
        y += row_h

    draw.line([x0, y, x2, y], fill=GRID, width=2)

    if disclaimer_text:
        disclaimer_y = max(
            y + cfg["disclaimer_gap_above"],
            card_bottom - inner_pad - cfg["disclaimer_bottom_pad"] - disclaimer_text_h,
        )
        _pa_center(draw, W, disclaimer_text, disclaimer_y, f_disclaimer, (90, 105, 125))

    # Footer handle in same NSE tone.
    handle_y = H + cfg["handle_y"]
    _pa_center(draw, W, PRICE_ACTION_BRAND_HANDLE, handle_y, f_footer, (255, 255, 255))

    img.save(out_path, format="JPEG", quality=95, subsampling=0, optimize=True)


def generate_price_action_all_images(summary: Dict) -> List[str]:
    """Generate the four image variants: General, Instagram, Standard, Reels."""
    generated = []
    variants = [
        ("general", GENERATE_GENERAL_IMAGE, GENERAL_IMAGE_OUTPUT_TEMPLATE),
        ("instagram", GENERATE_INSTAGRAM_IMAGE, INSTAGRAM_IMAGE_OUTPUT_TEMPLATE),
        ("standard", GENERATE_STANDARD_IMAGE, STANDARD_IMAGE_OUTPUT_TEMPLATE),
        ("reels", GENERATE_REELS_IMAGE, REELS_IMAGE_OUTPUT_TEMPLATE),
    ]
    for mode, enabled, template in variants:
        if not enabled:
            continue
        out_path = _price_action_output_path(template, summary)
        generate_price_action_image(summary=summary, out_path=out_path, image_mode=mode)
        generated.append(out_path)
        print(f"  🖼️ Saved {mode.title()} Price Action image: {os.path.abspath(out_path)}")
    return generated


def generate_instagram_size_image(summary: Dict) -> None:
    """
    Backward-compatible wrapper. The new Instagram output follows the same
    NSEIndicesImageGenerator.py tone and is saved under Images/{DATE}/Instagram/.
    """
    out_path = _price_action_output_path(INSTAGRAM_IMAGE_OUTPUT_TEMPLATE, summary)
    generate_price_action_image(summary=summary, out_path=out_path, image_mode="instagram")
    print("  📸 Saved Instagram image:", os.path.abspath(out_path))

def _ist_timestamp_for_filename():
    """Return stamp like 2025-07-13-6AM in Asia/Kolkata timezone."""
    if ZoneInfo is not None:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    else:
        # Fallback without zoneinfo; will use local time
        now = datetime.now()
    date_part = now.strftime("%Y-%m-%d")
    hour_12 = now.strftime("%I").lstrip("0") or "12"  # no leading zero
    ampm = now.strftime("%p")                         # AM / PM
    return f"{date_part}-{hour_12}{ampm}"

def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    st = {}
    for _, r in df.iterrows():
        st[r["Symbol"]] = Position(
            Symbol=r["Symbol"], Side=r["Side"], Status=r["Status"],
            Entry=float(r["Entry"]), ATR_Entry=float(r["ATR_Entry"]),
            Stop=float(r["Stop"]), T1=float(r["T1"]), T2=float(r["T2"]),
            Hit_T1=int(r.get("Hit_T1", 0)), Hit_T2=int(r.get("Hit_T2", 0)),
            BarsSinceEntry=int(r.get("BarsSinceEntry", 0)),
            CreatedAt=str(r.get("CreatedAt", "")), LastUpdate=str(r.get("LastUpdate", "")),
        )
    return st

def save_state(path: str, state: dict) -> None:
    rows = []
    for sym, p in state.items():
        rows.append({
            "Symbol": p.Symbol, "Side": p.Side, "Status": p.Status,
            "Entry": p.Entry, "ATR_Entry": p.ATR_Entry, "Stop": p.Stop,
            "T1": p.T1, "T2": p.T2, "Hit_T1": p.Hit_T1, "Hit_T2": p.Hit_T2,
            "BarsSinceEntry": p.BarsSinceEntry, "CreatedAt": p.CreatedAt, "LastUpdate": p.LastUpdate
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def main():
    # --- Pre-parse to get --env (so we can load defaults before building full parser) ---
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--env", type=str, default=os.environ.get("ENV_FILE", ".env"),
                     help="Path to .env file (default: ENV_FILE env var or ./.env)")
    pre_args, _ = pre.parse_known_args()

    env = load_dotenv_file(pre_args.env)
    if env:
        print(f"[INFO] Loaded .env defaults from: {os.path.abspath(pre_args.env)}")
    else:
        print(f"[INFO] No .env loaded (missing/empty): {os.path.abspath(pre_args.env)}")

    parser = argparse.ArgumentParser(description="Price Action Recommender — batch via Stock.xlsx or single --symbol")
    parser.add_argument("--env", type=str, default=pre_args.env, help="Path to .env file (loaded before args parsing)")
    parser.add_argument("--symbol", type=str, default=_env_default(env, "SYMBOL", None),
                        help="Single Yahoo ticker, e.g., RELIANCE.NS. If omitted, loads from --stock_file.")
    parser.add_argument("--stock_file", type=str, default=_env_default(env, "STOCK_FILE", "../../../../../../../Stock.xlsx"),
                        help="Path to Stock.xlsx (UnderlyingScrip, Symbol, Segment, UseOptionSentiment)")
    parser.add_argument("--only_use_option_sentiment", action="store_true",
                        help="Process only rows where UseOptionSentiment is TRUE/1/Yes")
    parser.add_argument("--reanchor_max_bars", type=int, default=_parse_int(_env_default(env, "REANCHOR_MAX_BARS", 15), 15),
                    help="Re-anchor or exit if T1 not hit within N bars")
    parser.add_argument("--reanchor_atr_pct", type=float, default=_parse_float(_env_default(env, "REANCHOR_ATR_PCT", 0.25), 0.25),
                        help="Re-anchor if ATR changes by >= this fraction vs ATR at entry (e.g., 0.25 = 25%)")
    parser.add_argument("--exit_on_trend_flip", action="store_true", default=_parse_bool(_env_default(env, "EXIT_ON_TREND_FLIP", "true"), True),
                        help="Exit if trend flips against the open position")
    parser.add_argument("--lookback_days", type=int, default=_parse_int(_env_default(env, "LOOKBACK_DAYS", 60), 60))
    parser.add_argument("--volume_z", type=float, default=_parse_float(_env_default(env, "VOLUME_Z", 2.0), 2.0))
    parser.add_argument("--atr_window", type=int, default=_parse_int(_env_default(env, "ATR_WINDOW", 14), 14))
    parser.add_argument("--sr_window", type=int, default=_parse_int(_env_default(env, "SR_WINDOW", 5), 5))
    parser.add_argument("--risk_reward", type=float, default=_parse_float(_env_default(env, "RISK_REWARD", 2.0), 2.0))
    parser.add_argument("--save_csv", action="store_true", default=_parse_bool(_env_default(env, "SAVE_CSV", "true"), True),
                        help="Always save CSVs (default: True)")
    parser.add_argument("--outdir", type=str, default=_env_default(env, "OUTDIR", "./PriceActionOutputs"),
                        help="Output directory for CSVs (default: ./PriceActionOutputs)")

    parser.add_argument("--price_action_image", action="store_true",
                        default=_parse_bool(_env_default(env, "PRICE_ACTION_IMAGE", "false"), False),
                        help="If enabled, generates branded JPEG per symbol at Images/SYMBOL_DD_MM_YYYY.jpeg")

    parser.add_argument("--state_csv", type=str, default=_env_default(env, "STATE_CSV", "./PriceActionOutputs/TradeState.csv"),
                        help="Persists open trades so targets remain anchored")
    parser.add_argument("--data_interval", type=str, default=_env_default(env, "DATA_INTERVAL", "1d"),
                    help="yfinance interval: 1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo")
    parser.add_argument("--data_period", type=str, default=_env_default(env, "DATA_PERIOD", "120d"),
                    help="yfinance period: e.g. 7d, 30d, 120d, 1y, 5y")


    args = parser.parse_args()
    # If not explicitly enabled via CLI, allow .env to turn it on
    if not args.only_use_option_sentiment:
        args.only_use_option_sentiment = _parse_bool(env.get("ONLY_USE_OPTION_SENTIMENT"), False)

    print(f"[INFO] stock_file: {os.path.abspath(args.stock_file)}")
    print(f"[INFO] outdir    : {os.path.abspath(args.outdir)}")
    print(f"[INFO] save_csv  : {args.save_csv}")
    print(f"[INFO] state_csv : {os.path.abspath(args.state_csv)}")


    os.makedirs(args.outdir, exist_ok=True)
    state = load_state(args.state_csv)

    symbol_pairs: List[Tuple[str, str, Optional[str]]] = []  # (raw, yahoo, stock_name_hint)
    if args.symbol:
        symbol_pairs = [(args.symbol, args.symbol, None)]
    else:
        if not os.path.exists(args.stock_file):
            print(f"❌ Stock file not found: {args.stock_file}", file=sys.stderr)
            sys.exit(1)
        df = load_stock_list(args.stock_file)
        if not {'Symbol', 'Segment'}.issubset(df.columns):
            print(f"❌ Stock.xlsx must have 'Symbol' and 'Segment' columns.", file=sys.stderr)
            sys.exit(1)
        if args.only_use_option_sentiment and "UseOptionSentiment" in df.columns:
            df = df[df["UseOptionSentiment"].astype(str).str.lower().isin(["true", "1", "yes"])]

        for _, row in df.iterrows():
            raw = str(row['Symbol']).strip()
            seg = str(row['Segment']).strip()
            stock_name_hint = str(row['Stock']).strip() if 'Stock' in df.columns and pd.notna(row.get('Stock')) else None
            if not raw:
                continue
            yahoo = to_yahoo_symbol(raw, seg)
            symbol_pairs.append((raw, yahoo, stock_name_hint))

    summaries = []
    all_alerts: List[VolumeAlert] = []

    for raw, ysym, stock_name_hint in symbol_pairs:
        try:
            print(f"\n=== Analyzing {raw} → {ysym} ===")
            result = analyze_symbol(
            ysym,
            args.lookback_days,
            args.volume_z,
            args.atr_window,
            args.sr_window,
            args.risk_reward,
            args.data_period,
            args.data_interval
        )

            result["summary"]["Symbol"] = raw  # <-- use raw symbol (no .NS/.BO) in CSV
            result["summary"]["DisplayName"] = _resolve_stock_display_name(raw_symbol=raw, yahoo_symbol=ysym, stock_name_hint=stock_name_hint)
            summaries.append(result["summary"])
            all_alerts.extend(result["alerts"])
            s = result["summary"]
            print(f"Trend: {s['Trend']} | Close: {s['Close']} | ATR: {s['ATR']}")

            # === IMAGE PATH SETUP ===
            if args.price_action_image:
                try:
                    # Generates the same four output variants used by NSEIndicesImageGenerator.py:
                    # Images/{DD_MM_YYYY}/General/{SYMBOL}.jpeg
                    # Images/{DD_MM_YYYY}/Instagram/{SYMBOL}.jpeg
                    # Images/{DD_MM_YYYY}/Standard/{SYMBOL}.jpeg
                    # Images/{DD_MM_YYYY}/Reels/{SYMBOL}.jpeg
                    generate_price_action_all_images(result["summary"])
                except Exception as _img_e:
                    print(f"  ⚠️ Failed to generate Price Action images for {raw}: {_img_e}", file=sys.stderr)

            
            # === EVENT-DRIVEN TRADE ENGINE (LONG example) ===
            pos = state.get(raw)  # raw = plain symbol (no .NS)
            close = float(s["Close"])
            atr_now = float(s["ATR"]) if s["ATR"] is not None else None
            today = pd.Timestamp("today", tz="Asia/Kolkata").strftime("%Y-%m-%d")

            def open_long():
                if atr_now is None:
                    return None
                entry = close
                atr_e = atr_now
                stop = (float(s["Support"]) - 1.0 * atr_e) if s["Support"] is not None else (entry - 1.5 * atr_e)
                t1 = entry + args.risk_reward * atr_e
                t2 = entry + (args.risk_reward + 1.0) * atr_e
                return Position(Symbol=raw, Side="LONG", Status="OPEN", Entry=entry, ATR_Entry=atr_e,
                                Stop=stop, T1=t1, T2=t2, Hit_T1=0, Hit_T2=0,
                                BarsSinceEntry=0, CreatedAt=today, LastUpdate=today)

            def trail_long(p: Position):
                if atr_now is None:
                    return p
                # chandelier stop that can only move up for longs
                p.Stop = max(p.Stop, close - 3.0 * atr_now)
                return p

            def update_hits_and_exit(p: Position):
                # mark partials
                if p.Hit_T1 == 0 and close >= p.T1:
                    p.Hit_T1 = 1
                    p.Stop = max(p.Stop, p.Entry)  # move to breakeven after T1
                if p.Hit_T2 == 0 and close >= p.T2:
                    p.Hit_T2 = 1
                # exit if stop hit
                if close <= p.Stop:
                    p.Status = "FLAT"
                return p

            def reanchor_needed(p: Position) -> bool:
                # 1) time-based: too many bars without T1
                if p.Hit_T1 == 0 and p.BarsSinceEntry >= args.reanchor_max_bars:
                    return True
                # 2) volatility regime shift: ATR changed a lot vs entry
                if atr_now is not None and p.ATR_Entry > 0:
                    if abs(atr_now - p.ATR_Entry) / p.ATR_Entry >= args.reanchor_atr_pct:
                        return True
                # 3) trend flip against us
                if args.exit_on_trend_flip and s["Trend"] == "Downtrend":
                    return True
                return False

            def reanchor_long(p: Position):
                # close & reopen with fresh targets ONLY on structural event
                # (you can also keep position and just rebuild T1/T2 if you prefer)
                newp = open_long()
                return newp

            if pos is None or pos.Status == "FLAT":
                # Entry condition: Uptrend & close inside BUY zone (use your existing zone)
                buy_lo, buy_hi = s["BuyZoneLow"], s["BuyZoneHigh"]
                if s["Trend"] == "Uptrend" and buy_lo is not None and buy_hi is not None and (buy_lo <= close <= buy_hi):
                    new_pos = open_long()
                    if new_pos:
                        state[raw] = new_pos
                        print(f"  ▶ OPEN LONG {raw}: entry={new_pos.Entry:.2f}, stop={new_pos.Stop:.2f}, T1={new_pos.T1:.2f}, T2={new_pos.T2:.2f}")
            else:
                if pos.Side == "LONG" and pos.Status == "OPEN":
                    pos.BarsSinceEntry += 1
                    pos = trail_long(pos)
                    pos = update_hits_and_exit(pos)
                    if pos.Status == "OPEN" and reanchor_needed(pos):
                        # re-anchor by closing and reopening (or just refresh targets)
                        newp = reanchor_long(pos)
                        if newp is not None:
                            state[raw] = newp
                            print(f"  ↻ RE-ANCHOR LONG {raw}: entry={newp.Entry:.2f}, stop={newp.Stop:.2f}, T1={newp.T1:.2f}, T2={newp.T2:.2f}")
                    else:
                        pos.LastUpdate = today
                        state[raw] = pos
                        print(f"  ▷ LONG {raw}: entry={pos.Entry:.2f}, stop={pos.Stop:.2f}, T1={pos.T1:.2f}({pos.Hit_T1}), T2={pos.T2:.2f}({pos.Hit_T2}), bars={pos.BarsSinceEntry}, status={pos.Status}")

            print(f"Support: {s['Support']} | Resistance: {s['Resistance']}")
            print(f"BUY Zone: {s['BuyZoneLow']} → {s['BuyZoneHigh']} | SELL Zone: {s['SellZoneLow']} → {s['SellZoneHigh']}")
            print(f"StopLoss: {s['StopLoss']} | Targets: T1={s['Target1']}, T2={s['Target2']}")
            sym_alerts = [a for a in all_alerts if a.symbol == ysym][-5:]
            if sym_alerts:
                print("  ⚠️ Unusual Volume Alerts (latest):")
                for a in sym_alerts:
                    d = pd.Timestamp(a.date).strftime("%Y-%m-%d")
                    print(f"   - {d}: z={a.zscore:.2f}, close={a.close:.2f}, volume={a.volume:,}, dir={a.direction} → {a.action}")
            else:
                print("  No recent unusual volume alerts for this symbol.")
        except Exception as e:
            print(f"❌ Error analyzing {ysym}: {e}", file=sys.stderr)

    if args.save_csv:
        if summaries:
            stamp = _ist_timestamp_for_filename()
            summary_path = os.path.join(args.outdir, f"PriceAction_Summary_{stamp}.csv")
            alerts_path  = os.path.join(args.outdir, f"PriceAction_Alerts_{stamp}.csv")

            pd.DataFrame(summaries).to_csv(summary_path, index=False)

            if all_alerts:
                pd.DataFrame([{
                    "Date": pd.to_datetime(a.date).strftime("%Y-%m-%d"),
                    "Symbol": a.symbol.split(".")[0],   # strip “.NS” / “.BO”
                    "Close": a.close,
                    "Volume": a.volume,
                    "ZScore": round(a.zscore, 2),
                    "Direction": a.direction,
                    "Action": a.action
                } for a in all_alerts]).to_csv(alerts_path, index=False)

            print("\n✅ CSV outputs saved:")
            print(" -", os.path.abspath(summary_path))
            save_state(args.state_csv, state)
            if all_alerts:
                print(" -", os.path.abspath(alerts_path))
            else:
                print(" - No alerts to save (no unusual volume spikes met the threshold).")
        else:
            print("\n⚠️ No summaries generated → nothing to save.")
            print("   Possible reasons: empty/invalid Stock.xlsx, bad ticker mapping, or all symbols failed to download.")
    else:
        print("\nℹ️ Skipped saving CSVs because --save_csv was not provided.")
   

if __name__ == "__main__":
    main()