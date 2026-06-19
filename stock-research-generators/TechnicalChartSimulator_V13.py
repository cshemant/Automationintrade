import os
import math
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime

try:
    import yfinance as yf
except Exception:
    yf = None
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================================================
# CONFIG / BUTTONS
# =========================================================
# INPUT_STOCKS can point to:
# 1) a single CSV / Excel file, OR
# 2) a folder containing multiple CSV / Excel files.
# If a folder is provided, the script will generate images for all supported files inside that folder.
INPUT_STOCKS = r"../../../../../../../SelectedStock.csv"
#INPUT_STOCKS = r"../../../AllIndexList/Test"

DATE = ""  # dd/mm/yyyy | keep blank for today
BRAND_HANDLE = "automationintrade"
TITLE_PREFIX = ""

# Set automatically while processing each input stock file.
CURRENT_INPUT_FILE_PATH = ""
CURRENT_INPUT_BATCH_NAME = ""

# Output folders
# Master chart goes to MASTER folder; reel-step sub-images go to SubImages folder.
OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/{IMAGE_TYPE}/{SYMBOL}.jpeg"  # backward-compatible
MASTER_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/Master/{IMAGE_TYPE}/{SYMBOL}.jpeg"
SUBIMAGE_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/SubImages/{IMAGE_TYPE}/{SYMBOL}/{SYMBOL}{SUFFIX}.jpeg"

GENERATE_GENERAL_IMAGE = True
GENERATE_INSTAGRAM_IMAGE = True
GENERATE_STANDARD_IMAGE = True
GENERATE_REELS_IMAGE = True
GENERATE_SUMMARY_CARD = True

# =========================================================
# REELS REVEAL-SEQUENCE BUTTONS FOR {SYMBOL}.jpeg
# =========================================================
# Generates 3 chart versions for each symbol:
# 1) Blank values    -> no numeric buy/target/SL values are shown
# 2) Headings only   -> only BUY ZONE / SELL TARGET / STOP LOSS headings are shown
# 3) Full chart      -> current full chart with all values
GENERATE_CHART_REVEAL_SEQUENCE = True
CHART_REVEAL_MODES = ["BLANK_VALUES", "HEADINGS_ONLY", "FULL"]
CHART_REVEAL_SUFFIX = {
    "BLANK_VALUES": "_01_BlankValues",
    "HEADINGS_ONLY": "_02_HeadingsOnly",
    "FULL": "",
}

# =========================================================
# ACTION-LINE STEP IMAGE BUTTONS
# =========================================================
# These 3 extra sub-images are useful for reels:
# 1) Buy line + buy value only
# 2) Buy line + target line with values
# 3) Buy line + target line + stop-loss line with values
GENERATE_ACTION_LINE_STEP_IMAGES = True
ACTION_LINE_STEP_MODES = ["BUY_LINE_ONLY", "BUY_TARGET_LINES", "BUY_TARGET_SL_LINES"]
ACTION_LINE_STEP_SUFFIX = {
    "BUY_LINE_ONLY": "_03_BuyLineOnly",
    "BUY_TARGET_LINES": "_04_BuyTargetLines",
    "BUY_TARGET_SL_LINES": "_05_BuyTargetSL",
}

# Controls what appears in the two non-final reveal charts
SHOW_ACTION_LINES_IN_BLANK_VALUES_IMAGE = True
SHOW_ACTION_LINES_IN_HEADINGS_ONLY_IMAGE = False
SHOW_ACTION_TAGS_IN_BLANK_VALUES_IMAGE = True
SHOW_ACTION_TAGS_IN_HEADINGS_ONLY_IMAGE = False

SUMMARY_OUTPUT_TEMPLATE = r"Images/{DATE_FOLDER}/{IMAGE_TYPE}/{SYMBOL}_Summary.jpeg"

# =========================================================
# SUMMARY CARD BUTTONS - COMMON
# =========================================================
# Font controls for the circled summary-card elements
SUMMARY_TITLE_FONT_SIZE = 54
SUMMARY_SUBTITLE_FONT_SIZE = 28
SUMMARY_ROW_LABEL_FONT_SIZE = 22
SUMMARY_ROW_VALUE_FONT_SIZE = 40
SUMMARY_SETUP_VALUE_FONT_SIZE = 36
SUMMARY_DISCLAIMER_FONT_SIZE = 16
SUMMARY_FOOTER_FONT_SIZE = 30

# Y-axis shift controls for title/footer/disclaimer
SUMMARY_TITLE_Y_SHIFT = 0
SUMMARY_SUBTITLE_Y_SHIFT = 0
SUMMARY_CARD_Y_SHIFT = 0
SUMMARY_DISCLAIMER_Y_SHIFT = 0
SUMMARY_FOOTER_Y_SHIFT = 0

# Layout controls
SUMMARY_TITLE_MAX_WIDTH_PCT = 0.82
SUMMARY_SUBTITLE_MAX_WIDTH_PCT = 0.78
SUMMARY_CARD_WIDTH_PCT = 0.86
SUMMARY_CARD_TOP_PCT = 0.19
SUMMARY_CARD_BOTTOM_PCT = 0.13
SUMMARY_CARD_INNER_X_PCT = 0.045
SUMMARY_CARD_INNER_Y_PCT = 0.045
SUMMARY_ROW_GAP = 18
SUMMARY_ROW_LABEL_X_PAD = 26
SUMMARY_ROW_VALUE_X_PAD = 26
SUMMARY_ROW_LABEL_Y_PAD = 18
SUMMARY_ROW_VALUE_Y_PAD = 56
SUMMARY_ROW_RADIUS = 22
SUMMARY_VALUE_MAX_WIDTH_PCT = 0.90

# Per-format font boosts / layout shifts
GENERAL_SUMMARY_FONT_SIZE_BOOST = 0
GENERAL_SUMMARY_TITLE_Y_SHIFT = 0
GENERAL_SUMMARY_CARD_Y_SHIFT = 0
GENERAL_SUMMARY_FOOTER_Y_SHIFT = 0

INSTAGRAM_SUMMARY_FONT_SIZE_BOOST = 10
INSTAGRAM_SUMMARY_TITLE_Y_SHIFT = 50
INSTAGRAM_SUMMARY_CARD_Y_SHIFT = 0
INSTAGRAM_SUMMARY_FOOTER_Y_SHIFT = 30

STANDARD_SUMMARY_FONT_SIZE_BOOST = 0
STANDARD_SUMMARY_TITLE_Y_SHIFT = 0
STANDARD_SUMMARY_CARD_Y_SHIFT = 0
STANDARD_SUMMARY_FOOTER_Y_SHIFT = 0

REELS_SUMMARY_FONT_SIZE_BOOST = 0
REELS_SUMMARY_TITLE_Y_SHIFT = 0
REELS_SUMMARY_CARD_Y_SHIFT = 0
REELS_SUMMARY_FOOTER_Y_SHIFT = 0

# Data / timeframe buttons
# REAL_THEN_SIMULATED = first try Yahoo Finance 1Y data; fallback to realistic simulated data.
# SIMULATED_ONLY = no internet/data dependency, but levels are anchored to current price if supplied.
DATA_MODE = "REAL_THEN_SIMULATED"
CHART_TIMEFRAME = "1Y"          # label only: 3M / 6M / 1Y
TRADE_STYLE = "SWING"           # INTRADAY / SWING / POSITIONAL
HISTORY_PERIOD = "1y"
HISTORY_INTERVAL = "1d"

# =========================================================
# VALIDITY / EXPIRY BUTTONS
# =========================================================
SHOW_VALIDITY_DATE = True
VALIDITY_TEXT_PREFIX = "Valid Till"
VALIDITY_DATE_OVERRIDE = ""      # dd/mm/yyyy. If provided, this exact date is shown.
VALIDITY_DATE_FORMAT = "%d %b %Y"
VALIDITY_MODE = "AUTO_BY_TRADE_STYLE"   # AUTO_BY_TRADE_STYLE / FIXED_TRADING_DAYS
FIXED_VALIDITY_TRADING_DAYS = 5
INTRADAY_VALIDITY_TRADING_DAYS = 1
SWING_VALIDITY_TRADING_DAYS = 5
POSITIONAL_VALIDITY_TRADING_DAYS = 20

GENERAL_VALIDITY_FONT_SIZE = 22
GENERAL_VALIDITY_Y_SHIFT = 0
INSTAGRAM_VALIDITY_FONT_SIZE = 23
INSTAGRAM_VALIDITY_Y_SHIFT = 0
STANDARD_VALIDITY_FONT_SIZE = 20
STANDARD_VALIDITY_Y_SHIFT = 0
REELS_VALIDITY_FONT_SIZE = 24
REELS_VALIDITY_Y_SHIFT = 0

SIMULATION_CANDLES = 120
START_PRICE = 1000
VOLATILITY = 0.018
TREND_STRENGTH = 0.0015

# Optional manual CMP fallback. Use only when yfinance/live data is unavailable.
# Example: MANUAL_CURRENT_PRICE = {"M&M": 3173.90, "BLUESTARCO": 1667.20}
MANUAL_CURRENT_PRICE = {}

# If your SelectedStock1.csv has any of these columns, the script will use it as current price.
CURRENT_PRICE_COLUMNS = ["CMP", "CurrentPrice", "Current Price", "LTP", "LastPrice", "Price"]

# Stock name buttons
# If INPUT_STOCKS contains any of these columns, the image title will use the full stock/company name.
# Otherwise, the script will use STOCK_NAME_OVERRIDES, then Yahoo Finance longName/shortName, then symbol fallback.
STOCK_NAME_COLUMNS = ["Stock", "Stock Name", "Company Name", "CompanyName", "Name"]

# Add or edit names here when Yahoo Finance name is unavailable or you want exact display text.
STOCK_NAME_OVERRIDES = {
    "POLYCAB": "Polycab India Ltd",
    "BLUESTARCO": "Blue Star Ltd",
    "M&M": "Mahindra & Mahindra Ltd",
    "MUTHOOTFIN": "Muthoot Finance Ltd",
}

TITLE_SUFFIX = "Technical Chart"
SUBTITLE_SUFFIX = "Technical Chart"
TITLE_MAX_WIDTH_PCT = 0.82
SUBTITLE_MAX_WIDTH_PCT = 0.74

SHOW_SUPPORT_RESISTANCE = True
SHOW_EMA_9 = True
SHOW_EMA_21 = True
SHOW_VOLUME = True
SHOW_RSI = True
SHOW_SIGNAL_BADGES = True

# Action level buttons
SHOW_ACTION_LEVELS = True
SHOW_BUY_ZONE_SHADE = True
SHOW_ACTION_PANEL = True
# Best-case setup logic: levels stay near recent actionable zones, not far catastrophic levels.
BEST_CASE_SETUP = True
LEVEL_LOOKBACK_CANDLES = 63      # ~3 months on daily candles
SWING_SUPPORT_BAND_PCT = 0.018   # Buy zone around support, approx 1.8% band
STOPLOSS_BELOW_SUPPORT_PCT = 0.025
TARGET_NEAR_RESISTANCE_PCT = 0.005

# Risk Reward buttons
# Practical swing-trade logic:
# 1:1.5 minimum | 1:2 preferred | 1:2.5+ excellent only if target is near real resistance.
RISK_REWARD = "1:2"              # Display/reference ratio, examples: "1:1.5", "1:2", "1:2.5"
MIN_RISK_REWARD = 1.5            # Minimum acceptable swing setup
IDEAL_RISK_REWARD = 2.0          # Preferred swing setup
EXCELLENT_RISK_REWARD = 2.5      # Excellent only when target is supported by resistance/structure

# IMPORTANT:
# False = do NOT blindly force target higher. Use natural resistance target and label setup quality.
# True  = force target to at least RISK_REWARD. Use only if you intentionally want educational/example images.
FORCE_TARGET_TO_RR = False
ENFORCE_MIN_RISK_REWARD = FORCE_TARGET_TO_RR  # backward-compatible old button name

SECOND_TARGET_EXTENSION_RATIO = 0.08
ACTION_LINE_WIDTH = 4
ACTION_LABEL_FONT_BOOST = 2

# Action-line placement buttons
# Keep horizontal BUY / SELL / SL lines slightly inside the plot area, so they do not touch/crop at edges.
ACTION_LINE_LEFT_INSET_PX = 24
ACTION_LINE_RIGHT_INSET_PX = 12

# Action label readability buttons
# These settings prevent BUY / SELL / SL tags from overlapping when levels are close.
ACTION_LABEL_MIN_GAP_PX = 34          # minimum vertical gap between right-side tags
ACTION_LABEL_RIGHT_PAD = 8            # distance from chart plot area to tags
ACTION_LABEL_CONNECTOR_WIDTH = 2      # connector line width from actual level to shifted tag
ACTION_LABEL_STAGGER_IF_CLOSE = True  # keep actual lines at true price but stagger labels
ACTION_LEVEL_EXTRA_Y_PADDING_PCT = 0.18  # extra chart y-axis padding for close action levels

# Chart placement buttons
CHART_TOP_GAP = 18
PRICE_CHART_HEIGHT_RATIO = 0.60
VOLUME_CHART_HEIGHT_RATIO = 0.16
RSI_CHART_HEIGHT_RATIO = 0.17
SECTION_GAP = 18

# =========================================================
# GENERAL IMAGE BUTTONS
# =========================================================
GENERAL_FIG_W = 7.5
GENERAL_FIG_H = 10.70
GENERAL_DPI = 160
GENERAL_TITLE_Y = 110
GENERAL_CARD_TOP = 243
GENERAL_CARD_SIDE_PAD = 78
GENERAL_CARD_INNER_PAD = 34
GENERAL_CARD_BOTTOM_MARGIN = 190
GENERAL_TITLE_FONT_SIZE = 66
GENERAL_SUBTITLE_FONT_SIZE = 28
GENERAL_LABEL_FONT_SIZE = 23
GENERAL_SMALL_FONT_SIZE = 20
GENERAL_FOOTER_FONT_SIZE = 38
GENERAL_HANDLE_Y = -180

# =========================================================
# INSTAGRAM IMAGE BUTTONS
# =========================================================
INSTAGRAM_FIG_W = 8.0
INSTAGRAM_FIG_H = 10.0
INSTAGRAM_DPI = 160
INSTAGRAM_TITLE_Y = 95
INSTAGRAM_CARD_TOP = 225
INSTAGRAM_CARD_SIDE_PAD = 70
INSTAGRAM_CARD_INNER_PAD = 30
INSTAGRAM_CARD_BOTTOM_MARGIN = 200
INSTAGRAM_TITLE_FONT_SIZE = 66
INSTAGRAM_SUBTITLE_FONT_SIZE = 28
INSTAGRAM_LABEL_FONT_SIZE = 26
INSTAGRAM_SMALL_FONT_SIZE = 24
INSTAGRAM_FOOTER_FONT_SIZE = 38
INSTAGRAM_HANDLE_Y = -160

# =========================================================
# STANDARD IMAGE BUTTONS
# =========================================================
# Full 16:9 desktop ratio output for standard image
STANDARD_FIG_W = 19.2
STANDARD_FIG_H = 10.8
STANDARD_DPI = 100
STANDARD_TITLE_Y = 88
STANDARD_CARD_TOP = 175
STANDARD_CARD_SIDE_PAD = 110
STANDARD_CARD_INNER_PAD = 30
STANDARD_CARD_BOTTOM_MARGIN = 105
STANDARD_TITLE_FONT_SIZE = 58
STANDARD_SUBTITLE_FONT_SIZE = 24
STANDARD_LABEL_FONT_SIZE = 20
STANDARD_SMALL_FONT_SIZE = 17
STANDARD_FOOTER_FONT_SIZE = 28
STANDARD_HANDLE_Y = -75

# =========================================================
# REELS IMAGE BUTTONS
# =========================================================
REELS_FIG_W = 10.0
REELS_FIG_H = 15.0
REELS_DPI = 120
REELS_TITLE_Y = 105
REELS_CARD_TOP = 255
REELS_CARD_SIDE_PAD = 72
REELS_CARD_INNER_PAD = 30
REELS_CARD_BOTTOM_MARGIN = 165
REELS_TITLE_FONT_SIZE = 64
REELS_SUBTITLE_FONT_SIZE = 28
REELS_LABEL_FONT_SIZE = 23
REELS_SMALL_FONT_SIZE = 20
REELS_FOOTER_FONT_SIZE = 34
REELS_HANDLE_Y = -105

# =========================================================
# STYLE COLORS
# =========================================================
NAVY_TOP = (10, 28, 52)
NAVY_BOT = (6, 16, 32)
CARD_FILL = (255, 255, 255)
CARD_OUTLINE = (26, 52, 82)
GRID = (228, 233, 240)
TEXT_DARK = (20, 30, 50)
TEXT_MUTED = (85, 96, 115)
GOLD = (243, 198, 65)
GREEN = (22, 145, 82)
RED = (205, 45, 45)
BLUE = (40, 105, 190)
ORANGE = (220, 132, 28)
PURPLE = (122, 80, 180)
AMBER = (210, 128, 26)
BUY_ZONE_FILL = (219, 247, 235)
STOPLOSS_FILL = (255, 228, 228)
TARGET_FILL = (255, 240, 210)

# =========================================================
# BASIC HELPERS
# =========================================================
def _get_date_folder() -> str:
    date_value = str(globals().get("DATE", "") or "").strip()
    if date_value:
        try:
            return datetime.strptime(date_value, "%d/%m/%Y").strftime("%d_%m_%Y")
        except Exception:
            pass
    return datetime.now().strftime("%d_%m_%Y")


def _get_analysis_date() -> datetime:
    date_value = str(globals().get("DATE", "") or "").strip()
    if date_value:
        try:
            return datetime.strptime(date_value, "%d/%m/%Y")
        except Exception:
            pass
    return datetime.now()


def _add_trading_days(start_dt: datetime, trading_days: int) -> datetime:
    if trading_days <= 0:
        return start_dt
    dt = pd.Timestamp(start_dt).normalize()
    added = 0
    while added < int(trading_days):
        dt += pd.Timedelta(days=1)
        if dt.weekday() < 5:
            added += 1
    return dt.to_pydatetime()


def _get_validity_date() -> datetime:
    override = str(globals().get("VALIDITY_DATE_OVERRIDE", "") or "").strip()
    if override:
        try:
            return datetime.strptime(override, "%d/%m/%Y")
        except Exception:
            pass

    base_dt = _get_analysis_date()
    mode = str(globals().get("VALIDITY_MODE", "AUTO_BY_TRADE_STYLE") or "AUTO_BY_TRADE_STYLE").strip().upper()

    if mode == "FIXED_TRADING_DAYS":
        days = int(globals().get("FIXED_VALIDITY_TRADING_DAYS", 5) or 5)
    else:
        trade_style = str(globals().get("TRADE_STYLE", "SWING") or "SWING").strip().upper()
        if trade_style == "INTRADAY":
            days = int(globals().get("INTRADAY_VALIDITY_TRADING_DAYS", 1) or 1)
        elif trade_style == "POSITIONAL":
            days = int(globals().get("POSITIONAL_VALIDITY_TRADING_DAYS", 20) or 20)
        else:
            days = int(globals().get("SWING_VALIDITY_TRADING_DAYS", 5) or 5)

    return _add_trading_days(base_dt, days)


def _get_validity_text() -> str:
    if not SHOW_VALIDITY_DATE:
        return ""
    prefix = str(globals().get("VALIDITY_TEXT_PREFIX", "Valid Till") or "Valid Till").strip()
    fmt = str(globals().get("VALIDITY_DATE_FORMAT", "%d %b %Y") or "%d %b %Y")
    try:
        dt = _get_validity_date()
        return f"{prefix}: {dt.strftime(fmt)}"
    except Exception:
        return prefix


def _safe_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace("/", "_").replace("\\", "_").replace(" ", "_")


def _safe_folder_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        return "Default"
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, '_')
    return value.strip('._ ') or "Default"


def _get_input_batch_name_from_path(path: str) -> str:
    base = os.path.splitext(os.path.basename(str(path).strip()))[0].strip()
    if not base:
        return "Default"

    # Example: NIFTY_MIDCAP_SELECT.xlsx -> MIDCAP_SELECT
    upper = base.upper()
    if upper.startswith("NIFTY_") and len(base) > len("NIFTY_"):
        base = base[len("NIFTY_"):]

    return _safe_folder_name(base)


def _set_current_input_context(path: str):
    global CURRENT_INPUT_FILE_PATH, CURRENT_INPUT_BATCH_NAME
    CURRENT_INPUT_FILE_PATH = str(path or "").strip()
    CURRENT_INPUT_BATCH_NAME = _get_input_batch_name_from_path(CURRENT_INPUT_FILE_PATH)


def _get_current_output_root() -> str:
    date_folder = _get_date_folder()
    batch_name = _safe_folder_name(globals().get("CURRENT_INPUT_BATCH_NAME", "") or "Default")
    return os.path.join("Images", date_folder, batch_name)


def build_output_path(symbol: str, image_type: str) -> str:
    # Master/full chart output path
    path = os.path.join(_get_current_output_root(), "Master", str(image_type), f"{_safe_symbol(symbol)}.jpeg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def build_subimage_output_path(symbol: str, image_type: str, suffix: str) -> str:
    path = os.path.join(
        _get_current_output_root(),
        "SubImages",
        str(image_type),
        _safe_symbol(symbol),
        f"{_safe_symbol(symbol)}{suffix}.jpeg",
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def build_chart_reveal_output_path(symbol: str, image_type: str, reveal_mode: str) -> str:
    reveal_mode = str(reveal_mode).upper()
    suffix = CHART_REVEAL_SUFFIX.get(reveal_mode, "")
    if not suffix:
        return build_output_path(symbol, image_type)
    return build_subimage_output_path(symbol, image_type, suffix)


def build_action_line_step_output_path(symbol: str, image_type: str, step_mode: str) -> str:
    suffix = ACTION_LINE_STEP_SUFFIX.get(str(step_mode).upper(), "")
    return build_subimage_output_path(symbol, image_type, suffix)


def build_summary_output_path(symbol: str, image_type: str) -> str:
    path = os.path.join(_get_current_output_root(), str(image_type), f"{_safe_symbol(symbol)}_Summary.jpeg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _load_font(size: int, bold: bool = False):
    candidates = []
    win_dir = r"C:\Windows\Fonts"
    if os.path.isdir(win_dir):
        if bold:
            candidates += [
                os.path.join(win_dir, "calibrib.ttf"),
                os.path.join(win_dir, "arialbd.ttf"),
                os.path.join(win_dir, "seguisb.ttf"),
            ]
        else:
            candidates += [
                os.path.join(win_dir, "calibri.ttf"),
                os.path.join(win_dir, "arial.ttf"),
                os.path.join(win_dir, "segoeui.ttf"),
            ]

    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]

    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_font_to_width(draw, text, max_width: int, start_size: int, bold: bool = True, min_size: int = 24):
    """
    Keeps long company-name titles inside the canvas by reducing font size only when needed.
    """
    size = int(start_size)
    while size > int(min_size):
        font = _load_font(size, bold=bold)
        if draw.textlength(str(text), font=font) <= max_width:
            return font
        size -= 2
    return _load_font(min_size, bold=bold)


def _clean_company_name(value):
    try:
        if value is None or pd.isna(value):
            return ""
        txt = str(value).strip()
        if not txt or txt.lower() in ["nan", "none", "null"]:
            return ""
        return " ".join(txt.split())
    except Exception:
        return ""


def _get_stock_display_name(symbol: str, stock_row: dict | None = None) -> str:
    """
    Returns full stock/company name for title.
    Priority:
    1. Name available in INPUT_STOCKS columns
    2. STOCK_NAME_OVERRIDES
    3. Yahoo Finance longName/shortName
    4. Symbol fallback
    """
    sym = _safe_symbol(symbol)

    if stock_row:
        for col in STOCK_NAME_COLUMNS:
            if col in stock_row:
                name = _clean_company_name(stock_row.get(col))
                if name:
                    return name

    override = _clean_company_name(STOCK_NAME_OVERRIDES.get(sym))
    if override:
        return override

    if yf is not None and str(DATA_MODE).upper() != "SIMULATED_ONLY":
        try:
            info = yf.Ticker(_yf_symbol(sym)).get_info()
            for key in ["longName", "shortName"]:
                name = _clean_company_name(info.get(key))
                if name:
                    return name
        except Exception:
            pass

    return sym


def _center(draw, W, text, y, font, fill):
    tw = draw.textlength(str(text), font=font)
    draw.text(((W - tw) / 2, y), str(text), font=font, fill=fill)


def _draw_vertical_gradient(img, top_color=NAVY_TOP, bottom_color=NAVY_BOT):
    w, h = img.size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    img.paste(grad, (0, 0))


def _add_vignette(img, strength=0.35):
    w, h = img.size
    vignette = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(vignette)
    margin = int(min(w, h) * 0.08)
    draw.ellipse([margin, margin, w - margin, h - margin], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=int(min(w, h) * 0.07)))
    inv = Image.eval(vignette, lambda p: 255 - p)
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    img.paste(overlay, (0, 0), Image.eval(inv, lambda p: int(p * strength)))


def _rounded_shadow_card(base_img, box, radius=30):
    l, t, r, b = box
    w, h = r - l, b - t
    shadow_blur = 22
    shadow = Image.new("RGBA", (w + shadow_blur * 4, h + shadow_blur * 4), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [shadow_blur * 2, shadow_blur * 2, shadow_blur * 2 + w, shadow_blur * 2 + h],
        radius=radius,
        fill=(0, 0, 0, 125),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    base_img.paste(shadow, (l - shadow_blur * 2, t + 14 - shadow_blur * 2), shadow)

    card_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_layer)
    cd.rounded_rectangle([l, t, r, b], radius=radius, fill=CARD_FILL)
    cd.rounded_rectangle([l, t, r, b], radius=radius, outline=CARD_OUTLINE, width=3)
    cd.rounded_rectangle([l + 6, t + 6, r - 6, b - 6], radius=max(6, radius - 6), outline=(210, 220, 232), width=2)
    base_img.paste(card_layer, (0, 0), card_layer)


def _get_image_layout(image_mode: str):
    m = str(image_mode).lower().strip()
    if m == "instagram":
        return {
            "size": (int(INSTAGRAM_FIG_W * INSTAGRAM_DPI), int(INSTAGRAM_FIG_H * INSTAGRAM_DPI)),
            "title_y": INSTAGRAM_TITLE_Y,
            "card_top": INSTAGRAM_CARD_TOP,
            "card_side_pad": INSTAGRAM_CARD_SIDE_PAD,
            "inner_pad": INSTAGRAM_CARD_INNER_PAD,
            "card_bottom_margin": INSTAGRAM_CARD_BOTTOM_MARGIN,
            "title_font": INSTAGRAM_TITLE_FONT_SIZE,
            "subtitle_font": INSTAGRAM_SUBTITLE_FONT_SIZE,
            "label_font": INSTAGRAM_LABEL_FONT_SIZE,
            "small_font": INSTAGRAM_SMALL_FONT_SIZE,
            "footer_font": INSTAGRAM_FOOTER_FONT_SIZE,
            "handle_y": INSTAGRAM_HANDLE_Y,
            "validity_font": INSTAGRAM_VALIDITY_FONT_SIZE,
            "validity_y_shift": INSTAGRAM_VALIDITY_Y_SHIFT,
        }
    if m == "standard":
        return {
            "size": (int(STANDARD_FIG_W * STANDARD_DPI), int(STANDARD_FIG_H * STANDARD_DPI)),
            "title_y": STANDARD_TITLE_Y,
            "card_top": STANDARD_CARD_TOP,
            "card_side_pad": STANDARD_CARD_SIDE_PAD,
            "inner_pad": STANDARD_CARD_INNER_PAD,
            "card_bottom_margin": STANDARD_CARD_BOTTOM_MARGIN,
            "title_font": STANDARD_TITLE_FONT_SIZE,
            "subtitle_font": STANDARD_SUBTITLE_FONT_SIZE,
            "label_font": STANDARD_LABEL_FONT_SIZE,
            "small_font": STANDARD_SMALL_FONT_SIZE,
            "footer_font": STANDARD_FOOTER_FONT_SIZE,
            "handle_y": STANDARD_HANDLE_Y,
            "validity_font": STANDARD_VALIDITY_FONT_SIZE,
            "validity_y_shift": STANDARD_VALIDITY_Y_SHIFT,
        }
    if m == "reels":
        return {
            "size": (int(REELS_FIG_W * REELS_DPI), int(REELS_FIG_H * REELS_DPI)),
            "title_y": REELS_TITLE_Y,
            "card_top": REELS_CARD_TOP,
            "card_side_pad": REELS_CARD_SIDE_PAD,
            "inner_pad": REELS_CARD_INNER_PAD,
            "card_bottom_margin": REELS_CARD_BOTTOM_MARGIN,
            "title_font": REELS_TITLE_FONT_SIZE,
            "subtitle_font": REELS_SUBTITLE_FONT_SIZE,
            "label_font": REELS_LABEL_FONT_SIZE,
            "small_font": REELS_SMALL_FONT_SIZE,
            "footer_font": REELS_FOOTER_FONT_SIZE,
            "handle_y": REELS_HANDLE_Y,
            "validity_font": REELS_VALIDITY_FONT_SIZE,
            "validity_y_shift": REELS_VALIDITY_Y_SHIFT,
        }
    return {
        "size": (int(GENERAL_FIG_W * GENERAL_DPI), int(GENERAL_FIG_H * GENERAL_DPI)),
        "title_y": GENERAL_TITLE_Y,
        "card_top": GENERAL_CARD_TOP,
        "card_side_pad": GENERAL_CARD_SIDE_PAD,
        "inner_pad": GENERAL_CARD_INNER_PAD,
        "card_bottom_margin": GENERAL_CARD_BOTTOM_MARGIN,
        "title_font": GENERAL_TITLE_FONT_SIZE,
        "subtitle_font": GENERAL_SUBTITLE_FONT_SIZE,
        "label_font": GENERAL_LABEL_FONT_SIZE,
        "small_font": GENERAL_SMALL_FONT_SIZE,
        "footer_font": GENERAL_FOOTER_FONT_SIZE,
        "handle_y": GENERAL_HANDLE_Y,
        "validity_font": GENERAL_VALIDITY_FONT_SIZE,
        "validity_y_shift": GENERAL_VALIDITY_Y_SHIFT,
    }

# =========================================================
# DATA SIMULATION + INDICATORS
# =========================================================
def _clean_price_value(v):
    try:
        if pd.isna(v):
            return None
        x = float(str(v).replace(",", "").replace("₹", "").strip())
        return x if x > 0 else None
    except Exception:
        return None


def _get_current_price_from_row(symbol: str, stock_row: dict | None = None):
    if stock_row:
        for col in CURRENT_PRICE_COLUMNS:
            if col in stock_row:
                x = _clean_price_value(stock_row.get(col))
                if x is not None:
                    return x
    return _clean_price_value(MANUAL_CURRENT_PRICE.get(symbol))


def _yf_symbol(symbol: str) -> str:
    symbol = str(symbol).strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def fetch_real_ohlcv(symbol: str) -> pd.DataFrame | None:
    if yf is None or str(DATA_MODE).upper() == "SIMULATED_ONLY":
        return None
    try:
        data = yf.download(
            _yf_symbol(symbol),
            period=HISTORY_PERIOD,
            interval=HISTORY_INTERVAL,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if data is None or data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] for c in data.columns]

        data = data.reset_index()
        date_col = "Date" if "Date" in data.columns else data.columns[0]
        data = data.rename(columns={date_col: "Date"})

        required = ["Open", "High", "Low", "Close", "Volume"]
        if any(c not in data.columns for c in required):
            return None

        data = data[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            data[c] = pd.to_numeric(data[c], errors="coerce")
        data = data.dropna(subset=["Open", "High", "Low", "Close"])
        data = data.tail(SIMULATION_CANDLES).reset_index(drop=True)
        if len(data) < 40:
            return None

        data["EMA9"] = data["Close"].ewm(span=9, adjust=False).mean()
        data["EMA21"] = data["Close"].ewm(span=21, adjust=False).mean()
        data["RSI"] = calculate_rsi(data["Close"], period=14)
        data["DataSource"] = "Real Yahoo Finance"
        return data
    except Exception as e:
        print(f"⚠ Could not fetch real data for {symbol}: {e}")
        return None


def simulate_ohlcv(symbol: str, candles: int = SIMULATION_CANDLES, stock_row: dict | None = None) -> pd.DataFrame:
    real_df = fetch_real_ohlcv(symbol)
    if real_df is not None:
        return real_df

    seed = int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    current_price = _get_current_price_from_row(symbol, stock_row)
    if current_price is None:
        current_price = START_PRICE + (seed % 900)

    # Build a realistic chart whose last close is anchored near current price,
    # so generated buy/sell levels do not appear at impossible old prices.
    trend = rng.choice([-1, 1]) * TREND_STRENGTH
    returns = rng.normal(loc=trend, scale=VOLATILITY, size=candles)
    close = np.cumprod(1 + returns)
    close = close / close[-1] * current_price

    open_ = np.r_[close[0] * (1 + rng.normal(0, 0.004)), close[:-1] * (1 + rng.normal(0, 0.006, candles - 1))]
    high = np.maximum(open_, close) * (1 + rng.uniform(0.003, 0.018, candles))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.003, 0.018, candles))
    volume = rng.integers(120000, 1100000, candles)

    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=candles, freq="B")
    df = pd.DataFrame({
        "Date": dates,
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    })

    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], period=14)
    df["DataSource"] = "Context Simulated"
    return df


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def get_signal_summary(df: pd.DataFrame):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    trend = "Bullish" if last["EMA9"] > last["EMA21"] else "Bearish"
    rsi = float(last["RSI"])

    if prev["EMA9"] <= prev["EMA21"] and last["EMA9"] > last["EMA21"]:
        action = "Fresh Buy Crossover"
        color = GREEN
    elif prev["EMA9"] >= prev["EMA21"] and last["EMA9"] < last["EMA21"]:
        action = "Fresh Sell Crossover"
        color = RED
    elif trend == "Bullish" and 45 <= rsi <= 70:
        action = "Buy on Dip Zone"
        color = GREEN
    elif trend == "Bearish" and rsi < 55:
        action = "Weak / Wait Zone"
        color = RED
    else:
        action = "Neutral / Watch"
        color = (95, 105, 120)

    return {
        "trend": trend,
        "rsi": rsi,
        "action": action,
        "color": color,
        "close": float(last["Close"]),
        "change_pct": ((last["Close"] - prev["Close"]) / prev["Close"]) * 100,
    }


def _nearest_recent_support(df: pd.DataFrame, close: float, lookback: int):
    recent = df.tail(lookback).copy()
    lows = pd.to_numeric(recent["Low"], errors="coerce").dropna().sort_values().values
    if len(lows) == 0:
        return close * 0.97

    # Prefer nearest support below CMP, not the absolute lowest crash wick.
    below = lows[lows < close]
    if len(below) == 0:
        return float(np.percentile(lows, 35))

    # Choose a stable support cluster from the upper side of below-CMP lows.
    q = float(np.percentile(below, 70))
    support = max(q, close * 0.90)
    return support


def _nearest_recent_resistance(df: pd.DataFrame, close: float, lookback: int):
    recent = df.tail(lookback).copy()
    highs = pd.to_numeric(recent["High"], errors="coerce").dropna().sort_values().values
    if len(highs) == 0:
        return close * 1.05

    above = highs[highs > close]
    if len(above) == 0:
        return close * 1.04

    # Choose nearest realistic resistance zone, not a very distant all-time high.
    resistance = float(np.percentile(above, 35))
    return max(resistance, close * 1.025)



def _parse_risk_reward_ratio(value) -> float:
    """
    Converts RISK_REWARD button value into minimum reward multiple.
    Example: "1:2" => 2.0, "1:2.5" => 2.5.
    """
    try:
        txt = str(value).strip().replace(" ", "")
        if ":" in txt:
            left, right = txt.split(":", 1)
            risk = float(left)
            reward = float(right)
            if risk > 0 and reward > 0:
                return reward / risk
        x = float(txt)
        return x if x > 0 else 2.0
    except Exception:
        return 2.0


def get_trade_plan(df: pd.DataFrame):
    """
    Creates realistic visual levels based on recent price context.

    New practical swing logic:
    - Target is first taken from nearest recent resistance.
    - Target is NOT blindly pushed to 1:2 unless FORCE_TARGET_TO_RR=True.
    - Setup quality is classified based on natural chart-based R:R:
        < 1:1.5  => Avoid / Wait
        1:1.5+   => Moderate
        1:2+     => Good
        1:2.5+   => Excellent, but only if target is close to real resistance
    """
    close = float(df.iloc[-1]["Close"])
    lookback = min(LEVEL_LOOKBACK_CANDLES, max(30, len(df)))

    support = _nearest_recent_support(df, close, lookback)
    resistance = _nearest_recent_resistance(df, close, lookback)

    # Buy zone should be actionable around current structure.
    buy_low = support
    buy_high = support * (1 + SWING_SUPPORT_BAND_PCT)

    # If price is already very close to support, make buy zone around CMP/support blend.
    if close <= buy_high * 1.015:
        buy_high = max(close, support * (1 + SWING_SUPPORT_BAND_PCT))
        buy_low = min(support, close * (1 - SWING_SUPPORT_BAND_PCT))

    stop_loss = support * (1 - STOPLOSS_BELOW_SUPPORT_PCT)

    # Natural target from actual nearby resistance.
    natural_target_1 = resistance * (1 - TARGET_NEAR_RESISTANCE_PCT)

    # Optional forced target only when explicitly enabled.
    risk_points = max(0.01, buy_high - stop_loss)
    preferred_rr = _parse_risk_reward_ratio(RISK_REWARD)
    forced_rr_target = buy_high + (risk_points * preferred_rr)

    if FORCE_TARGET_TO_RR:
        target_1 = max(natural_target_1, forced_rr_target)
        target_source = "Forced R:R Target" if target_1 > natural_target_1 else "Resistance Target"
    else:
        target_1 = natural_target_1
        target_source = "Resistance Target"

    # Keep target logical even when market data has a very tight range.
    if target_1 <= buy_high:
        target_1 = buy_high * 1.025
        target_source = "Minimum Logical Target"

    target_2 = target_1 + max((target_1 - buy_high) * SECOND_TARGET_EXTENSION_RATIO, risk_points * 0.25)

    risk = max(0.01, buy_high - stop_loss)
    reward = max(0.01, target_1 - buy_high)
    rr = reward / risk

    # Check whether the target is actually supported by nearby resistance/structure.
    # If target has been forced far above resistance, mark it as extended.
    target_near_resistance = abs(target_1 - natural_target_1) <= max(close * 0.01, risk * 0.35)

    # Trend confirmation for warning labels.
    last = df.iloc[-1]
    trend = "Bullish" if float(last["EMA9"]) > float(last["EMA21"]) else "Bearish"
    rsi = float(last["RSI"])

    if rr < MIN_RISK_REWARD:
        decision = "Avoid Fresh Buy"
        decision_color = RED
        setup_grade = "Weak"
    elif rr < IDEAL_RISK_REWARD:
        decision = "Moderate Setup"
        decision_color = AMBER
        setup_grade = "Moderate"
    elif rr < EXCELLENT_RISK_REWARD:
        decision = "Good Swing Setup"
        decision_color = GREEN
        setup_grade = "Good"
    else:
        if target_near_resistance:
            decision = "Excellent Setup"
            decision_color = GREEN
            setup_grade = "Excellent"
        else:
            decision = "Extended Target"
            decision_color = AMBER
            setup_grade = "Extended"

    # If price is near buy zone but trend is weak, avoid making the card look like a blind BUY.
    if trend == "Bearish" and decision not in ["Avoid Fresh Buy"]:
        decision = f"{decision} | Trend Weak"
        decision_color = AMBER

    if close < buy_low:
        decision = "Below Zone / Risky"
        decision_color = RED
        setup_grade = "Risky"
    elif buy_low <= close <= buy_high * 1.015 and rr >= MIN_RISK_REWARD and trend != "Bearish":
        decision = "Near Buy Zone"
        decision_color = GREEN

    return {
        "support": support,
        "resistance": resistance,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "natural_target_1": natural_target_1,
        "target_source": target_source,
        "target_near_resistance": target_near_resistance,
        "decision": decision,
        "decision_color": decision_color,
        "setup_grade": setup_grade,
        "risk_reward": rr,
        "min_risk_reward": MIN_RISK_REWARD,
        "ideal_risk_reward": IDEAL_RISK_REWARD,
        "excellent_risk_reward": EXCELLENT_RISK_REWARD,
        "risk_reward_label": str(RISK_REWARD),
    }

# =========================================================
# DRAWING HELPERS FOR CHARTS
# =========================================================
def _scale_y(value, vmin, vmax, y0, y1):
    if vmax == vmin:
        return (y0 + y1) / 2
    return y1 - ((value - vmin) / (vmax - vmin)) * (y1 - y0)


def _draw_panel(draw, box, title, font):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=(248, 251, 255), outline=(218, 226, 238), width=2)
    draw.text((x0 + 14, y0 + 10), title, font=font, fill=TEXT_MUTED)


def _draw_grid(draw, box, rows=4, cols=4):
    x0, y0, x1, y1 = box
    for i in range(1, rows):
        y = y0 + (y1 - y0) * i / rows
        draw.line([x0, y, x1, y], fill=GRID, width=1)
    for i in range(1, cols):
        x = x0 + (x1 - x0) * i / cols
        draw.line([x, y0, x, y1], fill=GRID, width=1)


def _draw_dashed_line(draw, xy, fill, width=3, dash=14, gap=8):
    x0, y0, x1, y1 = xy
    if abs(y1 - y0) < 1:
        x = x0
        while x < x1:
            draw.line([x, y0, min(x + dash, x1), y1], fill=fill, width=width)
            x += dash + gap
    else:
        draw.line(xy, fill=fill, width=width)


def _draw_price_tag(draw, x, y, text, font, fill, bg):
    pad_x, pad_y = 8, 4
    tw = draw.textlength(text, font=font)
    h = font.size + pad_y * 2
    draw.rounded_rectangle([x, y - h / 2, x + tw + pad_x * 2, y + h / 2], radius=8, fill=bg, outline=fill, width=2)
    draw.text((x + pad_x, y - font.size / 2 - 1), text, font=font, fill=fill)
    return x + tw + pad_x * 2, h


def _spread_label_positions(level_items, y_min, y_max, min_gap):
    """
    Keep price lines at their exact scaled level, but spread the text labels vertically.
    This prevents SELL / BUY / SL tags from overlapping when price levels are close.
    """
    if not ACTION_LABEL_STAGGER_IF_CLOSE or len(level_items) <= 1:
        return {item["key"]: item["y"] for item in level_items}

    ordered = sorted(level_items, key=lambda d: d["y"])
    positions = [float(item["y"]) for item in ordered]

    # Forward pass: enforce minimum gap from top to bottom.
    for i in range(1, len(positions)):
        if positions[i] - positions[i - 1] < min_gap:
            positions[i] = positions[i - 1] + min_gap

    # If labels go beyond lower bound, shift the whole cluster upward.
    overflow = positions[-1] - y_max
    if overflow > 0:
        positions = [y - overflow for y in positions]

    # Backward pass: enforce top bound and gap again.
    for i in range(len(positions) - 2, -1, -1):
        if positions[i + 1] - positions[i] < min_gap:
            positions[i] = positions[i + 1] - min_gap

    underflow = y_min - positions[0]
    if underflow > 0:
        positions = [y + underflow for y in positions]

    return {ordered[i]["key"]: positions[i] for i in range(len(ordered))}


def _normalize_reveal_mode(reveal_mode: str = "FULL") -> str:
    mode = str(reveal_mode or "FULL").strip().upper()
    allowed = [
        "BLANK_VALUES",
        "HEADINGS_ONLY",
        "FULL",
        "BUY_LINE_ONLY",
        "BUY_TARGET_LINES",
        "BUY_TARGET_SL_LINES",
    ]
    if mode not in allowed:
        return "FULL"
    return mode


def _is_action_line_step_mode(reveal_mode: str = "FULL") -> bool:
    return _normalize_reveal_mode(reveal_mode) in ["BUY_LINE_ONLY", "BUY_TARGET_LINES", "BUY_TARGET_SL_LINES"]


def _should_draw_reveal_action_lines(reveal_mode: str = "FULL") -> bool:
    mode = _normalize_reveal_mode(reveal_mode)
    if mode == "BLANK_VALUES":
        return bool(SHOW_ACTION_LINES_IN_BLANK_VALUES_IMAGE)
    if mode == "HEADINGS_ONLY":
        return bool(SHOW_ACTION_LINES_IN_HEADINGS_ONLY_IMAGE)
    return True


def _should_draw_reveal_action_tags(reveal_mode: str = "FULL") -> bool:
    mode = _normalize_reveal_mode(reveal_mode)
    if mode == "BLANK_VALUES":
        return bool(SHOW_ACTION_TAGS_IN_BLANK_VALUES_IMAGE)
    if mode == "HEADINGS_ONLY":
        return bool(SHOW_ACTION_TAGS_IN_HEADINGS_ONLY_IMAGE)
    return True


def _visible_action_keys_for_mode(reveal_mode: str = "FULL"):
    mode = _normalize_reveal_mode(reveal_mode)
    if mode == "BUY_LINE_ONLY":
        return {"buy"}
    if mode == "BUY_TARGET_LINES":
        return {"buy", "target"}
    if mode == "BUY_TARGET_SL_LINES":
        return {"buy", "target", "sl"}
    return {"buy", "target", "sl"}


def _action_tag_text(mode: str, key: str, plan: dict) -> str:
    mode = _normalize_reveal_mode(mode)

    if mode in ["FULL", "BUY_LINE_ONLY", "BUY_TARGET_LINES", "BUY_TARGET_SL_LINES"]:
        if key == "target":
            return f"SELL / T1 {plan['target_1']:,.0f}"
        if key == "buy":
            return f"BUY {plan['buy_low']:,.0f}-{plan['buy_high']:,.0f}"
        if key == "sl":
            return f"SL {plan['stop_loss']:,.0f}"

    if mode == "HEADINGS_ONLY":
        if key == "target":
            return "SELL / TARGET"
        if key == "buy":
            return "BUY ZONE"
        if key == "sl":
            return "STOP LOSS"

    # BLANK_VALUES: keep short labels but hide the numeric values
    if key == "target":
        return "SELL / T1"
    if key == "buy":
        return "BUY"
    if key == "sl":
        return "SL"
    return ""


def _draw_action_levels(draw, plan, plot_box, vmin, vmax, label_font, reveal_mode: str = "FULL"):
    if not SHOW_ACTION_LEVELS:
        return

    reveal_mode = _normalize_reveal_mode(reveal_mode)
    draw_action_lines = _should_draw_reveal_action_lines(reveal_mode)
    draw_action_tags = _should_draw_reveal_action_tags(reveal_mode)

    px0, py0, px1, py1 = plot_box
    label_x = px1 + ACTION_LABEL_RIGHT_PAD

    y_buy_high = _scale_y(plan["buy_high"], vmin, vmax, py0, py1)
    y_buy_low = _scale_y(plan["buy_low"], vmin, vmax, py0, py1)
    y_sl = _scale_y(plan["stop_loss"], vmin, vmax, py0, py1)
    y_t1 = _scale_y(plan["target_1"], vmin, vmax, py0, py1)
    y_t2 = _scale_y(plan["target_2"], vmin, vmax, py0, py1)

    if SHOW_BUY_ZONE_SHADE:
        draw.rounded_rectangle(
            [px0, min(y_buy_low, y_buy_high), px1, max(y_buy_low, y_buy_high)],
            radius=6,
            fill=BUY_ZONE_FILL,
            outline=(170, 230, 200),
            width=1,
        )

    line_x0 = px0 + ACTION_LINE_LEFT_INSET_PX
    line_x1 = px1 - ACTION_LINE_RIGHT_INSET_PX

    visible_keys = _visible_action_keys_for_mode(reveal_mode)

    if draw_action_lines:
        if "target" in visible_keys:
            _draw_dashed_line(draw, [line_x0, y_t2, line_x1, y_t2], fill=AMBER, width=2, dash=13, gap=8)
            draw.line([line_x0, y_t1, line_x1, y_t1], fill=AMBER, width=ACTION_LINE_WIDTH)
        if "buy" in visible_keys:
            draw.line([line_x0, y_buy_high, line_x1, y_buy_high], fill=GREEN, width=ACTION_LINE_WIDTH)
            draw.line([line_x0, y_buy_low, line_x1, y_buy_low], fill=GREEN, width=2)
        if "sl" in visible_keys:
            draw.line([line_x0, y_sl, line_x1, y_sl], fill=RED, width=ACTION_LINE_WIDTH)

    if not draw_action_tags:
        return

    all_tag_items = [
        {"key": "target", "y": y_t1, "text": _action_tag_text(reveal_mode, "target", plan), "fill": AMBER, "bg": TARGET_FILL},
        {"key": "buy", "y": y_buy_high, "text": _action_tag_text(reveal_mode, "buy", plan), "fill": GREEN, "bg": BUY_ZONE_FILL},
        {"key": "sl", "y": y_sl, "text": _action_tag_text(reveal_mode, "sl", plan), "fill": RED, "bg": STOPLOSS_FILL},
    ]
    tag_items = [item for item in all_tag_items if item["key"] in visible_keys]
    label_positions = _spread_label_positions(
        tag_items,
        py0 + 18,
        py1 - 18,
        max(int(ACTION_LABEL_MIN_GAP_PX), int(label_font.size * 1.45)),
    )

    for item in tag_items:
        actual_y = item["y"]
        tag_y = label_positions[item["key"]]

        # Small connector keeps the tag readable while still showing the exact price line.
        if abs(tag_y - actual_y) > 3:
            draw.line(
                [line_x1, actual_y, label_x - 4, tag_y],
                fill=item["fill"],
                width=ACTION_LABEL_CONNECTOR_WIDTH,
            )

        _draw_price_tag(draw, label_x, tag_y, item["text"], label_font, item["fill"], item["bg"])


def _draw_line_series(draw, values, box, vmin, vmax, color, width=3):
    x0, y0, x1, y1 = box
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        if pd.isna(v):
            continue
        x = x0 + (x1 - x0) * i / max(1, n - 1)
        y = _scale_y(float(v), vmin, vmax, y0, y1)
        pts.append((x, y))
    if len(pts) >= 2:
        draw.line(pts, fill=color, width=width, joint="curve")


def _draw_candles(draw, df, box, label_font, plan=None, reveal_mode: str = "FULL"):
    x0, y0, x1, y1 = box
    plot_y0 = y0 + 42
    plot_y1 = y1 - 28
    plot_box = (x0 + 14, plot_y0, x1 - 190, plot_y1)
    px0, py0, px1, py1 = plot_box

    price_min = float(df["Low"].min())
    price_max = float(df["High"].max())
    if plan is not None:
        price_min = min(price_min, float(plan["stop_loss"]), float(plan["buy_low"]))
        price_max = max(price_max, float(plan["target_2"]), float(plan["target_1"]))
    base_range = max(price_max - price_min, float(df.iloc[-1]["Close"]) * 0.02)
    pad = base_range * (0.08 + ACTION_LEVEL_EXTRA_Y_PADDING_PCT)
    vmin = price_min - pad
    vmax = price_max + pad

    _draw_grid(draw, plot_box, rows=5, cols=5)

    support = float(df["Low"].tail(25).min())
    resistance = float(df["High"].tail(25).max())

    if SHOW_SUPPORT_RESISTANCE:
        sy = _scale_y(support, vmin, vmax, py0, py1)
        ry = _scale_y(resistance, vmin, vmax, py0, py1)
        _draw_dashed_line(draw, [px0, sy, px1, sy], fill=(116, 180, 145), width=2, dash=12, gap=8)
        _draw_dashed_line(draw, [px0, ry, px1, ry], fill=(215, 120, 120), width=2, dash=12, gap=8)

    if plan is not None:
        _draw_action_levels(draw, plan, plot_box, vmin, vmax, label_font, reveal_mode=reveal_mode)

    n = len(df)
    step = (px1 - px0) / max(1, n)
    body_w = max(3, int(step * 0.56))

    for i, row in df.reset_index(drop=True).iterrows():
        cx = px0 + step * i + step / 2
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        color = GREEN if c >= o else RED
        y_open = _scale_y(o, vmin, vmax, py0, py1)
        y_close = _scale_y(c, vmin, vmax, py0, py1)
        y_high = _scale_y(h, vmin, vmax, py0, py1)
        y_low = _scale_y(l, vmin, vmax, py0, py1)
        draw.line([cx, y_high, cx, y_low], fill=color, width=2)
        top = min(y_open, y_close)
        bottom = max(y_open, y_close)
        if bottom - top < 2:
            bottom = top + 2
        draw.rectangle([cx - body_w / 2, top, cx + body_w / 2, bottom], fill=color, outline=color)

    if SHOW_EMA_9:
        _draw_line_series(draw, df["EMA9"].values, plot_box, vmin, vmax, BLUE, width=3)
    if SHOW_EMA_21:
        _draw_line_series(draw, df["EMA21"].values, plot_box, vmin, vmax, ORANGE, width=3)

    draw.text((x0 + 16, y1 - 24), "EMA9", font=label_font, fill=BLUE)
    draw.text((x0 + 88, y1 - 24), "EMA21", font=label_font, fill=ORANGE)
    draw.text((x1 - 175, y0 + 12), f"Close: {df.iloc[-1]['Close']:,.2f}", font=label_font, fill=TEXT_DARK)


def _draw_volume(draw, df, box, label_font):
    x0, y0, x1, y1 = box
    plot_y0 = y0 + 38
    plot_y1 = y1 - 18
    plot_box = (x0 + 14, plot_y0, x1 - 20, plot_y1)
    px0, py0, px1, py1 = plot_box
    _draw_grid(draw, plot_box, rows=3, cols=5)

    vmax = max(1, float(df["Volume"].max()))
    n = len(df)
    step = (px1 - px0) / max(1, n)
    bar_w = max(2, int(step * 0.58))

    for i, row in df.reset_index(drop=True).iterrows():
        cx = px0 + step * i + step / 2
        vol = float(row["Volume"])
        bar_top = py1 - (vol / vmax) * (py1 - py0)
        color = GREEN if row["Close"] >= row["Open"] else RED
        draw.rectangle([cx - bar_w / 2, bar_top, cx + bar_w / 2, py1], fill=color)

    avg_vol = int(df["Volume"].tail(20).mean())
    draw.text((x1 - 190, y0 + 10), f"Avg Vol: {avg_vol:,}", font=label_font, fill=TEXT_MUTED)


def _draw_rsi(draw, df, box, label_font):
    x0, y0, x1, y1 = box
    plot_y0 = y0 + 38
    plot_y1 = y1 - 22
    plot_box = (x0 + 14, plot_y0, x1 - 45, plot_y1)
    px0, py0, px1, py1 = plot_box
    _draw_grid(draw, plot_box, rows=4, cols=5)

    y70 = _scale_y(70, 0, 100, py0, py1)
    y30 = _scale_y(30, 0, 100, py0, py1)
    draw.line([px0, y70, px1, y70], fill=RED, width=2)
    draw.line([px0, y30, px1, y30], fill=GREEN, width=2)
    draw.text((px1 + 8, y70 - 10), "70", font=label_font, fill=RED)
    draw.text((px1 + 8, y30 - 10), "30", font=label_font, fill=GREEN)
    _draw_line_series(draw, df["RSI"].values, plot_box, 0, 100, PURPLE, width=3)
    draw.text((x1 - 140, y0 + 10), f"RSI: {df.iloc[-1]['RSI']:.1f}", font=label_font, fill=PURPLE)


def _draw_badges(draw, box, summary, font, small_font):
    x0, y0, x1, y1 = box
    badge_h = 46
    gap = 12
    labels = [
        ("Trend", summary["trend"], GREEN if summary["trend"] == "Bullish" else RED),
        ("Signal", summary["action"], summary["color"]),
        ("1D", f"{summary['change_pct']:+.2f}%", GREEN if summary["change_pct"] >= 0 else RED),
    ]
    available_w = x1 - x0
    badge_w = int((available_w - 2 * gap) / 3)
    for i, (k, v, color) in enumerate(labels):
        bx0 = x0 + i * (badge_w + gap)
        bx1 = bx0 + badge_w
        draw.rounded_rectangle([bx0, y0, bx1, y0 + badge_h], radius=17, fill=(244, 248, 252), outline=(220, 228, 238), width=2)
        draw.text((bx0 + 13, y0 + 9), f"{k}: ", font=small_font, fill=TEXT_MUTED)
        key_w = draw.textlength(f"{k}: ", font=small_font)
        draw.text((bx0 + 13 + key_w, y0 + 9), str(v), font=font, fill=color)


def _draw_action_panel(draw, box, plan, font, small_font, reveal_mode: str = "FULL"):
    if not SHOW_ACTION_PANEL:
        return

    reveal_mode = _normalize_reveal_mode(reveal_mode)

    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=(244, 248, 252), outline=(220, 228, 238), width=2)

    if reveal_mode == "FULL":
        items = [
            ("BUY ZONE", f"{plan['buy_low']:,.0f} - {plan['buy_high']:,.0f}", GREEN),
            ("SELL / TARGET", f"{plan['target_1']:,.0f}", AMBER),
            ("STOP LOSS", f"{plan['stop_loss']:,.0f}", RED),
            ("SETUP", f"{plan['setup_grade']} | R:R 1:{plan['risk_reward']:.1f}", plan['decision_color']),
        ]
    elif reveal_mode == "BUY_LINE_ONLY":
        items = [
            ("BUY ZONE", f"{plan['buy_low']:,.0f} - {plan['buy_high']:,.0f}", GREEN),
            ("SELL / TARGET", "", AMBER),
            ("STOP LOSS", "", RED),
            ("SETUP", "", plan['decision_color']),
        ]
    elif reveal_mode == "BUY_TARGET_LINES":
        items = [
            ("BUY ZONE", f"{plan['buy_low']:,.0f} - {plan['buy_high']:,.0f}", GREEN),
            ("SELL / TARGET", f"{plan['target_1']:,.0f}", AMBER),
            ("STOP LOSS", "", RED),
            ("SETUP", "", plan['decision_color']),
        ]
    elif reveal_mode == "BUY_TARGET_SL_LINES":
        items = [
            ("BUY ZONE", f"{plan['buy_low']:,.0f} - {plan['buy_high']:,.0f}", GREEN),
            ("SELL / TARGET", f"{plan['target_1']:,.0f}", AMBER),
            ("STOP LOSS", f"{plan['stop_loss']:,.0f}", RED),
            ("SETUP", "", plan['decision_color']),
        ]
    elif reveal_mode == "HEADINGS_ONLY":
        items = [
            ("BUY ZONE", "", GREEN),
            ("SELL / TARGET", "", AMBER),
            ("STOP LOSS", "", RED),
            ("SETUP", "", plan['decision_color']),
        ]
    else:
        items = [
            ("BUY ZONE", "", GREEN),
            ("SELL / TARGET", "", AMBER),
            ("STOP LOSS", "", RED),
            ("SETUP", "", plan['decision_color']),
        ]

    gap = 10
    item_w = int((x1 - x0 - gap * 5) / 4)
    cy = y0 + 8
    for i, (label, value, color) in enumerate(items):
        ix0 = x0 + gap + i * (item_w + gap)
        ix1 = ix0 + item_w
        draw.rounded_rectangle([ix0, cy, ix1, y1 - 8], radius=14, fill=(255, 255, 255), outline=(230, 235, 242), width=1)
        tw = draw.textlength(label, font=small_font)
        draw.text((ix0 + (item_w - tw) / 2, cy + 6), label, font=small_font, fill=TEXT_MUTED)
        vw = draw.textlength(value, font=font)
        draw.text((ix0 + (item_w - vw) / 2, cy + 28), value, font=font, fill=color)

def _format_rupee(value) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except Exception:
        return str(value)


def _get_rsi_label(rsi_value: float) -> str:
    try:
        rsi = float(rsi_value)
    except Exception:
        return "RSI N/A"
    if rsi >= 70:
        return "RSI High"
    if rsi <= 30:
        return "RSI Low"
    if rsi >= 60:
        return "RSI Strong"
    if rsi <= 40:
        return "RSI Weak"
    return "RSI Neutral"


# =========================================================
# IMAGE CREATION
# =========================================================
def create_technical_chart_image(stock_row: dict, out_path: str, image_mode: str, reveal_mode: str = "FULL"):
    symbol = _safe_symbol(stock_row.get("Symbol", ""))
    underlying = str(stock_row.get("UnderlyingScrip", "")).strip()
    segment = str(stock_row.get("Segment", "")).strip()

    df = simulate_ohlcv(symbol, stock_row=stock_row)
    summary = get_signal_summary(df)
    plan = get_trade_plan(df)
    reveal_mode = _normalize_reveal_mode(reveal_mode)

    cfg = _get_image_layout(image_mode)
    W, H = cfg["size"]
    img = Image.new("RGB", (W, H), NAVY_TOP)
    _draw_vertical_gradient(img)
    _add_vignette(img, strength=0.40)
    draw = ImageDraw.Draw(img)

    f_label = _load_font(cfg["label_font"], bold=True)
    f_small = _load_font(cfg["small_font"], bold=False)
    f_footer = _load_font(cfg["footer_font"], bold=True)

    stock_name = _get_stock_display_name(symbol, stock_row)
    title = f"{stock_name}"
    source = str(df.get("DataSource", pd.Series(["Chart"])).iloc[-1]) if "DataSource" in df.columns else "Chart"
    subtitle = f"{TRADE_STYLE.title()} Setup Based on {CHART_TIMEFRAME} Data | {SUBTITLE_SUFFIX}"

    f_title = _fit_font_to_width(
        draw,
        title,
        int(W * TITLE_MAX_WIDTH_PCT),
        cfg["title_font"],
        bold=True,
        min_size=max(28, int(cfg["title_font"] * 0.62)),
    )
    f_subtitle = _fit_font_to_width(
        draw,
        subtitle,
        int(W * SUBTITLE_MAX_WIDTH_PCT),
        cfg["subtitle_font"],
        bold=True,
        min_size=max(18, int(cfg["subtitle_font"] * 0.70)),
    )

    _center(draw, W, title, cfg["title_y"], f_title, GOLD)
    subtitle_y = cfg["title_y"] + int(f_title.size * 0.95)
    _center(draw, W, subtitle, subtitle_y, f_subtitle, (210, 220, 235))

    validity_text = _get_validity_text()
    validity_bottom_y = subtitle_y
    if validity_text:
        f_validity = _fit_font_to_width(
            draw,
            validity_text,
            int(W * 0.55),
            cfg.get("validity_font", cfg["small_font"]),
            bold=True,
            min_size=max(12, int(cfg.get("validity_font", cfg["small_font"]) * 0.72)),
        )
        validity_y = subtitle_y + int(f_subtitle.size * 1.18) + int(cfg.get("validity_y_shift", 0))
        tw = draw.textlength(validity_text, font=f_validity)
        badge_w = int(tw + 28)
        badge_h = int(f_validity.size + 14)
        bx0 = int((W - badge_w) / 2)
        by0 = int(validity_y)
        draw.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h], radius=14, fill=(244, 248, 252), outline=(220, 228, 238), width=2)
        draw.text((bx0 + 14, by0 + 6), validity_text, font=f_validity, fill=RED)
        validity_bottom_y = by0 + badge_h

    card_left = cfg["card_side_pad"]
    card_right = W - cfg["card_side_pad"]
    card_top = max(cfg["card_top"], int(validity_bottom_y + 16))
    card_bottom = H - cfg["card_bottom_margin"]
    _rounded_shadow_card(img, [card_left, card_top, card_right, card_bottom], radius=30)
    draw = ImageDraw.Draw(img)

    inner = cfg["inner_pad"]
    x0 = card_left + inner
    x1 = card_right - inner
    y = card_top + inner
    card_h = card_bottom - card_top - (inner * 2)

    if SHOW_SIGNAL_BADGES:
        _draw_badges(draw, (x0, y, x1, y + 48), summary, f_label, f_small)
        y += 48 + 12

    if SHOW_ACTION_PANEL:
        _draw_action_panel(draw, (x0, y, x1, y + 70), plan, f_label, f_small, reveal_mode=reveal_mode)
        y += 70 + CHART_TOP_GAP

    remaining_h = card_bottom - inner - y
    gap_total = SECTION_GAP * 2
    price_h = int((remaining_h - gap_total) * PRICE_CHART_HEIGHT_RATIO)
    vol_h = int((remaining_h - gap_total) * VOLUME_CHART_HEIGHT_RATIO)
    rsi_h = max(95, remaining_h - gap_total - price_h - vol_h)

    price_box = (x0, y, x1, y + price_h)
    _draw_panel(draw, price_box, "Price Action + EMA + Support / Resistance", f_label)
    _draw_candles(draw, df, price_box, f_small, plan=plan, reveal_mode=reveal_mode)
    y += price_h + SECTION_GAP

    if SHOW_VOLUME:
        vol_box = (x0, y, x1, y + vol_h)
        _draw_panel(draw, vol_box, "Volume", f_label)
        _draw_volume(draw, df, vol_box, f_small)
        y += vol_h + SECTION_GAP

    if SHOW_RSI:
        rsi_box = (x0, y, x1, y + rsi_h)
        _draw_panel(draw, rsi_box, "RSI Momentum", f_label)
        _draw_rsi(draw, df, rsi_box, f_small)

    disclaimer = "Technical levels are data-based visual estimates only. Not investment advice."
    dw = draw.textlength(disclaimer, font=f_small)
    draw.text(((W - dw) / 2, card_bottom + 12), disclaimer, font=f_small, fill=(220, 226, 236))

    _center(draw, W, BRAND_HANDLE, H + cfg["handle_y"], f_footer, (235, 240, 245))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, quality=94)
    return out_path

def _summary_format_settings(image_mode: str):
    """Returns per-format boost and shifts for summary card."""
    m = str(image_mode).lower().strip()
    if m == "instagram":
        return {
            "font_boost": INSTAGRAM_SUMMARY_FONT_SIZE_BOOST,
            "title_shift": INSTAGRAM_SUMMARY_TITLE_Y_SHIFT,
            "card_shift": INSTAGRAM_SUMMARY_CARD_Y_SHIFT,
            "footer_shift": INSTAGRAM_SUMMARY_FOOTER_Y_SHIFT,
        }
    if m == "standard":
        return {
            "font_boost": STANDARD_SUMMARY_FONT_SIZE_BOOST,
            "title_shift": STANDARD_SUMMARY_TITLE_Y_SHIFT,
            "card_shift": STANDARD_SUMMARY_CARD_Y_SHIFT,
            "footer_shift": STANDARD_SUMMARY_FOOTER_Y_SHIFT,
        }
    if m == "reels":
        return {
            "font_boost": REELS_SUMMARY_FONT_SIZE_BOOST,
            "title_shift": REELS_SUMMARY_TITLE_Y_SHIFT,
            "card_shift": REELS_SUMMARY_CARD_Y_SHIFT,
            "footer_shift": REELS_SUMMARY_FOOTER_Y_SHIFT,
        }
    return {
        "font_boost": GENERAL_SUMMARY_FONT_SIZE_BOOST,
        "title_shift": GENERAL_SUMMARY_TITLE_Y_SHIFT,
        "card_shift": GENERAL_SUMMARY_CARD_Y_SHIFT,
        "footer_shift": GENERAL_SUMMARY_FOOTER_Y_SHIFT,
    }


def create_summary_card(stock_row: dict, out_path: str, image_mode: str = "standard"):
    symbol = _safe_symbol(stock_row.get("Symbol", ""))
    stock_name = _get_stock_display_name(symbol, stock_row)

    df = simulate_ohlcv(symbol, stock_row=stock_row)
    summary = get_signal_summary(df)
    plan = get_trade_plan(df)

    cfg = _get_image_layout(image_mode)
    fmt = _summary_format_settings(image_mode)
    W, H = cfg["size"]

    img = Image.new("RGB", (W, H), NAVY_TOP)
    _draw_vertical_gradient(img)
    _add_vignette(img, strength=0.40)
    draw = ImageDraw.Draw(img)

    # Responsive base scale + format-specific boost.
    scale = min(W / 1600, H / 900)
    font_boost = int(fmt["font_boost"])

    title_size = max(28, int(SUMMARY_TITLE_FONT_SIZE * scale) + font_boost)
    subtitle_size = max(18, int(SUMMARY_SUBTITLE_FONT_SIZE * scale) + font_boost)
    label_size = max(13, int(SUMMARY_ROW_LABEL_FONT_SIZE * scale) + font_boost)
    value_size = max(20, int(SUMMARY_ROW_VALUE_FONT_SIZE * scale) + font_boost)
    setup_value_size = max(19, int(SUMMARY_SETUP_VALUE_FONT_SIZE * scale) + font_boost)
    disclaimer_size = max(11, int(SUMMARY_DISCLAIMER_FONT_SIZE * scale) + font_boost)
    footer_size = max(18, int(SUMMARY_FOOTER_FONT_SIZE * scale) + font_boost)

    setup_text = f"{TRADE_STYLE.title()} Setup | {SUBTITLE_SUFFIX}" if SUBTITLE_SUFFIX else f"{TRADE_STYLE.title()} Setup"

    f_title = _fit_font_to_width(
        draw,
        stock_name,
        int(W * SUMMARY_TITLE_MAX_WIDTH_PCT),
        title_size,
        bold=True,
        min_size=max(22, int(title_size * 0.60)),
    )
    f_subtitle = _fit_font_to_width(
        draw,
        setup_text,
        int(W * SUMMARY_SUBTITLE_MAX_WIDTH_PCT),
        subtitle_size,
        bold=True,
        min_size=max(14, int(subtitle_size * 0.70)),
    )
    f_label = _load_font(label_size, bold=False)
    f_footer = _load_font(footer_size, bold=True)
    f_disclaimer = _load_font(disclaimer_size, bold=False)

    # Title and subtitle Y buttons.
    title_y = max(28, int(H * 0.07) + SUMMARY_TITLE_Y_SHIFT + int(fmt["title_shift"]))
    subtitle_y = title_y + int(f_title.size * 0.95) + SUMMARY_SUBTITLE_Y_SHIFT
    _center(draw, W, stock_name, title_y, f_title, GOLD)
    _center(draw, W, setup_text, subtitle_y, f_subtitle, (210, 220, 235))

    validity_text = _get_validity_text()
    validity_bottom_y = subtitle_y
    if validity_text:
        validity_font_size = max(12, int(cfg.get("validity_font", cfg["small_font"]) * max(0.85, scale)))
        f_validity = _fit_font_to_width(
            draw,
            validity_text,
            int(W * 0.55),
            validity_font_size,
            bold=True,
            min_size=11,
        )
        validity_y = subtitle_y + int(f_subtitle.size * 1.18) + int(cfg.get("validity_y_shift", 0))
        tw = draw.textlength(validity_text, font=f_validity)
        badge_w = int(tw + 28)
        badge_h = int(f_validity.size + 14)
        bx0 = int((W - badge_w) / 2)
        by0 = int(validity_y)
        draw.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h], radius=14, fill=(244, 248, 252), outline=(220, 228, 238), width=2)
        draw.text((bx0 + 14, by0 + 6), validity_text, font=f_validity, fill=RED)
        validity_bottom_y = by0 + badge_h

    # Card geometry: default uses available space more aggressively for readability.
    card_width = int(W * SUMMARY_CARD_WIDTH_PCT)
    card_left = int((W - card_width) / 2)
    card_right = W - card_left
    card_top = max(
        int(H * SUMMARY_CARD_TOP_PCT),
        int(validity_bottom_y + 16),
    ) + SUMMARY_CARD_Y_SHIFT + int(fmt["card_shift"])
    card_bottom = H - max(75, int(H * SUMMARY_CARD_BOTTOM_PCT)) + SUMMARY_CARD_Y_SHIFT + int(fmt["card_shift"])

    # Keep card safely inside canvas.
    card_top = max(110, card_top)
    card_bottom = min(H - 80, card_bottom)
    if card_bottom - card_top < int(H * 0.58):
        card_bottom = min(H - 80, card_top + int(H * 0.62))

    _rounded_shadow_card(img, [card_left, card_top, card_right, card_bottom], radius=max(22, int(32 * scale)))
    draw = ImageDraw.Draw(img)

    x0 = card_left + max(26, int(W * SUMMARY_CARD_INNER_X_PCT))
    x1 = card_right - max(26, int(W * SUMMARY_CARD_INNER_X_PCT))
    y0 = card_top + max(24, int(H * SUMMARY_CARD_INNER_Y_PCT))
    y1 = card_bottom - max(24, int(H * SUMMARY_CARD_INNER_Y_PCT))

    rows = [
        ("SETUP", f"{plan['setup_grade']} | {summary['trend']} | {summary['action']}", plan['decision_color'], setup_value_size),
        ("BUY ZONE", f"{_format_rupee(plan['buy_low'])} – {_format_rupee(plan['buy_high'])}", GREEN, value_size),
        ("TARGET / SL", f"Target: {_format_rupee(plan['target_1'])}   |   SL: {_format_rupee(plan['stop_loss'])}", AMBER, value_size),
        ("RISK-REWARD", f"R:R 1:{plan['risk_reward']:.1f}   |   {_get_rsi_label(summary['rsi'])}   |   RSI {summary['rsi']:.1f}", PURPLE, value_size),
        ("CMP / 1D CHANGE", f"CMP: {_format_rupee(summary['close'])}   |   1D: {summary['change_pct']:+.2f}%", GREEN if summary['change_pct'] >= 0 else RED, value_size),
    ]

    row_gap = max(8, int(SUMMARY_ROW_GAP * scale))
    row_h = int((y1 - y0 - row_gap * (len(rows) - 1)) / len(rows))
    row_h = max(row_h, int(88 * scale))

    label_x_pad = max(14, int(SUMMARY_ROW_LABEL_X_PAD * scale))
    value_x_pad = max(14, int(SUMMARY_ROW_VALUE_X_PAD * scale))
    label_y_pad = max(8, int(SUMMARY_ROW_LABEL_Y_PAD * scale))
    value_y_pad = max(34, int(SUMMARY_ROW_VALUE_Y_PAD * scale))

    for idx, (label, value, color, start_size) in enumerate(rows):
        ry0 = y0 + idx * (row_h + row_gap)
        ry1 = min(ry0 + row_h, y1)
        draw.rounded_rectangle(
            [x0, ry0, x1, ry1],
            radius=max(14, int(SUMMARY_ROW_RADIUS * scale)),
            fill=(248, 251, 255),
            outline=(218, 226, 238),
            width=2,
        )
        draw.text((x0 + label_x_pad, ry0 + label_y_pad), label, font=f_label, fill=TEXT_MUTED)

        val_font = _fit_font_to_width(
            draw,
            value,
            int((x1 - x0) * SUMMARY_VALUE_MAX_WIDTH_PCT),
            start_size,
            bold=True,
            min_size=max(16, int(start_size * 0.55)),
        )
        value_y = ry0 + value_y_pad
        # If row is shorter in any format, center value vertically instead of crowding label.
        if value_y + val_font.size > ry1 - 8:
            value_y = ry0 + int((row_h - val_font.size) * 0.58)
        draw.text((x0 + value_x_pad, value_y), value, font=val_font, fill=color)

    disclaimer = "Technical levels are data-based visual estimates only. Not investment advice."
    dw = draw.textlength(disclaimer, font=f_disclaimer)
    disclaimer_y = card_bottom + max(8, int(14 * scale)) + SUMMARY_DISCLAIMER_Y_SHIFT
    draw.text(((W - dw) / 2, disclaimer_y), disclaimer, font=f_disclaimer, fill=(220, 226, 236))

    footer_y = H + cfg["handle_y"] + SUMMARY_FOOTER_Y_SHIFT + int(fmt["footer_shift"])
    _center(draw, W, BRAND_HANDLE, footer_y, f_footer, (235, 240, 245))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, quality=94)
    return out_path


# =========================================================
# INPUT LOADER
# =========================================================
def _is_supported_stock_input_file(path: str) -> bool:
    ext = os.path.splitext(str(path))[1].lower()
    return ext in [".csv", ".xlsx", ".xls"]


def get_input_stock_files(input_path: str) -> list[str]:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"INPUT_STOCKS path not found: {input_path}")

    if os.path.isfile(input_path):
        if not _is_supported_stock_input_file(input_path):
            raise ValueError("INPUT_STOCKS file must be a .csv, .xlsx, or .xls file")
        return [input_path]

    if os.path.isdir(input_path):
        files = []
        for name in sorted(os.listdir(input_path)):
            if name.startswith("~$"):
                continue
            full_path = os.path.join(input_path, name)
            if os.path.isfile(full_path) and _is_supported_stock_input_file(full_path):
                files.append(full_path)
        if not files:
            raise FileNotFoundError(
                f"No supported stock files (.csv/.xlsx/.xls) found inside folder: {input_path}"
            )
        return files

    raise ValueError("INPUT_STOCKS must be either a valid file path or a folder path")


def load_stock_list(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"INPUT_STOCKS file not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    # Supports both Excel and CSV inputs.
    # For Yahoo Finance chart generation, only Symbol is mandatory.
    # UnderlyingScrip and Segment are kept as optional columns for compatibility
    # with other Dhan/NSE/live-data scripts that may use the same stock list.
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
    elif ext == ".csv":
        try:
            df = pd.read_csv(path)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="utf-8-sig")
    else:
        raise ValueError("INPUT_STOCKS must be a .csv, .xlsx, or .xls file")

    # Clean accidental leading/trailing spaces in column names.
    df.columns = [str(c).strip() for c in df.columns]

    required = ["Symbol"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in INPUT_STOCKS: {missing}. Only 'Symbol' is required for Yahoo Finance download.")

    optional_cols = []
    for col in ["UnderlyingScrip", "Segment"] + CURRENT_PRICE_COLUMNS + STOCK_NAME_COLUMNS:
        if col in df.columns and col not in optional_cols:
            optional_cols.append(col)

    keep_cols = required + optional_cols
    df = df[keep_cols].copy().dropna(subset=["Symbol"])
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()

    # Remove blank/nan symbols that can appear after Excel/CSV formatting.
    df = df[~df["Symbol"].isin(["", "NAN", "NONE", "NULL"])]
    df = df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)

    return df

# =========================================================
# MAIN
# =========================================================
def main():
    input_files = get_input_stock_files(INPUT_STOCKS)
    generated = []

    image_modes = []
    if GENERATE_GENERAL_IMAGE:
        image_modes.append("General")
    if GENERATE_STANDARD_IMAGE:
        image_modes.append("Standard")
    if GENERATE_INSTAGRAM_IMAGE:
        image_modes.append("Instagram")
    if GENERATE_REELS_IMAGE:
        image_modes.append("Reels")

    print(f"Found {len(input_files)} input stock file(s) to process.")

    for stock_file in input_files:
        _set_current_input_context(stock_file)
        batch_name = globals().get("CURRENT_INPUT_BATCH_NAME", "Default")
        print(f"\n{'=' * 90}")
        print(f"Processing stock list file: {stock_file}")
        print(f"Output batch folder     : {os.path.join('Images', _get_date_folder(), batch_name)}")
        print(f"{'=' * 90}")

        stocks = load_stock_list(stock_file)
        print(f"Total symbols found in {os.path.basename(stock_file)}: {len(stocks)}")

        for _, row in stocks.iterrows():
            stock_row = row.to_dict()
            symbol = _safe_symbol(stock_row["Symbol"])
            print(f"\nProcessing: {symbol}")
            for mode in image_modes:
                # Master/full chart image goes to Images/{DATE}/{INPUT_FILE}/Master/{IMAGE_TYPE}/{SYMBOL}.jpeg
                out_path = build_output_path(symbol, mode)
                generated.append(create_technical_chart_image(stock_row, out_path, mode.lower(), reveal_mode="FULL"))

                # Existing reveal images go to Images/{DATE}/{INPUT_FILE}/SubImages/{IMAGE_TYPE}/{SYMBOL}/
                if GENERATE_CHART_REVEAL_SEQUENCE:
                    for reveal_mode in CHART_REVEAL_MODES:
                        if str(reveal_mode).upper() == "FULL":
                            continue
                        reveal_out = build_chart_reveal_output_path(symbol, mode, reveal_mode)
                        generated.append(create_technical_chart_image(stock_row, reveal_out, mode.lower(), reveal_mode=reveal_mode))

                if GENERATE_ACTION_LINE_STEP_IMAGES:
                    for step_mode in ACTION_LINE_STEP_MODES:
                        step_out = build_action_line_step_output_path(symbol, mode, step_mode)
                        generated.append(create_technical_chart_image(stock_row, step_out, mode.lower(), reveal_mode=step_mode))

                if GENERATE_SUMMARY_CARD:
                    summary_out = build_summary_output_path(symbol, mode)
                    generated.append(create_summary_card(stock_row, summary_out, mode.lower()))

    print("\nGenerated files:")
    for p in generated:
        print(f"✅ {p}")


if __name__ == "__main__":
    main()
