import os
import math
import glob
from datetime import datetime

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================================================
# AIT PORTFOLIO ANALYSIS IMAGE GENERATOR - KPI CLEAN VERSION
# =========================================================
# Generates 4 image types from PortfolioAnalysisOutput:
# 1. Standard  - full desktop size: 1920 x 1080
# 2. General   - same size as Instagram/Reels
# 3. Instagram - same size as General/Reels
# 4. Reels     - same size as General/Instagram
#
# Input expected from PortfolioAnalyzer.py:
# PortfolioAnalysisOutput/Portfolio_Analysis_DD_MM_YYYY.xlsx
# or
# PortfolioAnalysisOutput/Portfolio_Analysis_DD_MM_YYYY.csv
# =========================================================

# =========================================================
# CONFIG
# =========================================================
PORTFOLIO_OUTPUT_DIR = r"PortfolioAnalysisOutput"

# Keep blank to auto-pick latest Portfolio_Analysis_*.xlsx/csv from PortfolioAnalysisOutput
INPUT_FILE = ""

DATE = ""  # dd/mm/yyyy | keep blank for today
BRAND_HANDLE = "automationintrade"
TITLE_PREFIX = "Portfolio Quality Scorecard"
SUBTITLE_TEXT = ""  # Removed subtitle for cleaner professional look
DISCLAIMER_TEXT = "Data-based score only. Not investment advice."

# Optional Indian flag near title
FLAG = r"./flags/in.png"
FLAG_SHOW = False
FLAG_MAX_HEIGHT = 38
FLAG_TITLE_GAP = 14
FLAG_X_SHIFT = -8
FLAG_Y_SHIFT = 0

# Sorting and filtering
SORT_BY = "AIT Score"
SORT_ASCENDING = False
TOP_N = None  # Example: 20 | None = all rows
MAX_ROWS_PER_PAGE = None

# =========================================================
# ELEMENT FONT + Y-AXIS CONTROL BUTTONS
# =========================================================
# Marked element mapping:
# 1 = Main title
# 2 = KPI summary cards
# 3 = Blue banner
# 4 = Main table
# 5 = Disclaimer
# 6 = Brand handle/footer
#
# Use these buttons first when tuning the image. The older detailed
# font variables below are still kept for compatibility, but these
# element-level buttons are used by the renderer.

# ---------- SOCIAL IMAGES: General / Instagram / Reels ----------
SOCIAL_BOX_1_TITLE_FONT_SIZE = 58

SOCIAL_BOX_2_KPI_TITLE_FONT_SIZE = 22
SOCIAL_BOX_2_KPI_VALUE_FONT_SIZE = 31
SOCIAL_BOX_2_KPI_META_FONT_SIZE = 21
SOCIAL_BOX_2_KPI_Y_SHIFT = 0       # move KPI box up/down

SOCIAL_BOX_3_BANNER_FONT_SIZE = 30

SOCIAL_BOX_4_TABLE_HEADER_FONT_SIZE = 21
SOCIAL_BOX_4_TABLE_CELL_FONT_SIZE = 22
SOCIAL_BOX_4_TABLE_CELL_BOLD_FONT_SIZE = 22

SOCIAL_BOX_5_DISCLAIMER_FONT_SIZE = 19
SOCIAL_BOX_5_DISCLAIMER_Y_SHIFT = 0  # move disclaimer up/down

SOCIAL_BOX_6_HANDLE_FONT_SIZE = 28
SOCIAL_BOX_6_HANDLE_Y_SHIFT = 0      # move brand handle up/down

# ---------- STANDARD IMAGE: Desktop ----------
STANDARD_BOX_1_TITLE_FONT_SIZE = 50

STANDARD_BOX_2_KPI_TITLE_FONT_SIZE = 18
STANDARD_BOX_2_KPI_VALUE_FONT_SIZE = 28
STANDARD_BOX_2_KPI_META_FONT_SIZE = 18
STANDARD_BOX_2_KPI_Y_SHIFT = 0       # move KPI box up/down

STANDARD_BOX_3_BANNER_FONT_SIZE = 27

STANDARD_BOX_4_TABLE_HEADER_FONT_SIZE = 17
STANDARD_BOX_4_TABLE_CELL_FONT_SIZE = 17
STANDARD_BOX_4_TABLE_CELL_BOLD_FONT_SIZE = 17

STANDARD_BOX_5_DISCLAIMER_FONT_SIZE = 15
STANDARD_BOX_5_DISCLAIMER_Y_SHIFT = 0  # move disclaimer up/down

STANDARD_BOX_6_HANDLE_FONT_SIZE = 22
STANDARD_BOX_6_HANDLE_Y_SHIFT = 0      # move brand handle up/down

# Output templates
GENERAL_IMAGE_OUTPUT_TEMPLATE = r"PortfolioAnalysisOutput/Images/{DATE_FOLDER}/General/Portfolio_Analysis.jpeg"
INSTAGRAM_IMAGE_OUTPUT_TEMPLATE = r"PortfolioAnalysisOutput/Images/{DATE_FOLDER}/Instagram/Portfolio_Analysis.jpeg"
REELS_IMAGE_OUTPUT_TEMPLATE = r"PortfolioAnalysisOutput/Images/{DATE_FOLDER}/Reels/Portfolio_Analysis.jpeg"
STANDARD_IMAGE_OUTPUT_TEMPLATE = r"PortfolioAnalysisOutput/Images/{DATE_FOLDER}/Standard/Portfolio_Analysis.jpeg"

GENERATE_GENERAL_IMAGE = True
GENERATE_INSTAGRAM_IMAGE = True
GENERATE_REELS_IMAGE = True
GENERATE_STANDARD_IMAGE = True

# =========================================================
# SHARED SOCIAL IMAGE BUTTONS
# General, Instagram and Reels intentionally use identical dimensions.
# =========================================================
SOCIAL_WIDTH = 1280
SOCIAL_HEIGHT = 1600

SOCIAL_TITLE_Y = 70
SOCIAL_SUBTITLE_Y = 0
SOCIAL_CARD_TOP = 155
SOCIAL_SIDE_PAD = 58
SOCIAL_INNER_PAD = 28
SOCIAL_BOTTOM_MARGIN = 116
SOCIAL_HANDLE_Y = -74

SOCIAL_TITLE_FONT_SIZE = 58
SOCIAL_SUBTITLE_FONT_SIZE = 25
SOCIAL_META_FONT_SIZE = 21
SOCIAL_SUMMARY_TITLE_FONT_SIZE = 22
SOCIAL_SUMMARY_VALUE_FONT_SIZE = 31
SOCIAL_BANNER_FONT_SIZE = 30
SOCIAL_HEADER_FONT_SIZE = 21
SOCIAL_CELL_FONT_SIZE = 22
SOCIAL_CELL_BOLD_FONT_SIZE = 22
SOCIAL_FOOTER_FONT_SIZE = 28
SOCIAL_DISCLAIMER_FONT_SIZE = 19

SOCIAL_SUMMARY_H = 108
SOCIAL_BANNER_H = 74
SOCIAL_GAP_AFTER_SUMMARY = 20
SOCIAL_GAP_AFTER_BANNER = 18
SOCIAL_HEADER_H = 66
SOCIAL_ROW_H = 70

# =========================================================
# STANDARD IMAGE BUTTONS - FULL DESKTOP SIZE
# =========================================================
STANDARD_WIDTH = 1920
STANDARD_HEIGHT = 1080

STANDARD_TITLE_Y = 48
STANDARD_SUBTITLE_Y = 0
STANDARD_CARD_TOP = 122
STANDARD_SIDE_PAD = 70
STANDARD_INNER_PAD = 26
STANDARD_BOTTOM_MARGIN = 66
STANDARD_HANDLE_Y = -44

STANDARD_TITLE_FONT_SIZE = 50
STANDARD_SUBTITLE_FONT_SIZE = 21
STANDARD_META_FONT_SIZE = 18
STANDARD_SUMMARY_TITLE_FONT_SIZE = 18
STANDARD_SUMMARY_VALUE_FONT_SIZE = 28
STANDARD_BANNER_FONT_SIZE = 27
STANDARD_HEADER_FONT_SIZE = 17
STANDARD_CELL_FONT_SIZE = 17
STANDARD_CELL_BOLD_FONT_SIZE = 17
STANDARD_FOOTER_FONT_SIZE = 22
STANDARD_DISCLAIMER_FONT_SIZE = 15

STANDARD_SUMMARY_H = 86
STANDARD_BANNER_H = 62
STANDARD_GAP_AFTER_SUMMARY = 16
STANDARD_GAP_AFTER_BANNER = 14
STANDARD_HEADER_H = 54
STANDARD_ROW_H = 49

# =========================================================
# COLORS
# =========================================================
NAVY_TOP = (7, 18, 35)
NAVY_MID = (9, 32, 58)
NAVY_BOT = (4, 11, 23)
CARD_FILL = (252, 254, 255)
CARD_OUTLINE = (79, 113, 152)
HEADER_BG = (231, 237, 246)
GRID = (225, 232, 241)
GOLD = (247, 198, 58)
WHITE = (248, 250, 252)
TEXT_DARK = (19, 30, 48)
TEXT_MUTED = (88, 103, 122)
GREEN = (21, 135, 83)
RED = (202, 49, 52)
ORANGE = (194, 116, 31)
BLUE = (42, 106, 171)
CYAN = (25, 131, 160)
PURPLE = (109, 84, 170)
SOFT_GREEN = (219, 245, 235)
SOFT_RED = (255, 227, 227)
SOFT_ORANGE = (255, 241, 219)
SOFT_BLUE = (224, 238, 252)
SOFT_PURPLE = (236, 231, 249)

# =========================================================
# BASIC HELPERS
# =========================================================
def _get_date_folder() -> str:
    date_value = str(DATE or "").strip()
    if date_value:
        try:
            return datetime.strptime(date_value, "%d/%m/%Y").strftime("%d_%m_%Y")
        except Exception:
            pass
    return datetime.now().strftime("%d_%m_%Y")


def _get_report_date_text() -> str:
    date_value = str(DATE or "").strip()
    if date_value:
        try:
            return datetime.strptime(date_value, "%d/%m/%Y").strftime("%d %B %Y")
        except Exception:
            pass
    return datetime.now().strftime("%d %B %Y")


def build_output_path(template: str, page_no: int = 1) -> str:
    path = template.replace("{DATE_FOLDER}", _get_date_folder())
    root, ext = os.path.splitext(path)
    if page_no > 1:
        path = f"{root}_{page_no}{ext}"
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
                os.path.join(win_dir, "segoeuib.ttf"),
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
            if p and os.path.exists(p):
                return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _to_float(v):
    try:
        if pd.isna(v):
            return None
        s = str(v).strip()
        if not s or s.lower() in ["nan", "none", "null", "-"]:
            return None
        s = s.replace(",", "").replace("−", "-").replace("%", "")
        return float(s)
    except Exception:
        return None


def _fmt_num(v, decimals=2):
    x = _to_float(v)
    if x is None:
        return "-"
    return f"{x:,.{decimals}f}"


def _fmt_score(v):
    x = _to_float(v)
    if x is None:
        return "-"
    return f"{x:.1f}"


def _clean_text(v):
    if v is None or pd.isna(v):
        return "-"
    text = str(v).strip()
    return text if text else "-"


def _short_stock_name(name: str, max_chars: int = 24) -> str:
    text = _clean_text(name)

    replacements = {
        " limited": " ltd",
        " private": " pvt",
        " company": " co",
        " industries": " ind",
        " corporation": " corp",
        " financial": " fin",
    }

    text = " ".join(str(text).strip().split()).lower()
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.title()

    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _wrap_text(draw, text: str, font, max_width: int):
    text = _clean_text(text)
    words = text.split()
    lines = []
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _center(draw, width, text, y, font, fill):
    tw = draw.textlength(text, font=font)
    draw.text(((width - tw) / 2, y), text, font=font, fill=fill)


def _draw_background(img):
    w, h = img.size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.5:
            tt = t / 0.5
            c1, c2 = NAVY_TOP, NAVY_MID
        else:
            tt = (t - 0.5) / 0.5
            c1, c2 = NAVY_MID, NAVY_BOT
        r = int(c1[0] + (c2[0] - c1[0]) * tt)
        g = int(c1[1] + (c2[1] - c1[1]) * tt)
        b = int(c1[2] + (c2[2] - c1[2]) * tt)
        for x in range(w):
            px[x, y] = (r, g, b)
    img.paste(grad, (0, 0))

    # subtle center glow
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(w * 0.18), int(h * 0.05), int(w * 0.82), int(h * 0.72)], fill=(29, 95, 155, 48))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=int(min(w, h) * 0.10)))
    img.paste(glow, (0, 0), glow)

    # vignette
    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    margin = int(min(w, h) * 0.10)
    vd.ellipse([margin, margin, w - margin, h - margin], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=int(min(w, h) * 0.08)))
    inv = Image.eval(vignette, lambda p: 255 - p)
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    img.paste(overlay, (0, 0), Image.eval(inv, lambda p: int(p * 0.38)))


def _rounded_shadow_card(base_img, box, radius=30, shadow_offset=(0, 14), shadow_blur=22,
                         shadow_color=(0, 0, 0, 120), fill=CARD_FILL,
                         outline=CARD_OUTLINE, outline_w=3):
    l, t, r, b = box
    w = r - l
    h = b - t

    shadow = Image.new("RGBA", (w + shadow_blur * 4, h + shadow_blur * 4), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [shadow_blur * 2, shadow_blur * 2, shadow_blur * 2 + w, shadow_blur * 2 + h],
        radius=radius,
        fill=shadow_color,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    base_img.paste(shadow, (l + shadow_offset[0] - shadow_blur * 2, t + shadow_offset[1] - shadow_blur * 2), shadow)

    layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([l, t, r, b], radius=radius, fill=fill, outline=outline, width=outline_w)
    d.rounded_rectangle([l + 7, t + 7, r - 7, b - 7], radius=max(5, radius - 7), outline=(218, 226, 237), width=2)
    base_img.paste(layer, (0, 0), layer)


def _paste_flag_near_title(base_img, draw, title_text, title_y, title_font):
    if not FLAG_SHOW:
        return
    flag_path = str(FLAG or "").strip()
    if not flag_path or not os.path.exists(flag_path):
        return
    try:
        flag = Image.open(flag_path).convert("RGBA")
        ratio = FLAG_MAX_HEIGHT / float(flag.height)
        flag = flag.resize((max(1, int(flag.width * ratio)), max(1, int(flag.height * ratio))), Image.LANCZOS)
        title_w = draw.textlength(title_text, font=title_font)
        title_x = (base_img.size[0] - title_w) / 2
        flag_x = int(title_x - flag.width - FLAG_TITLE_GAP + FLAG_X_SHIFT)
        flag_y = int(title_y + (title_font.size - flag.height) / 2 + FLAG_Y_SHIFT)
        base_img.paste(flag, (flag_x, flag_y), flag)
    except Exception as e:
        print(f"⚠ Could not load/paste flag: {e}")

# =========================================================
# INPUT LOADING
# =========================================================
def find_latest_input_file():
    if INPUT_FILE and os.path.exists(INPUT_FILE):
        return INPUT_FILE
    patterns = [
        os.path.join(PORTFOLIO_OUTPUT_DIR, "Portfolio_Analysis_*.xlsx"),
        os.path.join(PORTFOLIO_OUTPUT_DIR, "Portfolio_Analysis_*.csv"),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No Portfolio_Analysis_*.xlsx/csv found inside: {PORTFOLIO_OUTPUT_DIR}\n"
            f"Run PortfolioAnalyzer.py first, or set INPUT_FILE manually."
        )
    return sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)[0]


def load_portfolio_data():
    input_path = find_latest_input_file()
    print(f"Input file: {input_path}")
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".xlsx":
        df = pd.read_excel(input_path)
    elif ext == ".csv":
        df = pd.read_csv(input_path)
    else:
        raise ValueError(f"Unsupported input file type: {ext}")
    df = df.copy().dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    if SORT_BY in df.columns:
        df[SORT_BY] = pd.to_numeric(df[SORT_BY], errors="coerce")
        df = df.sort_values(by=SORT_BY, ascending=SORT_ASCENDING)
    if TOP_N is not None:
        df = df.head(int(TOP_N))
    return df.reset_index(drop=True)

# =========================================================
# LAYOUT AND COLUMNS
# =========================================================
def get_layout(mode: str):
    if str(mode).lower() == "standard":
        return {
            "size": (STANDARD_WIDTH, STANDARD_HEIGHT),
            "title_y": STANDARD_TITLE_Y,
            "subtitle_y": STANDARD_SUBTITLE_Y,
            "card_top": STANDARD_CARD_TOP,
            "side_pad": STANDARD_SIDE_PAD,
            "inner_pad": STANDARD_INNER_PAD,
            "bottom_margin": STANDARD_BOTTOM_MARGIN,
            "handle_y": STANDARD_HANDLE_Y,
            "kpi_y_shift": STANDARD_BOX_2_KPI_Y_SHIFT,
            "disclaimer_y_shift": STANDARD_BOX_5_DISCLAIMER_Y_SHIFT,
            "handle_y_shift": STANDARD_BOX_6_HANDLE_Y_SHIFT,
            "summary_h": STANDARD_SUMMARY_H,
            "banner_h": STANDARD_BANNER_H,
            "gap_after_summary": STANDARD_GAP_AFTER_SUMMARY,
            "gap_after_banner": STANDARD_GAP_AFTER_BANNER,
            "header_h": STANDARD_HEADER_H,
            "row_h": STANDARD_ROW_H,
            "title_font": STANDARD_BOX_1_TITLE_FONT_SIZE,
            "subtitle_font": STANDARD_SUBTITLE_FONT_SIZE,
            "meta_font": STANDARD_BOX_2_KPI_META_FONT_SIZE,
            "summary_title_font": STANDARD_BOX_2_KPI_TITLE_FONT_SIZE,
            "summary_value_font": STANDARD_BOX_2_KPI_VALUE_FONT_SIZE,
            "banner_font": STANDARD_BOX_3_BANNER_FONT_SIZE,
            "header_font": STANDARD_BOX_4_TABLE_HEADER_FONT_SIZE,
            "cell_font": STANDARD_BOX_4_TABLE_CELL_FONT_SIZE,
            "cell_bold_font": STANDARD_BOX_4_TABLE_CELL_BOLD_FONT_SIZE,
            "footer_font": STANDARD_BOX_6_HANDLE_FONT_SIZE,
            "disclaimer_font": STANDARD_BOX_5_DISCLAIMER_FONT_SIZE,
        }
    return {
        "size": (SOCIAL_WIDTH, SOCIAL_HEIGHT),
        "title_y": SOCIAL_TITLE_Y,
        "subtitle_y": SOCIAL_SUBTITLE_Y,
        "card_top": SOCIAL_CARD_TOP,
        "side_pad": SOCIAL_SIDE_PAD,
        "inner_pad": SOCIAL_INNER_PAD,
        "bottom_margin": SOCIAL_BOTTOM_MARGIN,
        "handle_y": SOCIAL_HANDLE_Y,
        "kpi_y_shift": SOCIAL_BOX_2_KPI_Y_SHIFT,
        "disclaimer_y_shift": SOCIAL_BOX_5_DISCLAIMER_Y_SHIFT,
        "handle_y_shift": SOCIAL_BOX_6_HANDLE_Y_SHIFT,
        "summary_h": SOCIAL_SUMMARY_H,
        "banner_h": SOCIAL_BANNER_H,
        "gap_after_summary": SOCIAL_GAP_AFTER_SUMMARY,
        "gap_after_banner": SOCIAL_GAP_AFTER_BANNER,
        "header_h": SOCIAL_HEADER_H,
        "row_h": SOCIAL_ROW_H,
        "title_font": SOCIAL_BOX_1_TITLE_FONT_SIZE,
        "subtitle_font": SOCIAL_SUBTITLE_FONT_SIZE,
        "meta_font": SOCIAL_BOX_2_KPI_META_FONT_SIZE,
        "summary_title_font": SOCIAL_BOX_2_KPI_TITLE_FONT_SIZE,
        "summary_value_font": SOCIAL_BOX_2_KPI_VALUE_FONT_SIZE,
        "banner_font": SOCIAL_BOX_3_BANNER_FONT_SIZE,
        "header_font": SOCIAL_BOX_4_TABLE_HEADER_FONT_SIZE,
        "cell_font": SOCIAL_BOX_4_TABLE_CELL_FONT_SIZE,
        "cell_bold_font": SOCIAL_BOX_4_TABLE_CELL_BOLD_FONT_SIZE,
        "footer_font": SOCIAL_BOX_6_HANDLE_FONT_SIZE,
        "disclaimer_font": SOCIAL_BOX_5_DISCLAIMER_FONT_SIZE,
    }


def get_columns_for_mode(mode: str):
    """
    Clean professional table.
    Symbol column removed as requested, so the first visible column is Company.
    """
    if str(mode).lower() == "standard":
        return [
            ("Stock", "Company", 0.230, "stock"),
            ("CMP", "CMP", 0.075, "num"),
            ("AIT Score", "AIT Score", 0.080, "score"),
            ("Final Grade", "Grade", 0.060, "grade"),
            ("Quality Label", "Quality", 0.092, "label"),
            ("Growth Label", "Growth", 0.092, "label"),
            ("Valuation Label", "Value", 0.092, "label"),
            ("Upside Label", "Upside", 0.085, "label"),
            ("Risk Label", "Risk", 0.085, "risk"),
            ("Final View", "Quick Read", 0.214, "view"),
        ]
    return [
        ("Stock", "Company", 0.360, "stock"),
        ("AIT Score", "AIT Score", 0.125, "score"),
        ("Final Grade", "Grade", 0.085, "grade"),
        ("Quality Label", "Quality", 0.145, "label"),
        ("Growth Label", "Growth", 0.140, "label"),
        ("Risk Label", "Risk", 0.145, "risk"),
    ]

# =========================================================
# SCORE AND COLOR LOGIC
# =========================================================
def _score_color(value):
    x = _to_float(value)
    if x is None:
        return TEXT_MUTED, None
    if x >= 75:
        return GREEN, SOFT_GREEN
    if x >= 60:
        return BLUE, SOFT_BLUE
    if x >= 50:
        return ORANGE, SOFT_ORANGE
    return RED, SOFT_RED


def _grade_color(value):
    txt = _clean_text(value).upper()
    if txt in ["A+", "A"]:
        return GREEN, SOFT_GREEN
    if txt in ["B+", "B"]:
        return BLUE, SOFT_BLUE
    if txt == "C":
        return ORANGE, SOFT_ORANGE
    return RED, SOFT_RED


def _label_color(value, style="label"):
    txt = _clean_text(value).lower()
    if any(x in txt for x in ["excellent", "strong", "good"]):
        return GREEN, SOFT_GREEN
    if "average" in txt:
        return ORANGE, SOFT_ORANGE
    if any(x in txt for x in ["weak", "poor"]):
        return RED, SOFT_RED
    return TEXT_MUTED, None


def _cell_colors(style, value):
    if style == "score":
        return _score_color(value)
    if style == "grade":
        return _grade_color(value)
    if style in ["label", "risk"]:
        return _label_color(value, style)
    if style == "symbol":
        return BLUE, None
    if style == "view":
        return TEXT_MUTED, None
    return TEXT_DARK, None


def _format_cell(value, style):
    if style == "num":
        return _fmt_num(value, 2)
    if style == "score":
        return _fmt_score(value)
    return _clean_text(value)


def get_banner(df: pd.DataFrame):
    """
    Banner kept clean as requested:
    Example: 27 May 2026: Balanced Quality
    """
    date_text = _get_report_date_text()
    if df.empty or "AIT Score" not in df.columns:
        return f"{date_text}: Portfolio Snapshot", BLUE

    scores = pd.to_numeric(df["AIT Score"], errors="coerce").dropna()
    if scores.empty:
        return f"{date_text}: Portfolio Snapshot", BLUE

    avg = scores.mean()
    if avg >= 75:
        color = GREEN
        mood = "Strong Quality"
    elif avg >= 60:
        color = BLUE
        mood = "Balanced Quality"
    elif avg >= 50:
        color = ORANGE
        mood = "Mixed Quality"
    else:
        color = RED
        mood = "Weak Quality"

    return f"{date_text}: {mood}", color


def build_summary_cards(df: pd.DataFrame):
    scores = pd.to_numeric(df.get("AIT Score", pd.Series(dtype=float)), errors="coerce").dropna()
    total = len(scores)
    avg = scores.mean() if total else None
    strong = int((scores >= 75).sum()) if total else 0
    watch = int(((scores >= 60) & (scores < 75)).sum()) if total else 0
    weak = int((scores < 50).sum()) if total else 0

    best_stock = "-"
    best_score = "-"
    if total and "AIT Score" in df.columns:
        best_row = df.sort_values("AIT Score", ascending=False).iloc[0]
        best_stock = _clean_text(best_row.get("Symbol", "-"))
        best_score = _fmt_score(best_row.get("AIT Score", "-"))

    return [
        ("Avg AIT Score", _fmt_score(avg), "Portfolio score", BLUE, SOFT_BLUE),
        ("Strong", str(strong), f"out of {total}", GREEN, SOFT_GREEN),
        ("Watchlist", str(watch), "60-75 score", ORANGE, SOFT_ORANGE),
        ("Weak", str(weak), "below 50", RED, SOFT_RED),
        ("Best", best_stock, f"score {best_score}", PURPLE, SOFT_PURPLE),
    ]

# =========================================================
# DRAW HELPERS
# =========================================================
def _draw_text_lines(draw, text, x0, y0, x1, y1, font, fill, max_lines=2, center_vertical=True):
    max_w = int((x1 - x0) - 18)
    lines = _wrap_text(draw, text, font, max_w)[:max_lines]
    if not lines:
        lines = ["-"]
    line_h = font.size + 3
    total_h = len(lines) * line_h
    yy = y0 + ((y1 - y0) - total_h) / 2 if center_vertical else y0 + 8
    for ln in lines:
        draw.text((x0 + 10, yy), ln, font=font, fill=fill)
        yy += line_h


def _draw_badge(draw, box, text, font, fg, bg):
    x0, y0, x1, y1 = box
    if bg:
        draw.rounded_rectangle([x0 + 6, y0 + 10, x1 - 6, y1 - 10], radius=14, fill=bg)
    _draw_text_lines(draw, text, x0, y0, x1, y1, font, fg, max_lines=1)


def _draw_summary_cards(draw, cards, x0, y0, x1, h, f_title, f_value, f_meta):
    gap = 14
    n = len(cards)
    w = int((x1 - x0 - gap * (n - 1)) / n)
    for i, (title, value, meta, color, bg) in enumerate(cards):
        l = x0 + i * (w + gap)
        r = l + w
        draw.rounded_rectangle([l, y0, r, y0 + h], radius=20, fill=bg, outline=(214, 224, 236), width=1)
        draw.text((l + 18, y0 + 13), title, font=f_title, fill=TEXT_MUTED)
        # Shrink long best-symbol value
        val_font = f_value
        while draw.textlength(str(value), font=val_font) > (w - 36) and val_font.size > 16:
            val_font = _load_font(val_font.size - 2, bold=True)
        draw.text((l + 18, y0 + 38), str(value), font=val_font, fill=color)
        draw.text((l + 18, y0 + h - 25), meta, font=f_meta, fill=TEXT_MUTED)


def _draw_disclaimer(draw, W, H, cfg, f_disclaimer):
    text = DISCLAIMER_TEXT
    tw = draw.textlength(text, font=f_disclaimer)
    y = H + cfg["handle_y"] - f_disclaimer.size - 14 + cfg.get("disclaimer_y_shift", 0)
    draw.text(((W - tw) / 2, y), text, font=f_disclaimer, fill=(175, 187, 202))

# =========================================================
# MAIN IMAGE CREATOR
# =========================================================
def create_portfolio_image(df: pd.DataFrame, out_template: str, image_mode: str):
    cfg = get_layout(image_mode)
    columns = get_columns_for_mode(image_mode)

    W, H = cfg["size"]
    side = cfg["side_pad"]
    inner = cfg["inner_pad"]
    card_top = cfg["card_top"]
    max_card_bottom = H - cfg["bottom_margin"]

    f_title = _load_font(cfg["title_font"], True)
    f_subtitle = _load_font(cfg["subtitle_font"], False)
    f_meta = _load_font(cfg["meta_font"], False)
    f_sum_title = _load_font(cfg["summary_title_font"], True)
    f_sum_value = _load_font(cfg["summary_value_font"], True)
    f_banner = _load_font(cfg["banner_font"], True)
    f_hdr = _load_font(cfg["header_font"], True)
    f_cell = _load_font(cfg["cell_font"], False)
    f_cell_b = _load_font(cfg["cell_bold_font"], True)
    f_footer = _load_font(cfg["footer_font"], True)
    f_disclaimer = _load_font(cfg["disclaimer_font"], False)

    card_left = side
    card_right = W - side
    inner_left = card_left + inner
    inner_right = card_right - inner

    summary_top = card_top + inner + cfg.get("kpi_y_shift", 0)
    banner_top = summary_top + cfg["summary_h"] + cfg["gap_after_summary"]
    table_top = banner_top + cfg["banner_h"] + cfg["gap_after_banner"]
    rows_top = table_top + cfg["header_h"]
    available_rows_h = (max_card_bottom - inner) - rows_top
    auto_rows = max(1, int(available_rows_h // cfg["row_h"]))
    rows_per_page = int(MAX_ROWS_PER_PAGE) if MAX_ROWS_PER_PAGE else auto_rows

    total_rows = len(df.index)
    total_pages = int(math.ceil(total_rows / rows_per_page)) if total_rows > 0 else 1
    generated = []
    banner_text, banner_color = get_banner(df)
    summary_cards = build_summary_cards(df)

    total_ratio = sum(c[2] for c in columns)
    norm_cols = [(src, hdr, ratio / total_ratio, style) for src, hdr, ratio, style in columns]

    for page_idx in range(total_pages):
        start = page_idx * rows_per_page
        end = min(total_rows, start + rows_per_page)
        page_df = df.iloc[start:end].reset_index(drop=True)
        rows_in_page = len(page_df)

        dynamic_card_bottom = rows_top + rows_in_page * cfg["row_h"] + inner
        card_bottom = min(max_card_bottom, dynamic_card_bottom)

        img = Image.new("RGB", (W, H), NAVY_TOP)
        _draw_background(img)
        draw = ImageDraw.Draw(img)

        _center(draw, W, TITLE_PREFIX, cfg["title_y"], f_title, GOLD)
        _paste_flag_near_title(img, draw, TITLE_PREFIX, cfg["title_y"], f_title)

        _rounded_shadow_card(img, [card_left, card_top, card_right, card_bottom], radius=30)
        draw = ImageDraw.Draw(img)

        # KPI summary cards - kept as requested
        if cfg["summary_h"] > 0:
            _draw_summary_cards(
                draw,
                summary_cards,
                inner_left,
                summary_top,
                inner_right,
                cfg["summary_h"],
                f_sum_title,
                f_sum_value,
                f_meta,
            )

        # Banner - clean text only: 27 May 2026: Balanced Quality
        draw.rounded_rectangle([inner_left, banner_top, inner_right, banner_top + cfg["banner_h"]], radius=20, fill=banner_color)
        banner_font = f_banner
        while draw.textlength(banner_text, font=banner_font) > (inner_right - inner_left - 36) and banner_font.size > 16:
            banner_font = _load_font(banner_font.size - 2, True)
        tw = draw.textlength(banner_text, font=banner_font)
        try:
            bb = draw.textbbox((0, 0), banner_text, font=banner_font)
            th = bb[3] - bb[1]
        except Exception:
            th = banner_font.size
        draw.text((inner_left + (inner_right - inner_left - tw) / 2, banner_top + (cfg["banner_h"] - th) / 2 - 1), banner_text, font=banner_font, fill=WHITE)

        # Column x positions
        xs = [inner_left]
        running = inner_left
        table_w = inner_right - inner_left
        for _, _, ratio, _ in norm_cols[:-1]:
            running += int(table_w * ratio)
            xs.append(running)
        xs.append(inner_right)

        # Header
        draw.rounded_rectangle([inner_left, table_top, inner_right, table_top + cfg["header_h"]], radius=12, fill=HEADER_BG)
        # square off bottom of header
        draw.rectangle([inner_left, table_top + cfg["header_h"] - 12, inner_right, table_top + cfg["header_h"]], fill=HEADER_BG)

        for i, (_, header, _, _) in enumerate(norm_cols):
            _draw_text_lines(draw, header, xs[i], table_top, xs[i + 1], table_top + cfg["header_h"], f_hdr, TEXT_DARK, max_lines=2)
            if i != 0:
                draw.line([xs[i], table_top, xs[i], card_bottom - inner], fill=GRID, width=1)

        # Rows
        yrow = rows_top
        for ridx, row in page_df.iterrows():
            if yrow + cfg["row_h"] > card_bottom - inner:
                break
            row_bg = (247, 250, 253) if ridx % 2 else (255, 255, 255)
            draw.rectangle([inner_left, yrow, inner_right, yrow + cfg["row_h"]], fill=row_bg)

            for i, (src_col, _, _, style) in enumerate(norm_cols):
                raw_val = row.get(src_col, "-")
                if style == "stock":
                    text = _short_stock_name(raw_val, 28 if image_mode == "standard" else 20)
                else:
                    text = _format_cell(raw_val, style)
                color, chip_bg = _cell_colors(style, raw_val)
                x0, x1 = xs[i], xs[i + 1]
                if style in ["score", "grade", "label", "risk"]:
                    _draw_badge(draw, [x0, yrow, x1, yrow + cfg["row_h"]], text, f_cell_b, color, chip_bg)
                elif style == "symbol":
                    _draw_text_lines(draw, text, x0, yrow, x1, yrow + cfg["row_h"], f_cell_b, BLUE, max_lines=1)
                elif style == "stock":
                    _draw_text_lines(draw, text, x0, yrow, x1, yrow + cfg["row_h"], f_cell_b, TEXT_DARK, max_lines=2)
                elif style == "view":
                    _draw_text_lines(draw, text, x0, yrow, x1, yrow + cfg["row_h"], f_cell, TEXT_MUTED, max_lines=2)
                else:
                    _draw_text_lines(draw, text, x0, yrow, x1, yrow + cfg["row_h"], f_cell, TEXT_DARK, max_lines=1)

            draw.line([inner_left, yrow + cfg["row_h"], inner_right, yrow + cfg["row_h"]], fill=GRID, width=1)
            yrow += cfg["row_h"]

        # Footer and disclaimer
        _draw_disclaimer(draw, W, H, cfg, f_disclaimer)
        _center(draw, W, BRAND_HANDLE, H + cfg["handle_y"] + cfg.get("handle_y_shift", 0), f_footer, WHITE)

        out_path = build_output_path(out_template, page_idx + 1)
        img.save(out_path, quality=95)
        generated.append(out_path)

    return generated

# =========================================================
# MAIN
# =========================================================
def main():
    print("=" * 90)
    print("AIT PORTFOLIO ANALYSIS IMAGE GENERATOR - KPI CLEAN")
    print("=" * 90)

    df = load_portfolio_data()
    if df.empty:
        raise ValueError("Portfolio analysis file is empty. Nothing to render.")

    print(f"Rows loaded: {len(df)}")
    generated = []

    if GENERATE_GENERAL_IMAGE:
        print("Generating General image...")
        generated.extend(create_portfolio_image(df, GENERAL_IMAGE_OUTPUT_TEMPLATE, "general"))

    if GENERATE_INSTAGRAM_IMAGE:
        print("Generating Instagram image...")
        generated.extend(create_portfolio_image(df, INSTAGRAM_IMAGE_OUTPUT_TEMPLATE, "instagram"))

    if GENERATE_REELS_IMAGE:
        print("Generating Reels image...")
        generated.extend(create_portfolio_image(df, REELS_IMAGE_OUTPUT_TEMPLATE, "reels"))

    if GENERATE_STANDARD_IMAGE:
        print("Generating Standard desktop image...")
        generated.extend(create_portfolio_image(df, STANDARD_IMAGE_OUTPUT_TEMPLATE, "standard"))

    print("\nGenerated files:")
    for p in generated:
        print(f"✅ {p}")
    print("=" * 90)
    print("DONE")
    print("=" * 90)


if __name__ == "__main__":
    main()
