"""
GenerateTechnicalProfilePages.py

Creates static SEO-friendly technical analysis profile pages from:
  stock-research-data/technical-analysis/{SYMBOL}.json

Output:
  technical-analysis/{stock-name-technical-analysis}/index.html
  technical-analysis/index.html

Example:
  Mahindra & Mahindra Ltd -> /technical-analysis/mahindra-and-mahindra-technical-analysis/

Run:
  python GenerateTechnicalProfilePages.py
  python GenerateTechnicalProfilePages.py --symbols M&M,TCS
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "stock-research-data" / "technical-analysis"
OUT_DIR = ROOT / "technical-analysis"
SITEMAP = ROOT / "sitemap.xml"
STYLE_VERSION = "155"
SITE_URL = "https://automationintrade.com"

INDEX_SLUG_MAP = {
    "NIFTY 50": "nifty-50",
    "NIFTY MIDCAP 50": "nifty-midcap-50",
    "NIFTY BANK": "nifty-bank",
    "BANK NIFTY": "nifty-bank",
    "NIFTY FMCG": "nifty-fmcg",
    "NIFTY AUTO": "nifty-auto",
    "NIFTY PSU BANK": "nifty-psu-bank",
    "NIFTY PVT BANK": "nifty-pvt-bank",
    "NIFTY PRIVATE BANK": "nifty-pvt-bank",
    "NIFTY NEXT 50": "nifty-next-50",
    "NIFTY 100": "nifty-100",
    "NIFTY METAL": "nifty-metal",
    "NIFTY PHARMA": "nifty-pharma",
    "NIFTY IT": "nifty-it",
    "NIFTY REALTY": "nifty-realty",
    "NIFTY INFRA": "nifty-infra",
    "NIFTY ENERGY": "nifty-energy",
    "NIFTY MEDIA": "nifty-media",
    "NIFTY COMMODITIES": "nifty-commodities",
    "NIFTY FINANCIAL SERVICES": "nifty-financial-services",
    "FINNIFTY": "finnifty",
    "S&P BSE SENSEX": "sensex",
    "SENSEX": "sensex",
}

COMPANY_SUFFIX_RE = re.compile(
    r"\b(limited|ltd\.?|inc\.?|company|co\.?|corporation|corp\.?|industries|industry)\b",
    re.I,
)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def text_value(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def load_json(path: Path) -> Dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def slugify_stock_name(name: str, symbol: str = "") -> str:
    base = text_value(name) or text_value(symbol) or "stock"
    base = base.replace("&", " and ")
    base = COMPANY_SUFFIX_RE.sub("", base)
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base.lower())
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = re.sub(r"[^a-zA-Z0-9]+", "-", symbol.lower()).strip("-") or "stock"
    return f"{base}-technical-analysis"


def parse_symbols_arg(value: str) -> set[str]:
    if not value:
        return set()
    return {x.strip().upper().replace("/", "_").replace("\\", "_") for x in re.split(r"[,\s]+", value) if x.strip()}


def fmt_price(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return esc(value)
    try:
        return "₹" + format(float(value), ",.2f")
    except Exception:
        return esc(value)


def fmt_value(item: Dict[str, Any]) -> str:
    value = item.get("value")
    typ = item.get("type")
    if value is None or value == "":
        return "—"
    if typ == "price":
        return fmt_price(value)
    if typ == "percent":
        try:
            v = float(value)
            return f"{v:+.2f}%"
        except Exception:
            return esc(value)
    return esc(value)


def tone_class(value: Any) -> str:
    text = str(value or "").upper()
    try:
        v = float(value)
        if v > 0:
            return "is-positive"
        if v < 0:
            return "is-negative"
    except Exception:
        pass
    if any(w in text for w in ["BULL", "POSITIVE", "STRONG", "BUY", "GOOD", "UPTREND"]):
        return "is-positive"
    if any(w in text for w in ["BEAR", "WEAK", "AVOID", "SELL", "RISK", "CAUTION", "DOWNTREND"]):
        return "is-negative"
    return "is-neutral"


def metric_lookup(data: Dict[str, Any], label: str) -> str:
    for item in data.get("metrics", []) + data.get("levels", []):
        if str(item.get("label", "")).strip().lower() == label.lower():
            return text_value(fmt_value(item))
    return "—"


def metric_item(data: Dict[str, Any], label: str) -> Dict[str, Any] | None:
    target = label.strip().lower()
    for item in data.get("metrics", []) + data.get("levels", []):
        if str(item.get("label", "")).strip().lower() == target:
            return item
    return None


def metric_number(data: Dict[str, Any], label: str) -> float | None:
    item = metric_item(data, label)
    if not item:
        return None
    value = item.get("value")
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.replace("₹", "").replace(",", "").replace("%", "").strip()
            value = re.sub(r"[^0-9.\-]", "", value)
        return float(value)
    except Exception:
        return None


def trend_text(data: Dict[str, Any]) -> str:
    trend = metric_lookup(data, "Trend")
    return trend if trend != "—" else text_value(data.get("view") or data.get("signal") or "Technical View")


def technical_score(data: Dict[str, Any]) -> int:
    trend = trend_text(data).lower()
    view = text_value(data.get("view")).lower()
    rsi = metric_number(data, "RSI")
    adx = metric_number(data, "ADX")
    move = metric_number(data, "1D Move")
    close = metric_number(data, "Close")
    ema21 = metric_number(data, "EMA21")
    ema50 = metric_number(data, "EMA50")

    score = 50
    if any(x in trend + " " + view for x in ["strong", "bull", "positive", "uptrend", "buy", "breakout"]):
        score += 18
    if any(x in trend + " " + view for x in ["weak", "bear", "downtrend", "avoid", "wait", "risk"]):
        score -= 16

    if rsi is not None:
        if 45 <= rsi <= 65:
            score += 8
        elif 35 <= rsi < 45:
            score -= 3
        elif rsi < 35:
            score -= 8
        elif 65 < rsi <= 75:
            score += 4
        elif rsi > 75:
            score -= 5

    if adx is not None:
        if adx >= 25:
            score += 8
        elif adx < 15:
            score -= 4

    if move is not None:
        score += max(-10, min(10, move * 2))

    if close and ema21:
        score += 5 if close >= ema21 else -5
    if close and ema50:
        score += 6 if close >= ema50 else -6

    return int(max(0, min(100, round(score))))


def score_label(score: int) -> str:
    if score >= 75:
        return "Strong Technical Setup"
    if score >= 60:
        return "Positive Watchlist"
    if score >= 45:
        return "Neutral / Wait for Confirmation"
    if score >= 30:
        return "Weak Technical Setup"
    return "High Risk / Avoid Zone"


def build_dynamic_analysis(data: Dict[str, Any]) -> Tuple[str, str, str]:
    stock_name = text_value(data.get("stockName")) or text_value(data.get("symbol"))
    symbol = text_value(data.get("symbol"))
    view = text_value(data.get("view") or data.get("signal") or "Technical View")
    trend = trend_text(data)
    close = metric_lookup(data, "Close")
    rsi = metric_lookup(data, "RSI")
    adx = metric_lookup(data, "ADX")
    volume = metric_lookup(data, "Volume")
    support = metric_lookup(data, "Support")
    resistance = metric_lookup(data, "Resistance")
    buy_zone = metric_lookup(data, "Buy Zone")
    target = metric_lookup(data, "Sell / Target")
    stop_loss = metric_lookup(data, "Stop Loss")
    ema21 = metric_lookup(data, "EMA21")
    ema50 = metric_lookup(data, "EMA50")
    move = metric_lookup(data, "1D Move")
    score = technical_score(data)
    label = score_label(score)

    p1 = (
        f"{stock_name} ({symbol}) is currently showing a {view} technical view with an AIT Technical Score of {score}/100, "
        f"which places it in the {label} category. The latest generated close is {close}, with a one-day move of {move}. "
        f"The trend reading is {trend}, while RSI is {rsi} and ADX is {adx}. This combination helps identify whether the stock is trending, consolidating, or waiting for confirmation."
    )
    p2 = (
        f"For price-level planning, the current support zone is near {support}, while resistance is near {resistance}. "
        f"The generated buy zone is {buy_zone}, the upside reference or sell/target zone is {target}, and the stop-loss reference is {stop_loss}. "
        f"EMA21 is {ema21} and EMA50 is {ema50}, so comparing the close with these averages gives an additional trend filter."
    )
    p3 = (
        f"Volume condition is marked as {volume}. If price moves above resistance with improving volume and RSI strength, the setup can shift towards a stronger breakout watch. "
        f"If price breaks below support or remains below moving averages, the risk side stays important. This profile is updated from generated technical data and should be used as an educational reference, not as a direct buy or sell recommendation."
    )
    return p1, p2, p3


def index_links(data: Dict[str, Any]) -> List[str]:
    links = []
    indices = data.get("indices") or []
    if not indices and data.get("index"):
        indices = [data.get("index")]
    for item in indices:
        name = text_value(item).upper()
        slug = INDEX_SLUG_MAP.get(name)
        if slug:
            links.append(f'<a href="/market-tools/52-week-high-low/{esc(slug)}/">{esc(name)} 52W Tracker</a>')
    return links[:4]


def render_related_links(data: Dict[str, Any]) -> str:
    stock_name = text_value(data.get("stockName")) or text_value(data.get("symbol"))
    symbol = text_value(data.get("symbol"))
    links = [
        '<a href="/technical-analysis/">All Technical Analysis Profiles</a>',
        '<a href="/market-tools/stock-strength-ranker/">AIT Stock Strength Ranker</a>',
        '<a href="/market-tools/bullish-bearish-momentum-scanner/">Bullish/Bearish Momentum Scanner</a>',
        '<a href="/market-tools/near-breakout-scanner/">Near Breakout Scanner</a>',
        '<a href="/market-tools/volume-surge-scanner/">Volume Surge Scanner</a>',
        f'<a href="/?stock={esc(symbol)}&amp;research=technical-analysis">{esc(stock_name)} Research Card</a>',
    ] + index_links(data)
    return "\n".join(f"          {link}" for link in links)


def extract_header_footer() -> Tuple[str, str]:
    sample = ROOT / "market-tools" / "index.html"
    if not sample.exists():
        sample = ROOT / "index.html"
    text = sample.read_text(encoding="utf-8", errors="ignore")
    header_match = re.search(r"<header class=\"site-header\">.*?</header>", text, re.S)
    footer_match = re.search(r"<footer class=\"site-footer.*?</html>", text, re.S)
    if not header_match:
        raise RuntimeError("Could not extract site header.")
    header = header_match.group(0)
    footer = footer_match.group(0) if footer_match else "</body></html>"
    # Keep generated pages on latest stylesheet/script cache.
    header = re.sub(r"/style\.css\?v=\d+", f"/style.css?v={STYLE_VERSION}", header)
    footer = re.sub(r"/script\.js\?v=\d+", f"/script.js?v={STYLE_VERSION}", footer)
    return header, footer


def render_metric_cards(items: Iterable[Dict[str, Any]]) -> str:
    cards = []
    for item in items:
        label = esc(item.get("label", ""))
        value = fmt_value(item)
        cards.append(
            f'''        <div class="technical-profile-kv">
          <span>{label}</span>
          <strong class="{tone_class(item.get('tone') or item.get('value'))}">{value}</strong>
        </div>'''
        )
    return "\n".join(cards)


def render_action_rows(rows: Iterable[Dict[str, Any]]) -> str:
    out = []
    for row in rows:
        out.append(
            f'''        <div class="technical-profile-row">
          <span>{esc(row.get('label') or row.get('name') or '')}</span>
          <strong class="{tone_class(row.get('value'))}">{esc(row.get('value') or '')}</strong>
        </div>'''
        )
    return "\n".join(out)



def render_profile_page(data: Dict[str, Any], slug: str, header: str, footer: str) -> str:
    symbol = text_value(data.get("symbol"))
    stock_name = text_value(data.get("stockName")) or symbol
    view = text_value(data.get("view") or data.get("signal") or "Technical View")
    updated = text_value(data.get("updatedAt")) or datetime.now().strftime("%d-%b-%Y %H:%M IST")
    close = metric_lookup(data, "Close")
    rsi = metric_lookup(data, "RSI")
    adx = metric_lookup(data, "ADX")
    support = metric_lookup(data, "Support")
    resistance = metric_lookup(data, "Resistance")
    buy_zone = metric_lookup(data, "Buy Zone")
    target = metric_lookup(data, "Sell / Target")
    stop_loss = metric_lookup(data, "Stop Loss")
    score = technical_score(data)
    score_name = score_label(score)

    title = f"{stock_name} Technical Analysis Today | {symbol} Share Support, Resistance & Trend"
    description = (
        f"{stock_name} technical analysis today with CMP {close}, AIT score {score}/100, trend, RSI {rsi}, "
        f"ADX {adx}, support {support}, resistance {resistance}, buy zone, target and stop-loss."
    )
    canonical = f"{SITE_URL}/technical-analysis/{slug}/"
    h1 = f"{stock_name} Technical Analysis Today"
    p1, p2, p3 = build_dynamic_analysis(data)

    metrics_html = render_metric_cards(data.get("metrics", []))
    levels_html = render_metric_cards(data.get("levels", []))
    rows_html = render_action_rows(data.get("rows", []))
    related_html = render_related_links(data)

    faq_items = [
        (
            f"What is the technical view of {stock_name} today?",
            f"The current generated technical view for {stock_name} is {view}, with an AIT Technical Score of {score}/100. The score is derived from trend, RSI, ADX, moving averages, daily move and price-level context."
        ),
        (
            f"What is the support level for {stock_name}?",
            f"The generated support reference for {stock_name} is {support}. Traders usually watch whether price holds above support or breaks below it with volume."
        ),
        (
            f"What is the resistance level for {stock_name}?",
            f"The generated resistance reference for {stock_name} is {resistance}. A move above resistance with improving volume may indicate breakout strength."
        ),
        (
            f"What is the RSI of {stock_name}?",
            f"The latest generated RSI value shown for {stock_name} is {rsi}. RSI is used to judge momentum strength, weakness and overbought or oversold conditions."
        ),
        (
            f"Is {stock_name} technical analysis a buy or sell recommendation?",
            "No. This is an educational technical-analysis profile generated from data. It should be used for research and learning, not as direct investment advice."
        ),
    ]

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{SITE_URL}/#organization",
                "name": "Automation In Trade",
                "url": SITE_URL + "/",
            },
            {
                "@type": "WebPage",
                "@id": canonical + "#webpage",
                "url": canonical,
                "name": title,
                "description": description,
                "dateModified": updated,
                "isPartOf": {"@id": f"{SITE_URL}/#website"},
                "about": [stock_name, symbol, "technical analysis", "RSI", "support resistance", "moving averages"],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Technical Analysis", "item": SITE_URL + "/technical-analysis/"},
                    {"@type": "ListItem", "position": 3, "name": h1, "item": canonical},
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faq_items
                ],
            },
        ],
    }

    faq_html = "\n".join(
        f'    <details{" open" if i == 0 else ""}><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
        for i, (q, a) in enumerate(faq_items)
    )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{esc(title)}</title>
<meta name="description" content="{esc(description[:168])}"/>
<meta name="keywords" content="{esc(stock_name)} technical analysis today, {esc(symbol)} share technical analysis, {esc(stock_name)} RSI, {esc(stock_name)} support resistance, {esc(stock_name)} trend analysis, {esc(symbol)} share target stop loss"/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link rel="canonical" href="{canonical}"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;family=Manrope:wght@500;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="/style.css?v={STYLE_VERSION}" rel="stylesheet"/>
<meta property="og:site_name" content="Automation In Trade"/>
<meta property="og:title" content="{esc(title)}"/>
<meta property="og:description" content="{esc(description[:190])}"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:type" content="article"/>
<meta name="twitter:card" content="summary_large_image"/>
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
{header}
<main>
  <section class="technical-profile-hero section-padding">
    <nav class="technical-profile-breadcrumb"><a href="/">Home</a><span>›</span><a href="/technical-analysis/">Technical Analysis</a><span>›</span><span>{esc(stock_name)}</span></nav>
    <div class="technical-profile-hero-grid">
      <div>
        <p class="eyebrow">Stock Technical Analysis Profile</p>
        <h1>{esc(h1)}</h1>
        <p class="technical-profile-intro">{esc(p1)}</p>
        <div class="technical-profile-freshness">Updated: <strong>{esc(updated)}</strong> · Data-based educational view · Not investment advice</div>
        <div class="technical-profile-actions">
          <a class="btn btn-primary" href="/?stock={esc(symbol)}&amp;research=technical-analysis">Open Research Card</a>
          <a class="btn btn-secondary" href="/technical-zone-finder/">Technical Zone Finder</a>
        </div>
      </div>
      <aside class="technical-profile-score-card">
        <span>{esc(symbol)}</span>
        <h2 class="{tone_class(view)}">{esc(view)}</h2>
        <p>{esc(score_name)}</p>
        <div class="technical-score-meter"><strong>{score}</strong><small>/100 AIT Technical Score</small></div>
        <div class="technical-profile-mini-grid">
          <div><small>CMP</small><strong>{close}</strong></div>
          <div><small>RSI</small><strong>{rsi}</strong></div>
          <div><small>Support</small><strong>{support}</strong></div>
          <div><small>Resistance</small><strong>{resistance}</strong></div>
        </div>
      </aside>
    </div>
  </section>

  <section class="section-padding technical-profile-section">
    <div class="section-heading compact-market-seo">
      <p class="eyebrow">Complete Technical View</p>
      <h2>{esc(stock_name)} trend, RSI, ADX and volume analysis</h2>
      <p>{esc(p2)}</p>
    </div>
    <div class="technical-profile-grid">
      {metrics_html}
    </div>
  </section>

  <section class="section-padding technical-profile-section technical-profile-alt">
    <div class="section-heading compact-market-seo">
      <p class="eyebrow">Price Levels</p>
      <h2>{esc(stock_name)} support, resistance, target and stop-loss zones</h2>
      <p>{esc(p3)}</p>
    </div>
    <div class="technical-profile-grid levels-grid">
      {levels_html}
    </div>
  </section>

  <section class="section-padding technical-profile-section">
    <div class="technical-profile-two-col">
      <article class="technical-profile-card">
        <h2>{esc(stock_name)} technical interpretation</h2>
        <p>{esc(stock_name)} is currently classified as <strong>{esc(view)}</strong>. RSI is {rsi}, ADX is {adx}, support is near {support}, resistance is near {resistance}, buy zone is {buy_zone}, target is {target}, and stop-loss reference is {stop_loss}.</p>
        <div class="technical-profile-rows">
          {rows_html}
        </div>
      </article>
      <article class="technical-profile-card">
        <h2>How to use this technical analysis page</h2>
        <p>Check whether price is above key moving averages, whether RSI is overheated or weak, whether ADX supports trend strength, and whether current price is closer to support or resistance.</p>
        <ul class="technical-profile-list">
          <li>Use support and stop-loss zones for risk reference.</li>
          <li>Use resistance and target levels for upside reference.</li>
          <li>Compare the AIT Technical Score with trend and volume before forming a view.</li>
          <li>Avoid treating any generated level as a guaranteed entry or exit.</li>
        </ul>
      </article>
    </div>
  </section>

  <section class="section-padding technical-profile-section technical-profile-alt">
    <div class="section-heading compact-market-seo">
      <p class="eyebrow">Related Stock Research Links</p>
      <h2>Explore more technical signals for {esc(stock_name)}</h2>
      <p>These internal links connect this stock profile with scanners, 52-week high-low pages and research tools so users can continue analysis without searching again.</p>
    </div>
    <div class="technical-profile-related-links">
{related_html}
    </div>
  </section>

  <section class="section-padding technical-profile-faq">
    <h2>{esc(stock_name)} Technical Analysis FAQ</h2>
{faq_html}
  </section>
</main>
{footer}'''


def load_symbol_index_map() -> Dict[str, Dict[str, Any]]:
    """Load index membership and latest market values from 52-week JSON files."""
    high_low_dir = ROOT / "market-data" / "52-week-high-low"
    out: Dict[str, Dict[str, Any]] = {}
    if not high_low_dir.exists():
        return out
    for path in sorted(high_low_dir.glob("*.json")):
        payload = load_json(path) or {}
        index_name = payload.get("indexName") or path.stem
        for row in payload.get("stocks", []):
            symbol = text_value(row.get("symbol")).upper().replace("/", "_").replace("\\", "_")
            if not symbol:
                continue
            item = out.setdefault(symbol, {"indices": [], "marketUpdatedAt": payload.get("updatedAt", "")})
            if index_name not in item["indices"]:
                item["indices"].append(index_name)
            for key in ["cmp", "changePct", "high52", "low52", "downFromHighPct", "aboveLowPct", "status"]:
                if row.get(key) is not None:
                    item[key] = row.get(key)
            if row.get("stockName"):
                item["stockName"] = row.get("stockName")
            if payload.get("updatedAt"):
                item["marketUpdatedAt"] = payload.get("updatedAt")
    return out

def collect_profiles(symbols_filter: set[str]) -> List[Tuple[str, Dict[str, Any], Path]]:
    if not DATA_DIR.exists():
        return []
    profiles = []
    used_slugs = set()
    index_map = load_symbol_index_map()
    for path in sorted(DATA_DIR.glob("*.json")):
        symbol = path.stem.upper()
        if symbols_filter and symbol not in symbols_filter:
            continue
        data = load_json(path)
        if not data:
            continue

        enrich = index_map.get(symbol, {})
        if enrich:
            data = dict(data)
            data["indices"] = enrich.get("indices", data.get("indices", []))
            data["marketUpdatedAt"] = enrich.get("marketUpdatedAt", data.get("marketUpdatedAt", ""))
            if not data.get("stockName") and enrich.get("stockName"):
                data["stockName"] = enrich.get("stockName")
            # Keep technical indicator values from technical JSON, but expose latest 52W context for links/SEO.
            for key in ["high52", "low52", "downFromHighPct", "aboveLowPct", "status"]:
                if enrich.get(key) is not None:
                    data[key] = enrich.get(key)

        slug = slugify_stock_name(data.get("stockName") or symbol, symbol)
        if slug in used_slugs:
            slug = slugify_stock_name(f"{data.get('stockName') or symbol} {symbol}", symbol)
        used_slugs.add(slug)
        profiles.append((slug, data, path))
    return profiles

def render_hub_page(profiles: List[Tuple[str, Dict[str, Any], Path]], header: str, footer: str) -> str:
    cards = []
    for slug, data, _ in profiles:
        stock_name = text_value(data.get("stockName")) or text_value(data.get("symbol"))
        symbol = text_value(data.get("symbol"))
        view = text_value(data.get("view") or "Technical View")
        rsi = metric_lookup(data, "RSI")
        support = metric_lookup(data, "Support")
        resistance = metric_lookup(data, "Resistance")
        score = technical_score(data)
        cards.append(f'''      <a class="technical-profile-hub-card" href="/technical-analysis/{esc(slug)}/">
        <span>{esc(symbol)}</span>
        <h2>{esc(stock_name)} Technical Analysis Today</h2>
        <p class="{tone_class(view)}">{esc(view)} · Score {score}/100</p>
        <small>RSI {rsi} · Support {support} · Resistance {resistance}</small>
      </a>''')
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Stock Technical Analysis Profiles",
        "url": f"{SITE_URL}/technical-analysis/",
        "description": "Stock-wise technical analysis profiles with RSI, ADX, support, resistance, trend and risk levels.",
    }
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Stock Technical Analysis Today | RSI, Support, Resistance & Trend Profiles</title>
<meta name="description" content="Browse stock-wise technical analysis profiles with RSI, ADX, support, resistance, trend, buy zone, target and stop-loss reference levels."/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link rel="canonical" href="{SITE_URL}/technical-analysis/"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;family=Manrope:wght@500;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="/style.css?v={STYLE_VERSION}" rel="stylesheet"/>
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
{header}
<main>
<section class="technical-profile-hero section-padding">
  <p class="eyebrow">Stock Technical Analysis</p>
  <h1>Stock-wise technical analysis profiles</h1>
  <p class="technical-profile-intro">Open a stock profile to view trend, RSI, ADX, volume, support, resistance, target and stop-loss reference levels generated from technical-analysis JSON. These pages are designed as useful long-tail SEO assets for searches like stock technical analysis, support resistance and RSI trend view.</p>
</section>
<section class="section-padding">
  <div class="technical-profile-hub-grid">
{chr(10).join(cards)}
  </div>
</section>
</main>
{footer}'''

def update_sitemap(profile_slugs: List[str]) -> None:
    urls = [f"{SITE_URL}/technical-analysis/"] + [f"{SITE_URL}/technical-analysis/{slug}/" for slug in sorted(profile_slugs)]
    today = datetime.now().strftime("%Y-%m-%d")
    block = "\n".join(
        f"  <url><loc>{esc(url)}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.72</priority></url>"
        for url in urls
    )
    if not SITEMAP.exists():
        sitemap = f'''<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{block}\n</urlset>\n'''
        SITEMAP.write_text(sitemap, encoding="utf-8")
        return
    text = SITEMAP.read_text(encoding="utf-8", errors="ignore")
    # Remove previous technical profile URLs before appending latest set.
    text = re.sub(r"\s*<url>\s*<loc>https://automationintrade\.com/technical-analysis/.*?</url>", "", text, flags=re.S)
    text = text.replace("</urlset>", block + "\n</urlset>")
    SITEMAP.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SEO-friendly stock technical analysis profile pages.")
    parser.add_argument("--symbols", default="", help="Optional symbols to generate, e.g. M&M,TCS,RELIANCE")
    parser.add_argument("--clean", action="store_true", help="Delete existing generated technical-analysis profile folders before rebuilding.")
    args = parser.parse_args()

    profiles = collect_profiles(parse_symbols_arg(args.symbols))
    if not profiles:
        print("No technical-analysis JSON files found. Run GenerateTechnicalAnalysisJson.py first.")
        return 1

    header, footer = extract_header_footer()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for child in OUT_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)

    generated_slugs = []
    for slug, data, _ in profiles:
        page_dir = OUT_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render_profile_page(data, slug, header, footer), encoding="utf-8")
        generated_slugs.append(slug)
        print(f"Generated: /technical-analysis/{slug}/")

    (OUT_DIR / "index.html").write_text(render_hub_page(profiles, header, footer), encoding="utf-8")
    update_sitemap(generated_slugs)
    print(f"Generated {len(generated_slugs)} technical analysis profile pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
