import os
import pandas as pd
import numpy as np
from datetime import datetime


# ============================================================
# AIT SMART MOVE INDICATOR
# Author: Automation In Trade
# Purpose:
#   Custom indicator to detect stock mood, buy zone, stoploss,
#   target, confidence score, and reason using price action,
#   VWAP, RSI, ADX, volume surge, and support/resistance.
# ============================================================


# =========================
# CONFIGURATION
# =========================

# Stock list file path
# Expected columns: UnderlyingScrip, Symbol, Segment
STOCK_LIST = "../../../../../SelectedStock.csv"

# Candle data folder
# Expected file format inside this folder:
# {SYMBOL}_Live_15min.csv
# Example: POLYCAB_Live_15min.csv
#
# Expected candle columns:
# Timestamp,Open,High,Low,Close,Volume
INPUT_FOLDER = "CandleData"
OUTPUT_FOLDER = "Output"

# Auto-download toggle
# YES = try to download missing candle data automatically
# NO  = skip stock if candle data is missing
AUTO_DOWNLOAD_CANDLE_DATA = "YES"

# Download settings used only when AUTO_DOWNLOAD_CANDLE_DATA = YES
# Default downloader uses yfinance. For NSE symbols, .NS is automatically appended.
DOWNLOAD_INTERVAL = "15m"
DOWNLOAD_PERIOD = "5d"

# Timestamp handling
# Keeps candle CSV Timestamp like: 5/22/2026 9:15
MARKET_TIMEZONE = "Asia/Kolkata"

OUTPUT_FILE_NAME = "AIT_Smart_Move_Indicator_Output.xlsx"

# Stock name handling for Excel/CSV output
# If your SelectedStock.csv contains any of these columns, that value will be used.
# Otherwise STOCK_NAME_MAP will be used. If still unavailable, Symbol will be used.
STOCK_NAME_COLUMNS = [
    "Stock Name",
    "StockName",
    "Company Name",
    "Company",
    "Name",
    "Underlying Name",
    "Underlying",
]

STOCK_NAME_MAPPING_FILE = "StockNameMap.csv"  # Optional: columns Symbol, Stock Name

STOCK_NAME_MAP = {
    # NSE symbol -> complete stock/company name for Excel/CSV output.
    # Add more symbols here whenever needed.
    "POLYCAB": "Polycab India Ltd",
    "BLUESTARCO": "Blue Star Ltd",
    "HAVELLS": "Havells India Ltd",
    "DIXON": "Dixon Technologies (India) Ltd",
    "TRENT": "Trent Ltd",
    "SUZLON": "Suzlon Energy Ltd",
    "CIPLA": "Cipla Ltd",
    "SUNPHARMA": "Sun Pharmaceutical Industries Ltd",
    "APLAPOLLO": "APL Apollo Tubes Ltd",
    "NH": "Narayana Hrudayalaya Ltd",
    "MAXHEALTH": "Max Healthcare Institute Ltd",
    "KIMS": "Krishna Institute of Medical Sciences Ltd",
    "MEDANTA": "Global Health Ltd",
    "VIJAYA": "Vijaya Diagnostic Centre Ltd",
    "RECLTD": "REC Ltd",
    "PFC": "Power Finance Corporation Ltd",
    "POWERGRID": "Power Grid Corporation of India Ltd",
    "NHPC": "NHPC Ltd",
    "MUTHOOTFIN": "Muthoot Finance Ltd",
    "CUMMINSIND": "Cummins India Ltd",
    "PHOENIXLTD": "The Phoenix Mills Ltd",
    "GODREJPROP": "Godrej Properties Ltd",
    "OBEROIRLTY": "Oberoi Realty Ltd",
    "LODHA": "Macrotech Developers Ltd",
    "M&M": "Mahindra & Mahindra Ltd",
    "KPITTECH": "KPIT Technologies Ltd",
    "MARUTI": "Maruti Suzuki India Ltd",
    "HAL": "Hindustan Aeronautics Ltd",
    "BSE": "BSE Ltd",
    "M&MFIN": "M&M Financial Services Ltd",
    "ICICIBANK": "ICICI Bank Ltd",
    "RELIANCE": "Reliance Industries Ltd",
    "ITC": "ITC Ltd",
    "HDFCBANK": "HDFC Bank Ltd",
    "AXISBANK": "Axis Bank Ltd",
    "NTPC": "NTPC Ltd",
    "BHARTIARTL": "Bharti Airtel Ltd",
    "TATAMOTORS": "Tata Motors Ltd",
    "TVSMOTOR": "TVS Motor Company Ltd",
    "HEROMOTOCO": "Hero MotoCorp Ltd",
    "BAJAJ-AUTO": "Bajaj Auto Ltd",
    "APOLLOHOSP": "Apollo Hospitals Enterprise Ltd",
    "JUSTDIAL": "Just Dial Ltd",
    "DABUR": "Dabur India Ltd",
    "VBL": "Varun Beverages Ltd",
}

RSI_PERIOD = 14
ADX_PERIOD = 14
VOLUME_LOOKBACK = 20
SUPPORT_RESISTANCE_LOOKBACK = 20

NEAR_SUPPORT_PERCENT = 1.0
NEAR_RESISTANCE_PERCENT = 1.0

MIN_VOLUME_SURGE = 1.5

RISK_REWARD_TARGET_1 = 1.5
RISK_REWARD_TARGET_2 = 2.5


# =========================
# UTILITY FUNCTIONS
# =========================

def ensure_output_folder():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)


def normalize_datetime_series(datetime_series):
    """
    Converts timestamps safely for Indian market usage.

    - If timestamp has timezone like +00:00, it is converted to Asia/Kolkata.
    - If timestamp is already plain like 5/22/2026 9:15, it is kept as-is.
    - Final output is timezone-unaware datetime, so Excel does not throw timezone errors.
    """

    raw_series = datetime_series.astype(str).str.strip()

    timezone_pattern = r"(Z$|[+-]\d{2}:?\d{2}$)"
    has_timezone = raw_series.str.contains(timezone_pattern, regex=True, na=False).any()

    if has_timezone:
        parsed = pd.to_datetime(datetime_series, errors="coerce", utc=True)
        parsed = parsed.dt.tz_convert(MARKET_TIMEZONE).dt.tz_localize(None)
    else:
        parsed = pd.to_datetime(datetime_series, errors="coerce")

        # Extra safety: if pandas still returns tz-aware values, remove timezone.
        try:
            if getattr(parsed.dt, "tz", None) is not None:
                parsed = parsed.dt.tz_convert(MARKET_TIMEZONE).dt.tz_localize(None)
        except Exception:
            pass

    return parsed


def format_datetime_value(dt_value):
    """Returns timestamp exactly like: 5/22/2026 9:15"""

    if pd.isna(dt_value):
        return ""

    dt_value = pd.Timestamp(dt_value)

    if dt_value.tzinfo is not None:
        dt_value = dt_value.tz_convert(MARKET_TIMEZONE).tz_localize(None)

    return f"{dt_value.month}/{dt_value.day}/{dt_value.year} {dt_value.hour}:{dt_value.minute:02d}"


def format_datetime_series(datetime_series):
    parsed = normalize_datetime_series(datetime_series)
    return parsed.apply(format_datetime_value)


def rewrite_candle_file_with_clean_timestamp(file_path, df):
    """
    Rewrites candle CSV with clean Timestamp format:
        5/22/2026 9:15

    This removes timezone strings like +00:00 from downloaded candle files.
    """

    try:
        save_df = df.copy()
        save_df["Timestamp"] = save_df["Datetime"].apply(format_datetime_value)

        save_cols = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
        save_df = save_df[save_cols]
        save_df.to_csv(file_path, index=False)
    except Exception as e:
        print(f"Warning: Could not rewrite candle file timestamp format for {file_path}: {e}")


def clean_ohlcv_data(df, symbol=None):
    """
    Supports both formats:

    1) Older format:
       Symbol,Datetime,Open,High,Low,Close,Volume

    2) Live candle format:
       Timestamp,Open,High,Low,Close,Volume
       In this case Symbol is added from the file name / stock list.
    """

    df = df.copy()

    # Normalize column names safely
    df.columns = [str(col).strip() for col in df.columns]

    if "Datetime" not in df.columns and "Timestamp" in df.columns:
        df["Datetime"] = df["Timestamp"]

    if "Symbol" not in df.columns:
        if symbol is None:
            raise ValueError("Symbol column missing and no symbol was provided.")
        df["Symbol"] = symbol

    required_columns = ["Symbol", "Datetime", "Open", "High", "Low", "Close", "Volume"]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in input file: {missing_columns}")

    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df["Datetime"] = normalize_datetime_series(df["Datetime"])

    numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Symbol", "Datetime", "Open", "High", "Low", "Close", "Volume"])
    df = df.sort_values(["Symbol", "Datetime"]).reset_index(drop=True)

    return df


def load_stock_list(stock_list_path=STOCK_LIST):
    """
    Loads SelectedStock.csv.

    Expected columns:
        UnderlyingScrip, Symbol, Segment

    Supports comma, tab, pipe, and semicolon separated files.
    """

    if not os.path.exists(stock_list_path):
        raise FileNotFoundError(f"Stock list not found: {stock_list_path}")

    stock_df = pd.read_csv(stock_list_path, sep=None, engine="python")
    stock_df.columns = [str(col).strip() for col in stock_df.columns]

    required_columns = ["UnderlyingScrip", "Symbol", "Segment"]
    missing_columns = [col for col in required_columns if col not in stock_df.columns]

    if missing_columns:
        raise ValueError(f"Missing columns in stock list: {missing_columns}")

    stock_df = stock_df.dropna(subset=["Symbol"])
    stock_df["Symbol"] = stock_df["Symbol"].astype(str).str.strip().str.upper()
    stock_df["Segment"] = stock_df["Segment"].astype(str).str.strip().str.upper()

    stock_df = stock_df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)

    return stock_df


def load_external_stock_name_map():
    """
    Optional external mapping file support.

    Create StockNameMap.csv in the same folder as this script with columns:
        Symbol,Stock Name

    Example:
        HAVELLS,Havells India Ltd
        DIXON,Dixon Technologies (India) Ltd

    This lets you add names without editing the Python script.
    """

    if not os.path.exists(STOCK_NAME_MAPPING_FILE):
        return {}

    try:
        name_df = pd.read_csv(STOCK_NAME_MAPPING_FILE, sep=None, engine="python")
        name_df.columns = [str(col).strip() for col in name_df.columns]

        symbol_col = None
        name_col = None

        for col in name_df.columns:
            if col.strip().lower() == "symbol":
                symbol_col = col
            if col.strip().lower() in ["stock name", "stockname", "company name", "company", "name"]:
                name_col = col

        if symbol_col is None or name_col is None:
            print(f"Warning: {STOCK_NAME_MAPPING_FILE} must contain Symbol and Stock Name columns.")
            return {}

        mapping = {}
        for _, map_row in name_df.iterrows():
            symbol = str(map_row.get(symbol_col, "")).strip().upper()
            stock_name = str(map_row.get(name_col, "")).strip()
            if symbol and stock_name and stock_name.lower() != "nan":
                mapping[symbol] = stock_name

        return mapping

    except Exception as e:
        print(f"Warning: Could not read {STOCK_NAME_MAPPING_FILE}: {e}")
        return {}


def apply_stock_name_mapping(stock_df):
    """
    Ensures Stock Name is available for every symbol before processing.
    Priority:
        1. Existing name column in SelectedStock.csv
        2. StockNameMap.csv
        3. STOCK_NAME_MAP
        4. Symbol fallback
    """

    stock_df = stock_df.copy()
    external_map = load_external_stock_name_map()

    stock_names = []
    for _, row in stock_df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()

        existing_name = None
        for col in STOCK_NAME_COLUMNS:
            if col in row.index:
                value = row.get(col, None)
                if pd.notna(value) and str(value).strip():
                    existing_name = str(value).strip()
                    break

        if existing_name:
            stock_names.append(existing_name)
        elif symbol in external_map:
            stock_names.append(external_map[symbol])
        elif symbol in STOCK_NAME_MAP:
            stock_names.append(STOCK_NAME_MAP[symbol])
        else:
            stock_names.append(symbol)

    stock_df["Stock Name"] = stock_names
    return stock_df


def get_stock_name_from_stock_row(row):
    """
    Returns clean stock/company name for Excel/CSV output.

    Priority:
    1. Stock-name column from SelectedStock.csv if available
    2. STOCK_NAME_MAP
    3. Symbol fallback
    """

    symbol = str(row.get("Symbol", "")).strip().upper()

    for col in STOCK_NAME_COLUMNS:
        if col in row.index:
            value = row.get(col, None)
            if pd.notna(value) and str(value).strip():
                return str(value).strip()

    if symbol in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[symbol]

    return symbol


def get_candle_file_path(symbol):
    """
    Primary file format:
        CandleData/{SYMBOL}_Live_15min.csv

    Also supports fallback files like:
        {SYMBOL}_Live_1min.csv
        {SYMBOL}_Live_5min.csv
        {SYMBOL}_Live_15m.csv
    """

    primary_path = os.path.join(INPUT_FOLDER, f"{symbol}_Live_15min.csv")

    if os.path.exists(primary_path):
        return primary_path

    if not os.path.exists(INPUT_FOLDER):
        return primary_path

    possible_files = [
        file for file in os.listdir(INPUT_FOLDER)
        if file.upper().startswith(f"{symbol}_LIVE_") and file.lower().endswith(".csv")
    ]

    if possible_files:
        possible_files = sorted(possible_files)
        return os.path.join(INPUT_FOLDER, possible_files[0])

    return primary_path


def download_candle_data(symbol, segment=None):
    """
    Downloads missing candle data when AUTO_DOWNLOAD_CANDLE_DATA = YES.

    Current implementation uses yfinance as a default fallback downloader.
    For NSE_EQ symbols, .NS is automatically appended.

    If you want to use Dhan API instead, replace only this function and keep
    the rest of the script unchanged.
    """

    if str(AUTO_DOWNLOAD_CANDLE_DATA).strip().upper() != "YES":
        print(f"Skipping {symbol}: candle data missing and AUTO_DOWNLOAD_CANDLE_DATA is not YES")
        return None

    try:
        import yfinance as yf
    except ImportError:
        print(f"Cannot auto-download {symbol}: yfinance is not installed.")
        print("Install it using: pip install yfinance")
        return None

    os.makedirs(INPUT_FOLDER, exist_ok=True)

    yf_symbol = symbol
    if segment is None or str(segment).upper() in ["NSE_EQ", "NSE", "NSE_FNO"]:
        if not yf_symbol.endswith(".NS"):
            yf_symbol = f"{symbol}.NS"

    print(f"Auto-downloading candle data for {symbol} using yfinance symbol: {yf_symbol}")

    try:
        data = yf.download(
            yf_symbol,
            period=DOWNLOAD_PERIOD,
            interval=DOWNLOAD_INTERVAL,
            progress=False,
            auto_adjust=False,
            threads=False
        )
    except Exception as e:
        print(f"Download failed for {symbol}: {e}")
        return None

    if data is None or data.empty:
        print(f"No downloaded candle data found for {symbol}")
        return None

    data = data.reset_index()

    # yfinance may return Datetime or Date depending on interval.
    if "Datetime" in data.columns:
        data = data.rename(columns={"Datetime": "Timestamp"})
    elif "Date" in data.columns:
        data = data.rename(columns={"Date": "Timestamp"})

    # Flatten multi-index columns if yfinance returns them.
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    required_download_cols = ["Timestamp", "Open", "High", "Low", "Close", "Volume"]
    missing_download_cols = [col for col in required_download_cols if col not in data.columns]

    if missing_download_cols:
        print(f"Downloaded data for {symbol} is missing columns: {missing_download_cols}")
        return None

    data = data[required_download_cols].copy()
    data = data.dropna(subset=["Open", "High", "Low", "Close"])

    # Save Timestamp without timezone, exactly like: 5/22/2026 9:15
    data["Timestamp"] = format_datetime_series(data["Timestamp"])

    output_path = os.path.join(INPUT_FOLDER, f"{symbol}_Live_15min.csv")
    data.to_csv(output_path, index=False)

    print(f"Downloaded candle data saved: {output_path}")
    return output_path


def load_candle_data_for_symbol(symbol, segment=None):
    """
    Loads latest candle data for a symbol from CandleData.
    If missing, tries auto-download when AUTO_DOWNLOAD_CANDLE_DATA = YES.
    """

    candle_file_path = get_candle_file_path(symbol)

    if not os.path.exists(candle_file_path):
        candle_file_path = download_candle_data(symbol, segment)

    if candle_file_path is None or not os.path.exists(candle_file_path):
        return None

    df = pd.read_csv(candle_file_path)
    df = clean_ohlcv_data(df, symbol=symbol)

    # Keep the source candle file Timestamp clean for future use.
    rewrite_candle_file_with_clean_timestamp(candle_file_path, df)

    return df


# =========================
# TECHNICAL INDICATORS
# =========================

def calculate_rsi(df, period=14):
    df = df.copy()

    delta = df["Close"].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    df["RSI"] = rsi.fillna(50)

    return df


def calculate_vwap(df):
    df = df.copy()

    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cumulative_tpv = (typical_price * df["Volume"]).cumsum()
    cumulative_volume = df["Volume"].cumsum()

    df["VWAP"] = cumulative_tpv / cumulative_volume.replace(0, np.nan)
    df["VWAP"] = df["VWAP"].fillna(df["Close"])

    df["VWAP_Deviation_%"] = ((df["Close"] - df["VWAP"]) / df["VWAP"]) * 100

    return df


def calculate_adx(df, period=14):
    df = df.copy()

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    plus_dm = high.diff()
    minus_dm = low.diff() * -1

    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.rolling(window=period, min_periods=period).mean()

    plus_di = 100 * (
        pd.Series(plus_dm, index=df.index).rolling(window=period, min_periods=period).mean()
        / atr.replace(0, np.nan)
    )

    minus_di = 100 * (
        pd.Series(minus_dm, index=df.index).rolling(window=period, min_periods=period).mean()
        / atr.replace(0, np.nan)
    )

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)

    adx = dx.rolling(window=period, min_periods=period).mean()

    df["ADX"] = adx.fillna(20)
    df["Plus_DI"] = plus_di.fillna(0)
    df["Minus_DI"] = minus_di.fillna(0)

    return df


def calculate_volume_surge(df, lookback=20):
    df = df.copy()

    df["Avg_Volume"] = df["Volume"].rolling(window=lookback, min_periods=1).mean()
    df["Volume_Surge"] = df["Volume"] / df["Avg_Volume"].replace(0, np.nan)
    df["Volume_Surge"] = df["Volume_Surge"].fillna(1)

    return df


def calculate_support_resistance(df, lookback=20):
    df = df.copy()

    df["Support"] = df["Low"].rolling(window=lookback, min_periods=1).min()
    df["Resistance"] = df["High"].rolling(window=lookback, min_periods=1).max()

    return df


# =========================
# OPTION SENTIMENT PLACEHOLDER
# =========================

def get_option_sentiment(symbol):
    """
    Placeholder function.

    Later you can connect this with your OptionAnalysisResults.xlsx.

    Return values:
        Bullish
        Bearish
        Neutral
    """

    # For now, default is Neutral.
    # You can replace this logic with your option chain sentiment file.
    return "Neutral"


# =========================
# AIT SMART MOVE INDICATOR LOGIC
# =========================

def calculate_smart_move_for_latest_candle(symbol_df):
    symbol_df = symbol_df.copy()

    latest = symbol_df.iloc[-1]

    symbol = latest["Symbol"]
    latest_time = latest["Datetime"]

    close = latest["Close"]
    high = latest["High"]
    low = latest["Low"]

    rsi = latest["RSI"]
    adx = latest["ADX"]
    plus_di = latest["Plus_DI"]
    minus_di = latest["Minus_DI"]

    vwap = latest["VWAP"]
    vwap_dev = latest["VWAP_Deviation_%"]

    volume_surge = latest["Volume_Surge"]

    support = latest["Support"]
    resistance = latest["Resistance"]

    option_sentiment = get_option_sentiment(symbol)

    score = 0
    reasons = []

    # =========================
    # PRICE ABOVE VWAP
    # =========================

    if close > vwap:
        score += 20
        reasons.append("Price above VWAP")
    elif close < vwap:
        score -= 10
        reasons.append("Price below VWAP")

    # =========================
    # RSI STRENGTH
    # =========================

    if rsi >= 60:
        score += 15
        reasons.append("RSI strong")
    elif 50 <= rsi < 60:
        score += 8
        reasons.append("RSI mildly positive")
    elif 40 <= rsi < 50:
        score += 0
        reasons.append("RSI neutral weak")
    else:
        score -= 10
        reasons.append("RSI weak")

    # =========================
    # ADX TREND STRENGTH
    # =========================

    if adx >= 25 and plus_di > minus_di:
        score += 15
        reasons.append("ADX confirms bullish trend")
    elif adx >= 25 and minus_di > plus_di:
        score -= 15
        reasons.append("ADX confirms bearish trend")
    elif 18 <= adx < 25:
        score += 5
        reasons.append("ADX shows developing trend")
    else:
        reasons.append("ADX weak / range-bound")

    # =========================
    # VOLUME CONFIRMATION
    # =========================

    if volume_surge >= 2:
        score += 20
        reasons.append("Strong volume surge")
    elif volume_surge >= MIN_VOLUME_SURGE:
        score += 12
        reasons.append("Moderate volume surge")
    else:
        reasons.append("No major volume surge")

    # =========================
    # PRICE NEAR SUPPORT
    # =========================

    distance_from_support = ((close - support) / support) * 100 if support > 0 else np.nan
    distance_from_resistance = ((resistance - close) / close) * 100 if close > 0 else np.nan

    near_support = distance_from_support <= NEAR_SUPPORT_PERCENT
    near_resistance = distance_from_resistance <= NEAR_RESISTANCE_PERCENT

    if near_support:
        score += 15
        reasons.append("Price near support zone")

    if near_resistance:
        score -= 8
        reasons.append("Price near resistance zone")

    # =========================
    # BREAKOUT / BREAKDOWN LOGIC
    # =========================

    previous_resistance = symbol_df["Resistance"].iloc[-2] if len(symbol_df) > 1 else resistance
    previous_support = symbol_df["Support"].iloc[-2] if len(symbol_df) > 1 else support

    breakout = close > previous_resistance
    breakdown = close < previous_support

    if breakout and volume_surge >= MIN_VOLUME_SURGE:
        score += 15
        reasons.append("Breakout with volume confirmation")
    elif breakout:
        score += 8
        reasons.append("Breakout without strong volume")

    if breakdown and volume_surge >= MIN_VOLUME_SURGE:
        score -= 20
        reasons.append("Breakdown with volume pressure")
    elif breakdown:
        score -= 10
        reasons.append("Weak breakdown signal")

    # =========================
    # OPTION SENTIMENT
    # =========================

    if option_sentiment == "Bullish":
        score += 15
        reasons.append("Option sentiment bullish")
    elif option_sentiment == "Bearish":
        score -= 15
        reasons.append("Option sentiment bearish")
    else:
        reasons.append("Option sentiment neutral")

    # =========================
    # SCORE NORMALIZATION
    # =========================

    score = max(0, min(score, 100))

    # =========================
    # SIGNAL CLASSIFICATION
    # =========================

    if score >= 80:
        signal = "Strong Bullish"
        mood = "Bullish Breakout / Strong Buy Zone"
    elif score >= 65:
        signal = "Bullish"
        mood = "Buy on Dip / Positive Setup"
    elif score >= 50:
        signal = "Neutral Positive"
        mood = "Watch for Entry"
    elif score >= 35:
        signal = "Neutral Weak"
        mood = "Range Bound / Wait"
    else:
        signal = "Weak / Avoid"
        mood = "Bearish / Trap Zone"

    # =========================
    # BUY ZONE, STOPLOSS, TARGET
    # =========================

    if signal in ["Strong Bullish", "Bullish", "Neutral Positive"]:
        buy_zone_low = round(max(support, close * 0.995), 2)
        buy_zone_high = round(close, 2)

        stoploss = round(support * 0.995, 2)

        risk = buy_zone_high - stoploss

        if risk <= 0:
            risk = close * 0.01

        target_1 = round(buy_zone_high + (risk * RISK_REWARD_TARGET_1), 2)
        target_2 = round(buy_zone_high + (risk * RISK_REWARD_TARGET_2), 2)

    else:
        buy_zone_low = None
        buy_zone_high = None
        stoploss = None
        target_1 = None
        target_2 = None

    result = {
        "Datetime": latest_time,
        "Symbol": symbol,
        "Close": round(close, 2),
        "VWAP": round(vwap, 2),
        "VWAP Deviation %": round(vwap_dev, 2),
        "RSI": round(rsi, 2),
        "ADX": round(adx, 2),
        "Plus DI": round(plus_di, 2),
        "Minus DI": round(minus_di, 2),
        "Volume Surge": round(volume_surge, 2),
        "Support": round(support, 2),
        "Resistance": round(resistance, 2),
        "Near Support": "Yes" if near_support else "No",
        "Near Resistance": "Yes" if near_resistance else "No",
        "Option Sentiment": option_sentiment,
        "AIT Score": score,
        "Signal": signal,
        "Stock Mood": mood,
        "Buy Zone Low": buy_zone_low,
        "Buy Zone High": buy_zone_high,
        "Stoploss": stoploss,
        "Target 1": target_1,
        "Target 2": target_2,
        "Reason": " | ".join(reasons)
    }

    return result


# =========================
# MAIN PROCESSING FUNCTION
# =========================

def process_symbol_candle_data(symbol, symbol_df):
    symbol_df = symbol_df.copy()
    symbol_df = symbol_df.sort_values("Datetime").reset_index(drop=True)

    if len(symbol_df) < 20:
        print(f"Skipping {symbol}: Not enough candle data. Minimum 20 rows required.")
        return None

    symbol_df = calculate_rsi(symbol_df, RSI_PERIOD)
    symbol_df = calculate_vwap(symbol_df)
    symbol_df = calculate_adx(symbol_df, ADX_PERIOD)
    symbol_df = calculate_volume_surge(symbol_df, VOLUME_LOOKBACK)
    symbol_df = calculate_support_resistance(symbol_df, SUPPORT_RESISTANCE_LOOKBACK)

    return calculate_smart_move_for_latest_candle(symbol_df)


def process_all_stocks_from_stock_list():
    ensure_output_folder()

    os.makedirs(INPUT_FOLDER, exist_ok=True)

    stock_df = load_stock_list(STOCK_LIST)
    stock_df = apply_stock_name_mapping(stock_df)

    all_results = []
    skipped_symbols = []

    print(f"Loaded {len(stock_df)} symbols from: {STOCK_LIST}")
    print(f"Reading candle data from: {INPUT_FOLDER}")

    for _, row in stock_df.iterrows():
        symbol = str(row["Symbol"]).strip().upper()
        segment = str(row.get("Segment", "")).strip().upper()

        try:
            symbol_df = load_candle_data_for_symbol(symbol, segment)

            if symbol_df is None or symbol_df.empty:
                print(f"Skipping {symbol}: Candle data not available.")
                skipped_symbols.append({
                    "Symbol": symbol,
                    "Reason": "Candle data not available"
                })
                continue

            result = process_symbol_candle_data(symbol, symbol_df)

            if result is None:
                skipped_symbols.append({
                    "Symbol": symbol,
                    "Reason": "Not enough candle data"
                })
                continue

            result["UnderlyingScrip"] = row.get("UnderlyingScrip", None)
            result["Stock Name"] = get_stock_name_from_stock_row(row)
            result["Segment"] = segment
            all_results.append(result)

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            skipped_symbols.append({
                "Symbol": symbol,
                "Reason": str(e)
            })

    if not all_results:
        print("No results generated.")
        if skipped_symbols:
            skipped_df = pd.DataFrame(skipped_symbols)
            skipped_path = os.path.join(OUTPUT_FOLDER, "AIT_Smart_Move_Skipped_Symbols.csv")
            skipped_df.to_csv(skipped_path, index=False)
            print(f"Skipped symbols saved at: {skipped_path}")
        return

    output_df = pd.DataFrame(all_results)

    # Excel does not support timezone-aware datetimes. Also keep readable format.
    if "Datetime" in output_df.columns:
        output_df["Datetime"] = format_datetime_series(output_df["Datetime"])

    # Put stock-list metadata columns first if available.
    first_cols = ["UnderlyingScrip", "Symbol", "Stock Name", "Segment", "Datetime"]
    remaining_cols = [col for col in output_df.columns if col not in first_cols]
    output_df = output_df[first_cols + remaining_cols]

    output_path = os.path.join(OUTPUT_FOLDER, OUTPUT_FILE_NAME)
    csv_output_path = os.path.join(
        OUTPUT_FOLDER,
        OUTPUT_FILE_NAME.replace(".xlsx", ".csv")
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        output_df.to_excel(writer, sheet_name="AIT Smart Move", index=False)

        if skipped_symbols:
            skipped_df = pd.DataFrame(skipped_symbols)
            skipped_df.to_excel(writer, sheet_name="Skipped Symbols", index=False)

    output_df.to_csv(csv_output_path, index=False)

    if skipped_symbols:
        skipped_path = os.path.join(OUTPUT_FOLDER, "AIT_Smart_Move_Skipped_Symbols.csv")
        pd.DataFrame(skipped_symbols).to_csv(skipped_path, index=False)
        print(f"Skipped symbols saved at: {skipped_path}")

    print("\nAIT Smart Move Indicator completed successfully.")
    print(f"Excel saved at: {output_path}")
    print(f"CSV saved at: {csv_output_path}")


# =========================
# SAMPLE DATA GENERATOR
# =========================

def generate_sample_data():
    """
    This function creates sample OHLCV data.
    Use it only for testing the script.
    """

    sample_folder = INPUT_FOLDER

    if not os.path.exists(sample_folder):
        os.makedirs(sample_folder)

    symbols = ["ICICIBANK", "RELIANCE", "SUNPHARMA"]

    rows = []

    start_date = pd.Timestamp("2026-05-01 09:15:00")

    for symbol in symbols:
        price = np.random.randint(800, 2500)

        for i in range(60):
            dt = start_date + pd.Timedelta(minutes=15 * i)

            open_price = price + np.random.uniform(-10, 10)
            high_price = open_price + np.random.uniform(5, 20)
            low_price = open_price - np.random.uniform(5, 20)
            close_price = np.random.uniform(low_price, high_price)
            volume = np.random.randint(50000, 500000)

            rows.append({
                "Symbol": symbol,
                "Datetime": dt,
                "Open": round(open_price, 2),
                "High": round(high_price, 2),
                "Low": round(low_price, 2),
                "Close": round(close_price, 2),
                "Volume": volume
            })

            price = close_price

    sample_df = pd.DataFrame(rows)

    sample_file_path = os.path.join(sample_folder, "sample_ohlcv_data.csv")
    sample_df.to_csv(sample_file_path, index=False)

    print(f"Sample data created at: {sample_file_path}")


# =========================
# SCRIPT ENTRY POINT
# =========================

if __name__ == "__main__":

    # Keep this False for your real workflow.
    # Your real workflow reads symbols from STOCK_LIST and candles from CandleData/.
    CREATE_SAMPLE_DATA = False

    if CREATE_SAMPLE_DATA:
        generate_sample_data()

    process_all_stocks_from_stock_list()