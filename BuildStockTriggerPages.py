"""
BuildStockTriggerPages.py

Generate SEO-friendly event pages, permanent stock hubs and category pages from
market-data/stock-triggers.json. The generator is called automatically by
GenerateStockTriggersJson.py, so these pages are rebuilt whenever the daily
market-data workflow runs.

Commands:
    python BuildStockTriggerPages.py
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "market-data" / "stock-triggers.json"
INDEX_TEMPLATE = ROOT / "stock-triggers" / "index.html"
EVENT_DIR = ROOT / "stock-triggers" / "events"
CATEGORY_DIR = ROOT / "stock-triggers" / "category"
METHOD_DIR = ROOT / "stock-triggers" / "methodology"
STOCK_DIR = ROOT / "stocks"
SITEMAP_FILE = ROOT / "sitemap.xml"
STOCK_TRIGGER_SITEMAP_FILE = ROOT / "sitemap-stock-triggers.xml"
ROBOTS_FILE = ROOT / "robots.txt"
MANIFEST_FILE = ROOT / "market-data" / "stock-trigger-pages-manifest.json"
URL_HISTORY_FILE = ROOT / "market-data" / "stock-trigger-url-history.json"
REDIRECTS_FILE = ROOT / "_redirects"
SITE_URL = "https://automationintrade.com"
IST = timezone(timedelta(hours=5, minutes=30))
START_MARKER = "<!-- AIT_STOCK_TRIGGER_GENERATED_START -->"
END_MARKER = "<!-- AIT_STOCK_TRIGGER_GENERATED_END -->"
REDIRECT_START = "# AIT_STOCK_TRIGGER_REDIRECTS_START"
REDIRECT_END = "# AIT_STOCK_TRIGGER_REDIRECTS_END"


def safe_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value: Any, fallback: str = "item") -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text(value).lower()).strip("-")
    return value or fallback


def safe_url(value: Any, fallback: str = "#") -> str:
    url = text(value)
    if not url:
        return fallback
    if url.startswith("/"):
        return url
    parsed = urlparse(url)
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        return url
    return fallback


def trigger_source(row: Dict[str, Any]) -> Tuple[str, str, bool]:
    attachment = safe_url(row.get("attachmentUrl"))
    if attachment != "#":
        return attachment, "Original filing", True
    source = safe_url(row.get("sourceUrl"))
    source_page = safe_url(row.get("sourcePageUrl"))
    candidate = source if source != "#" else source_page
    if candidate == "#":
        return "#", "", False
    parsed = urlparse(candidate)
    direct = (
        text(row.get("sourceLinkType")) == "original-filing"
        or "nsearchives.nseindia.com" in parsed.netloc.lower()
        or bool(re.search(r"\.(pdf|xml|zip)(?:$|[?#])", candidate, flags=re.I))
    )
    return candidate, ("Original filing" if direct else "View on NSE"), direct


def fmt_number(value: Any) -> str:
    try:
        return f"{float(value):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return text(value) or "-"


def fmt_price(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return "₹" + fmt_number(value)


def parse_date(value: Any) -> Optional[datetime]:
    raw = text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw[:11], fmt)
            except ValueError:
                continue
    return None


def template_parts() -> Tuple[str, str]:
    raw = INDEX_TEMPLATE.read_text(encoding="utf-8")
    header_match = re.search(r"(<header\b.*?</header>)", raw, flags=re.S | re.I)
    footer_match = re.search(r"(<footer\b.*?</footer>)", raw, flags=re.S | re.I)
    if not header_match or not footer_match:
        raise RuntimeError("Could not read shared header/footer from stock-triggers/index.html")
    return header_match.group(1), footer_match.group(1)


def json_ld(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def shell(
    *,
    title: str,
    description: str,
    canonical_path: str,
    main: str,
    schema: Dict[str, Any],
    header: str,
    footer: str,
    robots: str = "index, follow, max-image-preview:large",
) -> str:
    canonical = SITE_URL + canonical_path
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{escape(title)}</title>
<meta name="description" content="{escape(description, quote=True)}"/>
<meta name="robots" content="{escape(robots, quote=True)}"/>
<link rel="canonical" href="{escape(canonical, quote=True)}"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/><link crossorigin href="https://fonts.gstatic.com" rel="preconnect"/><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;family=Manrope:wght@500;600;700;800&amp;display=swap" rel="stylesheet"/><link href="/style.css?v=167" rel="stylesheet"/>
<meta property="og:site_name" content="Automation In Trade"/>
<meta property="og:title" content="{escape(title, quote=True)}"/>
<meta property="og:description" content="{escape(description, quote=True)}"/>
<meta property="og:url" content="{escape(canonical, quote=True)}"/>
<meta property="og:type" content="article"/>
<meta name="twitter:card" content="summary"/>
<script type="application/ld+json">{json_ld(schema)}</script>
</head>
<body>
{header}
<main>{main}</main>
{footer}
<script src="/script.js?v=167"></script>
<script src="/stock-triggers/watchlist.js?v=167"></script>
</body>
</html>
'''


def event_link(row: Dict[str, Any]) -> str:
    return safe_url(row.get("eventUrl"), f"/stock-triggers/?symbol={escape(text(row.get('symbol')))}")


def trigger_list(rows: Iterable[Dict[str, Any]], limit: int = 20) -> str:
    cards: List[str] = []
    for row in list(rows)[:limit]:
        symbol = text(row.get("symbol"))
        subject = text(row.get("subject")) or "Company development"
        summary = text(row.get("summary"))
        category = text(row.get("categoryLabel")) or "Material update"
        sentiment = text(row.get("sentiment")) or "Neutral"
        score = int(row.get("impactScore") or 0)
        band = text(row.get("materialityBand")) or "Unclassified"
        confidence = int(row.get("dataConfidence") or 0)
        published = text(row.get("publishedDisplay")) or text(row.get("actionDate"))
        cards.append(f'''<article class="generated-trigger-row">
<div class="generated-trigger-row-head"><div><a class="generated-symbol" href="{escape(safe_url(row.get('stockHubUrl')), quote=True)}">{escape(symbol)}</a><span>{escape(category)}</span></div><strong>{score}/100 <small>{escape(band)}</small></strong></div>
<h3><a href="{escape(event_link(row), quote=True)}">{escape(subject)}</a></h3>
<p>{escape(summary)}</p>
<div class="generated-trigger-row-meta"><span>{escape(sentiment)}</span><span>Confidence {confidence}/100</span><span>{escape(published)}</span><a href="{escape(event_link(row), quote=True)}">Full event analysis</a></div>
</article>''')
    return "\n".join(cards) or '<p class="generated-empty">No trigger records are available for this view.</p>'


def metric_items(metrics: Iterable[Dict[str, Any]], limit: int = 6) -> str:
    items: List[str] = []
    for metric in list(metrics or [])[:limit]:
        label = text(metric.get("label"))
        value = metric.get("value")
        if metric.get("type") == "percent":
            try:
                display = f"{float(value):+.2f}%"
            except (TypeError, ValueError):
                display = text(value)
        elif metric.get("type") == "price":
            display = fmt_price(value)
        else:
            display = text(value)
        items.append(f"<article><span>{escape(label)}</span><strong>{escape(display or '-')}</strong></article>")
    return "".join(items) or "<p>Supporting metrics are not available for this stock yet.</p>"


def score_breakdown_html(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in row.get("scoreBreakdown") or []:
        try:
            score = max(0, int(item.get("score") or 0))
            maximum = max(1, int(item.get("max") or 1))
        except (TypeError, ValueError):
            continue
        width = min(100, round(score * 100 / maximum))
        parts.append(f'''<article class="generated-score-factor">
<div><strong>{escape(text(item.get('label')))}</strong><span>{score}/{maximum}</span></div>
<div class="generated-score-track" aria-label="{escape(text(item.get('label')), quote=True)} score {score} out of {maximum}"><i style="width:{width}%"></i></div>
<p>{escape(text(item.get('reason')))}</p>
</article>''')
    return "".join(parts) or "<p>Score factors are unavailable for this legacy record.</p>"


def score_limitations_html(row: Dict[str, Any]) -> str:
    values = [text(value) for value in (row.get("scoreLimitations") or []) if text(value)]
    if not values:
        return "<li>No major data limitation was automatically detected.</li>"
    return "".join(f"<li>{escape(value)}</li>" for value in values[:5])


def research_payload(symbol: str, kind: str) -> Dict[str, Any]:
    return safe_load(ROOT / "stock-research-data" / kind / f"{symbol}.json", {})


def build_event_page(row: Dict[str, Any], header: str, footer: str) -> str:
    symbol = text(row.get("symbol"))
    company = text(row.get("stockName") or row.get("companyName") or symbol)
    subject = text(row.get("subject")) or "Company development"
    summary = text(row.get("summary"))
    category = text(row.get("categoryLabel")) or "Material update"
    sentiment = text(row.get("sentiment")) or "Neutral"
    score = int(row.get("impactScore") or 0)
    band = text(row.get("materialityBand")) or "Unclassified"
    confidence = int(row.get("dataConfidence") or 0)
    published = text(row.get("publishedDisplay")) or text(row.get("actionDate"))
    source, source_label, direct_source = trigger_source(row)
    stock_hub = safe_url(row.get("stockHubUrl"), f"/stock-triggers/?symbol={symbol}")
    category_url = safe_url(row.get("categoryUrl"), "/stock-triggers/")
    technical = safe_url(row.get("profileUrl"), "/technical-analysis/")
    highlights = "".join(f"<span>{escape(text(value))}</span>" for value in (row.get("highlights") or [])[:5])
    highlights_block = f'<div class="generated-pill-row">{highlights}</div>' if highlights else ""
    cmp_line = fmt_price(row.get("cmp"))
    change = row.get("changePct")
    if change not in (None, ""):
        try:
            cmp_line += f" ({float(change):+.2f}%)"
        except (TypeError, ValueError):
            pass
    facts = row.get("extractedFacts") or {}
    largest_amount = facts.get("largestAmountCrore")
    if largest_amount not in (None, ""):
        try:
            magnitude_line = f"₹{float(largest_amount):,.2f} crore (largest extracted value)"
        except (TypeError, ValueError):
            magnitude_line = text(largest_amount)
    elif facts.get("perShareRupees"):
        try:
            magnitude_line = f"₹{float(facts.get('perShareRupees')[0]):,.2f} per share"
        except (TypeError, ValueError, IndexError):
            magnitude_line = text(facts.get("perShareRupees"))
    elif facts.get("actionRatios"):
        magnitude_line = "Action ratio " + ", ".join(text(value) for value in facts.get("actionRatios")[:3])
    else:
        magnitude_line = ""
    magnitude_fact = (
        f'<div><dt>Financial magnitude</dt><dd>{escape(magnitude_line)}</dd></div>'
        if magnitude_line else ""
    )
    market_context = row.get("marketContext") or {}
    market_line_parts: List[str] = []
    if market_context.get("changePct") not in (None, ""):
        try:
            market_line_parts.append(f"1D move {float(market_context.get('changePct')):+.2f}%")
        except (TypeError, ValueError):
            pass
    if market_context.get("volumeSurgeRatio") not in (None, ""):
        try:
            market_line_parts.append(f"Volume {float(market_context.get('volumeSurgeRatio')):.2f}× average")
        except (TypeError, ValueError):
            pass
    if market_context.get("strengthScore") not in (None, ""):
        try:
            market_line_parts.append(f"Strength {float(market_context.get('strengthScore')):.1f}")
        except (TypeError, ValueError):
            pass
    market_line = " · ".join(market_line_parts) or "No current market-confirmation metrics available"
    score_breakdown = score_breakdown_html(row)
    score_limitations = score_limitations_html(row)
    filing_facts = [text(value) for value in (row.get("filingKeyFacts") or []) if text(value)]
    filing_facts_html = "".join(f"<li>{escape(value)}</li>" for value in filing_facts[:5])
    filing_section = (
        f'<h2>Key facts extracted from the official filing</h2><ul class="generated-limit-list">{filing_facts_html}</ul>'
        if filing_facts_html
        else ""
    )
    source_button = (
        f'<a class="btn btn-secondary" href="{escape(source, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(source_label)}</a>'
        if source != "#"
        else ""
    )

    main = f'''<section class="generated-page section-padding"><div class="container generated-page-container">
<nav class="generated-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>›</span><a href="/stock-triggers/">Stock Triggers</a><span>›</span><a href="{escape(category_url, quote=True)}">{escape(category)}</a><span>›</span><span>{escape(symbol)}</span></nav>
<section class="generated-event-hero">
<div><p class="eyebrow">{escape(category)} · {escape(sentiment)}</p><h1>{escape(company)} - {escape(subject)}</h1><p>{escape(summary)}</p>{highlights_block}</div>
<aside><span>AIT materiality score</span><strong>{score}/100</strong><b>{escape(band)}</b><small>Data confidence: {confidence}/100</small></aside>
</section>
<div class="generated-event-grid">
<section class="generated-content-panel">{filing_section}<h2>Why this event may matter</h2><p>{escape(text(row.get('whyItMatters')))}</p><h2>Why the score is {score}/100</h2><p>{escape(text(row.get('scoreExplanation')))}</p><div class="generated-score-breakdown">{score_breakdown}</div><h3 class="generated-subheading">What reduced confidence or materiality</h3><ul class="generated-limit-list">{score_limitations}</ul><h2>What should be verified</h2><p>{escape(text(row.get('riskNote')))}</p><h2>Event facts</h2><dl class="generated-fact-list"><div><dt>Company</dt><dd>{escape(company)} ({escape(symbol)})</dd></div><div><dt>Published / action time</dt><dd>{escape(published or '-')}</dd></div><div><dt>Classification</dt><dd>{escape(category)} · {escape(sentiment)}</dd></div><div><dt>Summary basis</dt><dd>{escape(text(row.get('summaryBasis')) or ('Official filing text' if row.get('filingExtracted') else 'Exchange announcement text'))}</dd></div><div><dt>Materiality band</dt><dd>{escape(band)}</dd></div><div><dt>Data confidence</dt><dd>{confidence}/100</dd></div>{magnitude_fact}<div><dt>Market confirmation</dt><dd>{escape(market_line)}</dd></div><div><dt>Price snapshot</dt><dd>{escape(cmp_line)}</dd></div><div><dt>AI enrichment</dt><dd>{'Yes - review against source' if row.get('aiEnhanced') else 'No - deterministic rules used'}</dd></div></dl></section>
<aside class="generated-side-panel"><button type="button" class="btn btn-primary" data-ait-follow-symbol="{escape(symbol, quote=True)}" data-ait-follow-name="{escape(company, quote=True)}">Follow {escape(symbol)}</button><a class="btn btn-secondary" href="{escape(stock_hub, quote=True)}">Open stock timeline</a><a class="btn btn-secondary" href="{escape(technical, quote=True)}">Technical context</a>{source_button}<p class="market-table-note">{('The summary uses extracted official-filing text. ' if row.get('filingExtracted') else '')}Always verify facts, dates and units in the original exchange/company disclosure.</p></aside>
</div>
<section class="generated-disclaimer"><strong>Educational boundary</strong><p>The materiality score measures the importance and evidence quality of this disclosure. It is not a buy/sell signal, target price or prediction of share-price movement.</p></section>
</div></section>'''

    canonical_path = safe_url(row.get("eventUrl"), "/stock-triggers/")
    published_iso = text(row.get("publishedAt"))
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{company}: {subject}",
        "description": summary,
        "datePublished": published_iso or None,
        "dateModified": published_iso or None,
        "mainEntityOfPage": SITE_URL + canonical_path,
        "publisher": {"@type": "Organization", "name": "Automation In Trade", "url": SITE_URL},
        "isBasedOn": source if source != "#" else None,
        "about": {"@type": "Corporation", "name": company, "tickerSymbol": symbol},
    }
    schema = {key: value for key, value in schema.items() if value is not None}
    robots = "index, follow, max-image-preview:large" if score >= 55 and source != "#" else "noindex, follow"
    description = (summary or f"{company} disclosed {subject}.")[:155]
    return shell(
        title=f"{company}: {subject} - impact and risks | AIT",
        description=description,
        canonical_path=canonical_path,
        main=main,
        schema=schema,
        header=header,
        footer=footer,
        robots=robots,
    )


def build_stock_page(symbol: str, rows: List[Dict[str, Any]], header: str, footer: str, updated_at: str) -> str:
    first = rows[0]
    company = text(first.get("stockName") or first.get("companyName") or symbol)
    result = research_payload(symbol, "results")
    technical = research_payload(symbol, "technical-analysis")
    price_action = research_payload(symbol, "price-action")
    indices = sorted({text(value) for row in rows for value in (row.get("indices") or []) if text(value)})
    index_html = "".join(f"<span>{escape(value)}</span>" for value in indices[:8]) or "<span>Index mapping unavailable</span>"
    stock_url = safe_url(first.get("stockHubUrl"), f"/stocks/{slugify(symbol)}/")
    technical_url = safe_url(first.get("profileUrl"), "/technical-analysis/")

    main = f'''<section class="generated-page section-padding"><div class="container generated-page-container">
<nav class="generated-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>›</span><a href="/stock-triggers/">Stock Triggers</a><span>›</span><span>{escape(company)}</span></nav>
<section class="generated-stock-hero"><div><p class="eyebrow">Permanent stock trigger hub</p><h1>{escape(company)} ({escape(symbol)})</h1><p>Latest business triggers, result quality, technical context and upcoming corporate actions collected under one company timeline.</p><div class="generated-pill-row">{index_html}</div></div><aside><span>Latest price snapshot</span><strong>{escape(fmt_price(first.get('cmp')))}</strong><small>Feed updated {escape(updated_at or '-')}</small><button type="button" class="btn btn-primary" data-ait-follow-symbol="{escape(symbol, quote=True)}" data-ait-follow-name="{escape(company, quote=True)}">Follow {escape(symbol)}</button></aside></section>
<section class="generated-stock-layout"><div><div class="market-table-heading"><div><p class="eyebrow">Company event history</p><h2>Latest triggers</h2></div><a class="btn btn-secondary" href="/stock-triggers/?symbol={escape(symbol, quote=True)}">Open filtered live feed</a></div><div class="generated-trigger-list">{trigger_list(rows, 25)}</div></div>
<aside class="generated-stock-sidebar"><section><h2>Latest result view</h2><strong>{escape(text(result.get('view')) or 'Not generated')}</strong><p>{escape(text(result.get('summary')) or 'Result data will appear after the research generator covers this stock.')}</p><div class="generated-mini-metrics">{metric_items(result.get('metrics') or [], 4)}</div></section><section><h2>Technical context</h2><strong>{escape(text(technical.get('view')) or text(price_action.get('view')) or 'Not generated')}</strong><p>{escape(text(technical.get('summary')) or text(price_action.get('summary')) or 'Technical context will appear when available.')}</p><div class="generated-mini-metrics">{metric_items(technical.get('metrics') or price_action.get('metrics') or [], 4)}</div><a class="btn btn-secondary" href="{escape(technical_url, quote=True)}">Open full technical profile</a></section></aside></section>
<section class="generated-disclaimer"><strong>Data separation</strong><p>Business triggers and technical indicators are displayed as separate context. Neither module provides personalised investment advice.</p></section>
</div></section>'''

    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{company} stock trigger timeline",
        "description": f"Latest verified company events and supporting research context for {company} ({symbol}).",
        "url": SITE_URL + stock_url,
        "about": {"@type": "Corporation", "name": company, "tickerSymbol": symbol},
    }
    return shell(
        title=f"{company} latest stock triggers and analysis | AIT",
        description=f"Track {company} ({symbol}) orders, results, guidance, corporate actions, risks and technical context in one updated timeline.",
        canonical_path=stock_url,
        main=main,
        schema=schema,
        header=header,
        footer=footer,
    )


def build_category_page(category: str, rows: List[Dict[str, Any]], header: str, footer: str, updated_at: str) -> str:
    label = text(rows[0].get("categoryLabel")) or category.replace("_", " ").title()
    category_url = safe_url(rows[0].get("categoryUrl"), f"/stock-triggers/category/{slugify(category)}/")
    main = f'''<section class="generated-page section-padding"><div class="container generated-page-container">
<nav class="generated-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>›</span><a href="/stock-triggers/">Stock Triggers</a><span>›</span><span>{escape(label)}</span></nav>
<section class="generated-category-hero"><p class="eyebrow">Dynamic trigger category</p><h1>{escape(label)} - latest Indian stock developments</h1><p>This page is rebuilt by the daily data pipeline. It contains {len(rows)} retained source-linked trigger records. Last generated: {escape(updated_at or '-')}.</p><a class="btn btn-primary" href="/stock-triggers/?category={escape(category, quote=True)}">Use live filters</a></section>
<div class="generated-trigger-list">{trigger_list(rows, 100)}</div>
<section class="generated-disclaimer"><strong>Methodology</strong><p>Announcements are classified with deterministic rules and optional AI enrichment. Open the source filing before relying on a summary.</p></section>
</div></section>'''
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{label} stock triggers",
        "description": f"Latest {label.lower()} disclosures and corporate developments for Indian listed companies.",
        "url": SITE_URL + category_url,
    }
    return shell(
        title=f"{label} stocks and company updates | AIT",
        description=f"Automatically updated {label.lower()} stock events with source links, impact context and risks.",
        canonical_path=category_url,
        main=main,
        schema=schema,
        header=header,
        footer=footer,
    )


def build_methodology_page(payload: Dict[str, Any], header: str, footer: str) -> str:
    categories = payload.get("categories") or []
    category_html = "".join(
        f"<li><strong>{escape(text(item.get('label')))}</strong><span>{escape(text(item.get('id')))}</span></li>"
        for item in categories if isinstance(item, dict)
    )
    main = f'''<section class="generated-page section-padding"><div class="container generated-page-container">
<nav class="generated-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>&rsaquo;</span><a href="/stock-triggers/">Stock Triggers</a><span>&rsaquo;</span><span>Methodology</span></nav>
<section class="generated-category-hero"><p class="eyebrow">Transparency and trust</p><h1>AIT Stock Trigger Intelligence methodology</h1><p>This page explains how company disclosures become trigger records, how the score should be interpreted and how the system protects users when a source is temporarily unavailable.</p></section>
<div class="generated-method-grid"><section><h2>1. Sources and update cycle</h2><p>Recent official corporate announcements are requested during the scheduled market-data workflow. Upcoming corporate actions are merged from the existing local corporate-action dataset. Current price, volume, strength and momentum context is read from the website’s existing daily scanners.</p><p><strong>Latest packaged status:</strong> {escape(text(payload.get('sourceMode')))} · {escape(text(payload.get('updatedAt')))}</p></section><section><h2>2. Classification</h2><p>Deterministic rules separate business events from low-information updates. Investor meetings and recording links are classified separately so they are not mistaken for institutional accumulation.</p><ul class="generated-method-list">{category_html}</ul></section><section><h2>3. Five-factor materiality score</h2><p>The 0-100 score is the visible sum of business materiality (35), evidence specificity (20), financial magnitude (20), market confirmation (15), and recency or urgency (10). Every event page shows the points and reason for each factor.</p></section><section><h2>4. Data confidence</h2><p>A separate confidence score reflects filing detail, extracted facts and source availability. Low-confidence records can remain visible for monitoring, but the page clearly states what could not be verified.</p></section><section><h2>5. Fallback protection</h2><p>If the fresh request fails, recent previously generated records are preserved and corporate actions are rebuilt. Retained records are re-scored with the newest model so old static scores do not remain in the feed.</p></section><section><h2>6. AI and corrections</h2><p>AI may improve wording but cannot invent amounts or override the transparent scoring formula. Users should verify the original filing because automated extraction can misread units, dates or context.</p></section><section><h2>7. Score boundary</h2><p>The materiality score measures the importance and evidence quality of a disclosure. It does not forecast return, target price, probability of a rise or suitability for any investor.</p></section><section><h2>8. Data-use boundary</h2><p>Automation In Trade should review exchange data-sharing and commercial redistribution requirements before scaling paid redistribution, API access or bulk export.</p></section></div>
<section class="generated-disclaimer"><strong>Educational use only</strong><p>The trigger feed is a discovery and monitoring tool, not an investment recommendation or personalised advisory service.</p></section>
</div></section>'''
    schema = {"@context": "https://schema.org", "@type": "WebPage", "name": "AIT Stock Trigger Intelligence methodology", "url": SITE_URL + "/stock-triggers/methodology/", "description": "Sources, classification, scoring, AI labels, fallback protection and educational boundaries for AIT Stock Trigger Intelligence."}
    return shell(title="Stock Trigger Intelligence methodology | AIT", description="Learn how AIT classifies company announcements, calculates transparent five-factor materiality scores, measures confidence and handles stale sources.", canonical_path="/stock-triggers/methodology/", main=main, schema=schema, header=header, footer=footer)


def sitemap_entry(path: str, lastmod: str = "") -> str:
    """Return a clean Google-friendly XML sitemap entry.

    Google ignores priority/changefreq, so only loc and a truthful lastmod are
    emitted. Keeping each tag on its own line also makes manual inspection in
    Search Console and editors much less confusing.
    """
    lines = ["  <url>", f"    <loc>{SITE_URL}{escape(path)}</loc>"]
    if lastmod:
        lines.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
    lines.append("  </url>")
    return "\n".join(lines)


def ensure_robots_sitemaps() -> None:
    """Advertise both the main sitemap and the dedicated Stock Triggers sitemap."""
    main_line = f"Sitemap: {SITE_URL}/sitemap.xml"
    trigger_line = f"Sitemap: {SITE_URL}/sitemap-stock-triggers.xml"
    raw = ROBOTS_FILE.read_text(encoding="utf-8") if ROBOTS_FILE.exists() else "User-agent: *\nAllow: /\n"
    lines = [line.rstrip() for line in raw.splitlines()]
    lines = [line for line in lines if line.strip() not in {main_line, trigger_line}]
    while lines and not lines[-1].strip():
        lines.pop()
    lines.extend(["", main_line, trigger_line])
    ROBOTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def write_page_if_changed(target: Path, content: str, previous: Dict[str, Any], build_date: str) -> Dict[str, Any]:
    """Write a page only when its rendered content changed.

    The returned lastmod is therefore a truthful content-modification date, not
    merely the date on which the cron job happened to run.
    """
    digest = content_hash(content)
    previous_hash = text(previous.get("hash"))
    previous_lastmod = text(previous.get("lastmod"))
    unchanged = previous_hash == digest
    if not unchanged and target.exists():
        try:
            unchanged = target.read_text(encoding="utf-8") == content
        except OSError:
            unchanged = False
    if not unchanged:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    elif not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        unchanged = False
    return {"hash": digest, "lastmod": previous_lastmod if unchanged and previous_lastmod else build_date}


def update_redirects(rows: List[Dict[str, Any]], build_date: str) -> int:
    """Persist permanent redirects from legacy event URLs to stable canonical URLs."""
    payload = safe_load(URL_HISTORY_FILE, {})
    history = payload.get("redirects", {}) if isinstance(payload, dict) else {}
    if not isinstance(history, dict):
        history = {}

    for row in rows:
        current = safe_url(row.get("eventUrl"))
        if current == "#":
            continue
        for old in row.get("legacyEventUrls") or []:
            old_path = safe_url(old)
            if old_path == "#" or old_path == current:
                continue
            history[old_path] = {"to": current, "lastSeen": build_date}

    # Collapse any redirect chains so Googlebot always receives one 301 hop.
    for old, meta in list(history.items()):
        target = text(meta.get("to")) if isinstance(meta, dict) else text(meta)
        seen = {old}
        while target in history and target not in seen:
            seen.add(target)
            next_meta = history[target]
            target = text(next_meta.get("to")) if isinstance(next_meta, dict) else text(next_meta)
        if not target or target == old:
            history.pop(old, None)
            continue
        last_seen = text(meta.get("lastSeen")) if isinstance(meta, dict) else build_date
        history[old] = {"to": target, "lastSeen": last_seen or build_date}

    URL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    URL_HISTORY_FILE.write_text(
        json.dumps({"updatedAt": build_date, "redirects": history}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    existing = REDIRECTS_FILE.read_text(encoding="utf-8") if REDIRECTS_FILE.exists() else ""
    pattern = re.compile(re.escape(REDIRECT_START) + r".*?" + re.escape(REDIRECT_END) + r"\s*", flags=re.S)
    clean = pattern.sub("", existing).rstrip()
    redirect_lines = [REDIRECT_START]
    for old in sorted(history):
        target = text(history[old].get("to")) if isinstance(history[old], dict) else text(history[old])
        if old.startswith("/") and target.startswith("/") and old != target:
            redirect_lines.append(f"{old} {target} 301")
    redirect_lines.append(REDIRECT_END)
    combined = (clean + "\n\n" if clean else "") + "\n".join(redirect_lines) + "\n"
    REDIRECTS_FILE.write_text(combined, encoding="utf-8")
    return max(0, len(redirect_lines) - 2)


def update_sitemap(
    *,
    event_registry: Dict[str, Dict[str, Any]],
    stock_registry: Dict[str, Dict[str, Any]],
    category_registry: Dict[str, Dict[str, Any]],
    main_lastmod: str,
    methodology_lastmod: str,
) -> int:
    """Write stable Stock Trigger URLs to a dedicated root-level sitemap."""
    if SITEMAP_FILE.exists():
        raw = SITEMAP_FILE.read_text(encoding="utf-8")
        block_pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER) + r"\s*", flags=re.S)
        cleaned = block_pattern.sub("", raw)
        if cleaned != raw:
            SITEMAP_FILE.write_text(cleaned, encoding="utf-8")

    entries: List[str] = [
        sitemap_entry("/stock-triggers/", main_lastmod),
        sitemap_entry("/stock-triggers/methodology/", methodology_lastmod),
    ]
    for path in sorted(category_registry):
        meta = category_registry[path]
        entries.append(sitemap_entry(path, text(meta.get("lastmod"))))
    for path in sorted(stock_registry):
        meta = stock_registry[path]
        entries.append(sitemap_entry(path, text(meta.get("lastmod"))))
    for path in sorted(event_registry):
        meta = event_registry[path]
        if meta.get("indexable"):
            entries.append(sitemap_entry(path, text(meta.get("lastmod"))))

    if len(entries) > 50000:
        raise RuntimeError("Stock Trigger sitemap exceeded 50,000 URLs; split it into a sitemap index before publishing.")

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    STOCK_TRIGGER_SITEMAP_FILE.write_text(sitemap, encoding="utf-8")
    ensure_robots_sitemaps()
    return len(entries)


def build_pages(payload: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    if payload is None:
        payload = safe_load(DATA_FILE, {})
    rows = [row for row in (payload.get("triggers") or []) if isinstance(row, dict)]
    header, footer = template_parts()
    updated_at = text(payload.get("updatedAt"))
    generated = parse_date(payload.get("generatedAt"))
    data_lastmod = generated.date().isoformat() if generated else datetime.now().date().isoformat()
    build_date = datetime.now(IST).date().isoformat()

    previous_manifest = safe_load(MANIFEST_FILE, {})
    event_registry = previous_manifest.get("eventRegistry", {}) if isinstance(previous_manifest, dict) else {}
    stock_registry = previous_manifest.get("stockRegistry", {}) if isinstance(previous_manifest, dict) else {}
    category_registry = previous_manifest.get("categoryRegistry", {}) if isinstance(previous_manifest, dict) else {}
    methodology_registry = previous_manifest.get("methodologyRegistry", {}) if isinstance(previous_manifest, dict) else {}
    if not isinstance(event_registry, dict):
        event_registry = {}
    if not isinstance(stock_registry, dict):
        stock_registry = {}
    if not isinstance(category_registry, dict):
        category_registry = {}
    if not isinstance(methodology_registry, dict):
        methodology_registry = {}

    # Important SEO rule: never wipe event/stock directories on a cron run.
    # Historical, indexable URLs remain available instead of turning into 404s
    # just because they fell outside the rolling 500-row feed.
    for directory in (EVENT_DIR, CATEGORY_DIR, STOCK_DIR, METHOD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    event_count = 0
    stock_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    category_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen_event_paths: set[str] = set()

    for row in rows:
        symbol = text(row.get("symbol")).upper()
        category = text(row.get("category")) or "OTHER_MATERIAL"
        if symbol:
            stock_rows[symbol].append(row)
        category_rows[category].append(row)
        event_url = safe_url(row.get("eventUrl"))
        slug = text(row.get("eventSlug")) or event_url.rstrip("/").split("/")[-1]
        if not slug or event_url == "#" or event_url in seen_event_paths:
            continue
        seen_event_paths.add(event_url)
        target = EVENT_DIR / slug / "index.html"
        rendered = build_event_page(row, header, footer)
        previous_meta = event_registry.get(event_url, {}) if isinstance(event_registry.get(event_url), dict) else {}
        page_meta = write_page_if_changed(target, rendered, previous_meta, build_date)
        source, _label, _direct = trigger_source(row)
        page_meta.update({
            "indexable": int(row.get("impactScore") or 0) >= 55 and source != "#",
            "sourceId": text(row.get("stableEventId") or row.get("id")),
        })
        event_registry[event_url] = page_meta
        event_count += 1

    for symbol, symbol_rows in stock_rows.items():
        symbol_rows.sort(key=lambda row: text(row.get("publishedAt")), reverse=True)
        path = safe_url(symbol_rows[0].get("stockHubUrl"), f"/stocks/{slugify(symbol)}/")
        target = ROOT / path.strip("/") / "index.html"
        rendered = build_stock_page(symbol, symbol_rows, header, footer, updated_at)
        previous_meta = stock_registry.get(path, {}) if isinstance(stock_registry.get(path), dict) else {}
        stock_registry[path] = write_page_if_changed(target, rendered, previous_meta, build_date)

    for category, grouped in category_rows.items():
        grouped.sort(key=lambda row: text(row.get("publishedAt")), reverse=True)
        path = safe_url(grouped[0].get("categoryUrl"), f"/stock-triggers/category/{slugify(category)}/")
        target = ROOT / path.strip("/") / "index.html"
        rendered = build_category_page(category, grouped, header, footer, updated_at)
        previous_meta = category_registry.get(path, {}) if isinstance(category_registry.get(path), dict) else {}
        category_registry[path] = write_page_if_changed(target, rendered, previous_meta, build_date)

    methodology_path = "/stock-triggers/methodology/"
    methodology_target = METHOD_DIR / "index.html"
    methodology_rendered = build_methodology_page(payload, header, footer)
    methodology_registry = write_page_if_changed(
        methodology_target,
        methodology_rendered,
        methodology_registry if isinstance(methodology_registry, dict) else {},
        build_date,
    )

    redirect_count = update_redirects(rows, build_date)
    sitemap_count = update_sitemap(
        event_registry=event_registry,
        stock_registry=stock_registry,
        category_registry=category_registry,
        main_lastmod=data_lastmod,
        methodology_lastmod=text(methodology_registry.get("lastmod")) or build_date,
    )
    manifest = {
        "updatedAt": updated_at,
        "generatedAt": payload.get("generatedAt"),
        "eventPagesUpdatedOrChecked": event_count,
        "eventPagesKnown": len(event_registry),
        "stockHubsKnown": len(stock_registry),
        "categoryPagesKnown": len(category_registry),
        "redirects": redirect_count,
        "sitemapEntries": sitemap_count,
        "sitemapFile": "/sitemap-stock-triggers.xml",
        "eventDirectory": "/stock-triggers/events/",
        "stockDirectory": "/stocks/",
        "urlPolicy": "stable-company-date-id-v2",
        "eventRegistry": event_registry,
        "stockRegistry": stock_registry,
        "categoryRegistry": category_registry,
        "methodologyRegistry": methodology_registry,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "events": event_count,
        "stocks": len(stock_rows),
        "categories": len(category_rows),
        "sitemap": sitemap_count,
        "redirects": redirect_count,
    }


def main() -> int:
    stats = build_pages()
    print(
        f"Generated {stats['events']} event pages, {stats['stocks']} stock hubs, "
        f"{stats['categories']} category pages, {stats['sitemap']} sitemap entries and {stats['redirects']} redirects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
