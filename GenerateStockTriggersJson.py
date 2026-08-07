"""
GenerateStockTriggersJson.py

Dynamic Stock Trigger Intelligence generator for Automation In Trade.

The generator runs as part of UpdateAllData.py and publishes:
    market-data/stock-triggers.json

Primary source:
- NSE corporate announcements endpoint (date-window CSV/JSON).

Additional source:
- The already generated market-data/corporate-actions.json file.

Resilience:
- New records are merged with the previous trigger file.
- If NSE is temporarily unavailable, recent previous records are preserved.
- Corporate-action triggers continue to be rebuilt from local JSON.
- The output records source health and stale/fallback state for the UI.

Commands:
    python GenerateStockTriggersJson.py
    python GenerateStockTriggersJson.py --days 7
    python GenerateStockTriggersJson.py --symbols RELIANCE,TCS
    python GenerateStockTriggersJson.py --source-file sample-announcements.csv
    python GenerateStockTriggersJson.py --offline

Optional AI enrichment:
- Set GEMINI_API_KEY and AIT_TRIGGER_AI_ENABLED=true.
- Set GEMINI_MODEL if a model other than gemini-2.5-flash is required.
- AI enrichment is non-blocking; deterministic summaries are always available.

Important:
- This tool republishes short, transformed summaries and links users to the
  original exchange/company filing. Review exchange data licensing and usage
  terms before commercial redistribution at scale.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlparse

import requests

try:
    from pypdf import PdfReader
except ImportError:  # Optional at runtime; the generator remains functional without PDF extraction.
    PdfReader = None

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "market-data" / "stock-triggers.json"
CORPORATE_ACTIONS_FILE = ROOT / "market-data" / "corporate-actions.json"
STOCK_INDEX_FILE = ROOT / "market-data" / "stock-research-index.json"
JOB_RUNS_FILE = ROOT / "market-data" / "stock-trigger-job-runs.json"
STRENGTH_FILE = ROOT / "market-data" / "stock-strength-ranker.json"
VOLUME_FILE = ROOT / "market-data" / "volume-surge-scanner.json"
MOMENTUM_FILE = ROOT / "market-data" / "bullish-bearish-momentum-scanner.json"
FILING_CACHE_FILE = ROOT / "market-data" / "stock-trigger-filing-cache.json"

NSE_HOME_URL = "https://www.nseindia.com/"
NSE_ANNOUNCEMENTS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_ANNOUNCEMENTS_API = os.getenv(
    "NSE_ANNOUNCEMENTS_API",
    "https://www.nseindia.com/api/corporate-announcements",
).strip()

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_RETENTION_DAYS = 120
DEFAULT_MAX_ITEMS = 500
REQUEST_TIMEOUT_SECONDS = 18
MAX_FILING_BYTES = 10 * 1024 * 1024
MAX_FILING_TEXT_CHARS = 18000
DEFAULT_FILING_EXTRACT_LIMIT = int(os.getenv("AIT_TRIGGER_FILING_EXTRACT_LIMIT", "35") or 35)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_ANNOUNCEMENTS_PAGE,
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

CATEGORY_RULES: Sequence[Tuple[str, str, Sequence[str], int]] = (
    (
        "ORDER_WIN",
        "Large Order / Contract",
        (
            "purchase order", "work order", "order received", "order win", "order bagged",
            "awarded contract", "contract awarded", "letter of award", "letter of intent",
            "new order", "bagging/receiving of orders", "project awarded", "contract received",
        ),
        18,
    ),
    (
        "RESULTS",
        "Quarterly / Financial Results",
        (
            "financial results", "quarterly results", "audited results", "unaudited results",
            "results for the quarter", "earnings", "integrated filing financial",
        ),
        16,
    ),
    (
        "GUIDANCE",
        "Guidance / Business Outlook",
        (
            "guidance", "business outlook", "revenue target", "margin guidance", "growth target",
            "order book guidance", "management outlook", "investor presentation",
        ),
        15,
    ),
    (
        "EXPANSION",
        "Capacity Expansion / New Facility",
        (
            "capacity expansion", "new plant", "new facility", "commissioning", "commercial production",
            "production commenced", "capacity addition", "greenfield", "brownfield", "new unit",
        ),
        16,
    ),
    (
        "ACQUISITION_PARTNERSHIP",
        "Acquisition / Partnership",
        (
            "acquisition", "acquire", "joint venture", "strategic partnership", "collaboration",
            "memorandum of understanding", "mou", "merger", "demerger", "business transfer",
        ),
        15,
    ),
    (
        "PROMOTER_ACTIVITY",
        "Promoter / Insider Activity",
        (
            "promoter", "insider trading", "pledge", "encumbrance", "open market purchase",
            "open market sale", "regulation 7(2)", "sast", "takeover regulations",
        ),
        14,
    ),
    (
        "INVESTOR_MEETING",
        "Investor Meeting / Conference Call",
        (
            "analyst meet", "analysts/institutional investor meet", "investor meet",
            "conference call", "con. call", "earnings call", "audio recording",
            "link of recording", "recording of conference call", "transcript",
        ),
        20,
    ),
    (
        "INSTITUTIONAL_ACTIVITY",
        "Institutional / Fund Activity",
        (
            "institutional investor", "mutual fund", "foreign portfolio investor", "fpi",
            "qualified institutional", "qip", "bulk deal", "block deal", "fund holding",
        ),
        10,
    ),
    (
        "CREDIT_RATING",
        "Credit Rating Change",
        (
            "credit rating", "rating upgrade", "rating downgrade", "ratings revised",
            "rating reaffirmed", "credit ratings",
        ),
        13,
    ),
    (
        "FUND_RAISE",
        "Fund Raise / Dilution",
        (
            "fund raising", "fund raise", "preferential issue", "qualified institutions placement",
            "rights issue", "warrants", "allotment of shares", "issue of securities", "debt issuance",
        ),
        13,
    ),
    (
        "MANAGEMENT_CHANGE",
        "Management / Auditor Change",
        (
            "resignation", "appointment", "change in management", "chief financial officer",
            "managing director", "chief executive officer", "company secretary", "auditor",
            "key managerial personnel", "director",
        ),
        12,
    ),
    (
        "REGULATORY_LEGAL",
        "Regulatory / Legal Development",
        (
            "regulatory", "penalty", "show cause", "tax demand", "litigation", "legal proceeding",
            "sebi order", "investigation", "inspection", "search operation", "fine imposed",
        ),
        13,
    ),
    (
        "CORPORATE_ACTION",
        "Corporate Action",
        (
            "dividend", "bonus", "stock split", "sub-division", "buyback", "record date",
            "rights issue", "face value", "capital reduction",
        ),
        12,
    ),
)

POSITIVE_TERMS = (
    "order received", "received a purchase order", "purchase order worth", "contract awarded", "new order",
    "awarded", "upgrade", "growth", "profit increase", "revenue increase",
    "commissioning", "commercial production", "acquisition", "partnership", "dividend",
    "buyback", "promoter purchase", "debt reduction", "record order book", "expansion",
)
NEGATIVE_TERMS = (
    "downgrade", "resignation", "penalty", "default", "loss", "decline", "cancelled",
    "cancellation", "pledge", "encumbrance", "promoter sale", "tax demand", "investigation",
    "fraud", "insolvency", "liquidation", "fire incident", "shutdown", "suspension",
)

MATERIAL_GENERIC_SUBJECTS = (
    "outcome of board meeting", "general updates", "press release", "investor presentation",
    "corporate announcement", "other business matters",
)

WHY_IT_MATTERS = {
    "ORDER_WIN": "A meaningful order can improve revenue visibility and the future order book, but execution timing and margins still matter.",
    "RESULTS": "Financial results reveal current growth, profitability, margins and balance-sheet trends. Compare the numbers with prior periods and expectations.",
    "GUIDANCE": "Management guidance can reset market expectations. Track whether future results support the stated targets.",
    "EXPANSION": "New capacity may support future growth, but utilisation, funding, commissioning delays and demand determine the real benefit.",
    "ACQUISITION_PARTNERSHIP": "The transaction may expand products, customers or geography. Valuation, integration and execution risks should be checked.",
    "PROMOTER_ACTIVITY": "Promoter and insider transactions can change ownership signals. The size, route and reason are more important than the headline alone.",
    "INVESTOR_MEETING": "The meeting or recording can contain useful management commentary, but scheduling or publishing a call is not itself a business event or proof of institutional buying.",
    "INSTITUTIONAL_ACTIVITY": "Institutional activity may improve market attention, but meetings and placements are not automatic confirmation of buying.",
    "CREDIT_RATING": "A rating change can affect borrowing cost, lender confidence and refinancing ability. Read the rating rationale and outlook.",
    "FUND_RAISE": "Fresh capital can fund growth or reduce debt, while equity issuance may dilute existing shareholders. Check price, size and purpose.",
    "MANAGEMENT_CHANGE": "Leadership or auditor changes can affect governance and execution. Review the reason, replacement and transition timeline.",
    "REGULATORY_LEGAL": "Regulatory or legal developments can create financial and reputational risk. Verify the amount, stage and company response.",
    "CORPORATE_ACTION": "Corporate actions change eligibility, price or share quantity mechanics, but do not automatically create shareholder wealth.",
    "OTHER_MATERIAL": "The filing may affect business expectations or governance. Read the original disclosure before drawing a conclusion.",
}

RISK_NOTES = {
    "ORDER_WIN": "Check order size versus annual revenue, execution period, cancellation clauses and working-capital requirements.",
    "RESULTS": "One quarter may be affected by seasonality or one-off items; inspect cash flow, margins and management commentary.",
    "GUIDANCE": "Guidance is forward-looking and may be revised if demand, costs or execution change.",
    "EXPANSION": "Project delays, cost overruns, low utilisation and debt-funded capex can reduce the expected benefit.",
    "ACQUISITION_PARTNERSHIP": "Strategic announcements may take time to close and may not produce the expected synergies.",
    "PROMOTER_ACTIVITY": "Small transactions can be immaterial; verify quantity, percentage holding and whether shares are pledged.",
    "INVESTOR_MEETING": "Check the transcript or recording for genuinely new guidance, order-book information, capital-allocation changes or risks. A recording link alone has low materiality.",
    "INSTITUTIONAL_ACTIVITY": "An investor meeting or QIP process does not prove sustained institutional accumulation.",
    "CREDIT_RATING": "Read the complete rating rationale; reaffirmation may still include a negative outlook or elevated leverage.",
    "FUND_RAISE": "Review dilution, issue price, end use, debt obligations and shareholder approvals.",
    "MANAGEMENT_CHANGE": "Unexpected resignations can be a warning, but routine appointments may have limited financial impact.",
    "REGULATORY_LEGAL": "The final liability may differ from the disclosed demand or allegation; follow subsequent appeals and orders.",
    "CORPORATE_ACTION": "Verify ex-date, record date, ratio and eligibility from the original exchange filing.",
    "OTHER_MATERIAL": "The headline may omit conditions or limitations contained in the attached filing.",
}


# Version 2 separates the final materiality score into visible, auditable
# components. Category alone can no longer make most events look identical.
SCORING_MODEL_VERSION = "2.0"

CATEGORY_MATERIALITY_BASE: Dict[str, int] = {
    "ORDER_WIN": 24,
    "RESULTS": 26,
    "GUIDANCE": 22,
    "EXPANSION": 22,
    "ACQUISITION_PARTNERSHIP": 24,
    "PROMOTER_ACTIVITY": 18,
    "INVESTOR_MEETING": 5,
    "INSTITUTIONAL_ACTIVITY": 16,
    "CREDIT_RATING": 18,
    "FUND_RAISE": 21,
    "MANAGEMENT_CHANGE": 14,
    "REGULATORY_LEGAL": 22,
    "CORPORATE_ACTION": 10,
    "OTHER_MATERIAL": 8,
}

CATEGORY_MATERIALITY_REASON: Dict[str, str] = {
    "ORDER_WIN": "Orders can affect future revenue visibility, subject to size and execution terms.",
    "RESULTS": "Quarterly results directly reveal growth, margin and profit quality.",
    "GUIDANCE": "Guidance can change future expectations but remains forward-looking.",
    "EXPANSION": "Capacity additions can affect future growth after commissioning and utilisation.",
    "ACQUISITION_PARTNERSHIP": "Transactions can alter business scale, products or geography.",
    "PROMOTER_ACTIVITY": "Ownership changes matter only when transaction size and intent are meaningful.",
    "INVESTOR_MEETING": "A meeting, call or recording is informational until it contains a new material disclosure.",
    "INSTITUTIONAL_ACTIVITY": "Actual fund transactions or placements can affect ownership and liquidity.",
    "CREDIT_RATING": "Ratings can influence borrowing cost and refinancing access.",
    "FUND_RAISE": "Capital raising affects funding capacity and may dilute shareholders.",
    "MANAGEMENT_CHANGE": "Leadership or auditor changes may affect governance and execution.",
    "REGULATORY_LEGAL": "Legal or regulatory developments can create financial and reputational risk.",
    "CORPORATE_ACTION": "Corporate actions affect eligibility or capital structure; materiality depends on type and terms.",
    "OTHER_MATERIAL": "The filing requires additional facts before its business impact can be judged.",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def format_ist(dt: Optional[datetime] = None) -> str:
    return (dt or now_ist()).strftime("%d-%b-%Y %H:%M IST")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip(" ,;:-") + "…"


def safe_json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def normalise_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def get_field(row: Dict[str, Any], *candidates: str) -> Any:
    normalised = {normalise_key(k): v for k, v in row.items()}
    for candidate in candidates:
        key = normalise_key(candidate)
        if key in normalised and normalised[key] not in (None, "", "-"):
            return normalised[key]
    return ""


def parse_datetime_flexible(value: Any) -> Optional[datetime]:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("T", " ").replace("Z", "")
    formats = (
        "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d %b %Y %H:%M:%S", "%d %b %Y %H:%M", "%d %b %Y",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=IST)
        except ValueError:
            continue
    match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?", text)
    if match:
        return parse_datetime_flexible(" ".join(part for part in match.groups() if part))
    return None


def iso_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.astimezone(IST).isoformat(timespec="seconds")


def is_http_url(value: Any) -> bool:
    url = clean_text(value)
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_direct_filing_url(value: Any) -> bool:
    url = clean_text(value)
    if not is_http_url(url):
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "nsearchives.nseindia.com" in host:
        return True
    if re.search(r"\.(pdf|xml|html?|zip)(?:$|[?#])", url, re.I):
        return True
    # Company-hosted filing links are accepted, but generic NSE listing pages are not
    # labelled as an original filing.
    return "nseindia.com" not in host and any(
        token in path for token in ("filing", "announcement", "investor", "result", "press")
    )


def canonical_attachment(value: Any) -> str:
    """Return only a genuine, clickable filing URL.

    NSE's CSV export has occasionally shifted columns and placed a date/time in
    the attachment field. Returning that raw value created localhost paths such
    as /stock-triggers/31-Jul-2026%2013:50:15. Invalid values are now rejected.
    """
    url = clean_text(value).strip("\"'")
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://nsearchives.nseindia.com" + url
    elif not is_http_url(url) and re.search(r"\.(pdf|xml|html?|zip)(?:$|[?#])", url, re.I):
        url = "https://nsearchives.nseindia.com/" + url.lstrip("/")
    return url if is_direct_filing_url(url) else ""


def find_attachment_url(row: Dict[str, Any]) -> str:
    preferred = get_field(
        row,
        "ATTACHMENT", "attachment", "fileUrl", "pdfUrl", "attchmntFile",
        "attachmentFile", "attachment_url", "fileName", "filePath",
    )
    attachment = canonical_attachment(preferred)
    if attachment:
        return attachment
    # Defensive recovery for NSE schema changes: scan all values, but accept only
    # URLs/filenames that pass the direct-filing validator.
    for value in row.values():
        attachment = canonical_attachment(value)
        if attachment:
            return attachment
    return ""


def load_stock_map() -> Dict[str, Dict[str, Any]]:
    payload = safe_json_load(STOCK_INDEX_FILE, {})
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("stocks", []) if isinstance(payload, dict) else []:
        symbol = clean_text(item.get("symbol")).upper()
        if not symbol:
            continue
        result[symbol] = {
            "stockName": clean_text(item.get("stockName")) or symbol,
            "cmp": item.get("cmp"),
            "changePct": item.get("changePct"),
            "indices": item.get("indices") or [],
            "isFree": bool(item.get("isFree")),
            "accessTier": item.get("accessTier") or "premium",
            "profileUrl": technical_profile_url(item),
        }

    def merge_scanner(path: Path, fields: Sequence[str]) -> None:
        scanner = safe_json_load(path, {})
        updated_at = clean_text(scanner.get("updatedAt")) if isinstance(scanner, dict) else ""
        rows = scanner.get("stocks", []) if isinstance(scanner, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = clean_text(row.get("symbol")).upper()
            if not symbol:
                continue
            target = result.setdefault(symbol, {
                "stockName": clean_text(row.get("stockName")) or symbol,
                "cmp": row.get("cmp"),
                "changePct": row.get("changePct"),
                "indices": row.get("indices") or [],
                "isFree": False,
                "accessTier": "premium",
                "profileUrl": "/technical-analysis/",
            })
            if not target.get("stockName") or target.get("stockName") == symbol:
                target["stockName"] = clean_text(row.get("stockName")) or symbol
            for common in ("cmp", "changePct"):
                if row.get(common) not in (None, ""):
                    target[common] = row.get(common)
            if row.get("indices"):
                target["indices"] = list(dict.fromkeys((target.get("indices") or []) + list(row.get("indices") or [])))
            for field in fields:
                if row.get(field) not in (None, ""):
                    target[field] = row.get(field)
            if updated_at:
                target.setdefault("marketContextUpdatedAt", updated_at)

    merge_scanner(STRENGTH_FILE, ("strengthScore", "rank", "status", "signal"))
    merge_scanner(VOLUME_FILE, ("volumeSurgeRatio", "volumeScore", "volumeSource", "signal"))
    merge_scanner(MOMENTUM_FILE, ("momentumScore", "bias", "rank"))
    return result


def technical_profile_url(item: Dict[str, Any]) -> str:
    name = clean_text(item.get("stockName") or item.get("symbol") or "stock")
    name = re.sub(r"\b(limited|ltd\.?|inc\.?|company|co\.?|corporation|corp\.?)\b", "", name, flags=re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"/technical-analysis/{slug}-technical-analysis/" if slug else "/technical-analysis/"


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def response_to_rows(response: requests.Response) -> List[Dict[str, Any]]:
    content_type = (response.headers.get("content-type") or "").lower()
    text = response.text.lstrip("\ufeff").strip()
    if not text:
        return []

    if "json" in content_type or text.startswith("[") or text.startswith("{"):
        payload = response.json()
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("data", "rows", "announcements", "records"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
            # Some NSE endpoints use a nested object with a data array.
            for value in payload.values():
                if isinstance(value, dict) and isinstance(value.get("data"), list):
                    return [row for row in value["data"] if isinstance(row, dict)]
        return []

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def fetch_nse_announcements(from_date: date, to_date: date) -> Tuple[List[Dict[str, Any]], str]:
    session = build_session()

    def warm_up() -> None:
        # The filing page is a better cookie/referrer warm-up than the generic
        # homepage. Home remains a fallback because NSE occasionally redirects.
        for url in (NSE_ANNOUNCEMENTS_PAGE, NSE_HOME_URL):
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
                if response.ok:
                    return
            except requests.RequestException:
                continue

    warm_up()
    base_params = {
        "index": "equities",
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }
    # JSON is requested first. NSE's CSV export has occasionally returned
    # shifted columns, which can place timestamps in the attachment field.
    attempts = [base_params, dict(base_params, csv="true")]
    errors: List[str] = []

    for params in attempts:
        try:
            response = session.get(
                NSE_ANNOUNCEMENTS_API,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={
                    **HEADERS,
                    "Accept": "text/csv,text/plain,*/*" if params.get("csv") else "application/json,text/plain,*/*",
                    "Referer": NSE_ANNOUNCEMENTS_PAGE,
                },
            )
            if response.status_code in {401, 403}:
                warm_up()
                response = session.get(
                    NSE_ANNOUNCEMENTS_API,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers={
                        **HEADERS,
                        "Accept": "text/csv,text/plain,*/*" if params.get("csv") else "application/json,text/plain,*/*",
                        "Referer": NSE_ANNOUNCEMENTS_PAGE,
                    },
                )
            response.raise_for_status()
            rows = response_to_rows(response)
            if rows:
                sample = rows[: min(100, len(rows))]
                usable = sum(
                    1
                    for row in sample
                    if clean_text(get_field(row, "SYMBOL", "symbol", "ticker"))
                    and clean_text(get_field(row, "SUBJECT", "subject", "purpose", "desc"))
                )
                dated = sum(
                    1
                    for row in sample
                    if parse_datetime_flexible(
                        get_field(
                            row,
                            "BROADCAST DATE/TIME", "broadcastDate", "broadcastDateTime", "broadcast",
                            "sort_date", "DISSEMINATION DATE/TIME", "disseminationDate", "date",
                            "timestamp", "an_dt", "dt",
                        )
                    )
                )
                if (
                    usable >= max(1, int(len(sample) * 0.65))
                    and dated >= max(1, int(len(sample) * 0.35))
                ):
                    return rows, str(response.url)
                errors.append(
                    f"rejected malformed announcement schema from {response.url}: "
                    f"usable={usable}/{len(sample)}, dated={dated}/{len(sample)}"
                )
                continue
            errors.append(f"empty response from {response.url}")
        except Exception as exc:
            errors.append(clean_text(exc))

    raise RuntimeError("; ".join(error for error in errors if error) or "NSE announcement response contained no rows")


def load_source_file(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json" or raw.lstrip().startswith(("[", "{")):
        payload = json.loads(raw)
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key in ("data", "rows", "announcements", "records"):
                if isinstance(payload.get(key), list):
                    return [r for r in payload[key] if isinstance(r, dict)]
        return []
    return [dict(row) for row in csv.DictReader(io.StringIO(raw))]


def classify_trigger(subject: str, details: str) -> Tuple[str, str, int, List[str]]:
    combined = f"{subject} {details}".lower()
    best: Optional[Tuple[str, str, int, List[str]]] = None
    for code, label, keywords, weight in CATEGORY_RULES:
        matched = [keyword for keyword in keywords if keyword in combined]
        if not matched:
            continue
        score = weight + min(12, len(matched) * 3)
        candidate = (code, label, score, matched[:5])
        if best is None or candidate[2] > best[2]:
            best = candidate
    if best:
        return best
    return "OTHER_MATERIAL", "Other Material Update", 4, []


def is_material(subject: str, details: str, category: str) -> bool:
    if category != "OTHER_MATERIAL":
        return True
    combined = f"{subject} {details}".lower()
    if any(term in combined for term in MATERIAL_GENERIC_SUBJECTS):
        # Generic announcements are retained only when they contain additional
        # business-impact terms rather than pure compliance boilerplate.
        business_terms = (
            "order", "contract", "revenue", "profit", "capacity", "acquisition", "investment",
            "fund", "dividend", "buyback", "rating", "resignation", "penalty", "guidance",
        )
        return any(term in combined for term in business_terms)
    return len(details) >= 80


def determine_sentiment(subject: str, details: str) -> Tuple[str, int, List[str]]:
    combined = f"{subject} {details}".lower()
    positive = [term for term in POSITIVE_TERMS if term in combined]
    negative = [term for term in NEGATIVE_TERMS if term in combined]
    if positive and negative:
        return "Mixed", 0, (positive[:2] + negative[:2])
    if negative:
        return "Caution", -8, negative[:4]
    if positive:
        return "Positive", 7, positive[:4]
    return "Neutral", 0, []


def extract_highlights(text: str) -> List[str]:
    highlights: List[str] = []
    patterns = (
        r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?\s*(?:crore|cr|lakh|million|billion)?",
        r"[\d,]+(?:\.\d+)?\s*(?:crore|cr|lakh|million|billion)",
        r"(?:₹|Rs\.?)\s*[\d,]+(?:\.\d+)?\s*(?:per\s+share|/\s*share)",
        r"\b\d{1,4}\s*[:/]\s*\d{1,4}\b",
        r"\b\d+(?:\.\d+)?%\b",
        r"\b(?:FY|Q)[1-4]?\s*20\d{2}(?:[-–/]\d{2,4})?\b",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            value = clean_text(match)
            if value and value.lower() not in {v.lower() for v in highlights}:
                highlights.append(value)
            if len(highlights) >= 4:
                return highlights
    return highlights


GENERIC_SUBJECTS = {
    "press release", "updates", "general updates", "announcement", "outcome of board meeting",
    "other", "newspaper publication", "copy of newspaper publication",
}


def extract_disclosure_title(details: str) -> str:
    value = clean_text(details)
    patterns = (
        r"\btitled\s+[\"'](.{8,220}?)(?:[\"']|$)",
        r"\btitle(?:d)?\s*[:\-]\s*([^.;]{8,220})",
        r"\bregarding\s+(?:a\s+|an\s+|the\s+)?(.{12,220})",
    )
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.I)
        if not match:
            continue
        title = clean_text(match.group(1)).strip(" .,:;\"'")
        title = re.sub(r"\s+(?:dated|submitted)\s+\w+\s+\d{1,2}.*$", "", title, flags=re.I)
        if len(title) >= 8:
            return truncate(title, 150)
    return ""


def refine_subject(subject: str, details: str, category: str = "") -> str:
    current = clean_text(subject) or "Corporate development"
    if current.lower() not in GENERIC_SUBJECTS and len(current) > 12:
        return current
    title = extract_disclosure_title(details)
    if title and title.lower() != current.lower():
        return title
    labels = {
        "RESULTS": "Financial Results / Earnings Update",
        "ORDER_WIN": "Order / Contract Update",
        "GUIDANCE": "Business Outlook / Investor Presentation",
        "EXPANSION": "Capacity Expansion Update",
        "ACQUISITION_PARTNERSHIP": "Acquisition / Partnership Update",
        "CREDIT_RATING": "Credit Rating Update",
        "FUND_RAISE": "Fund-Raising Update",
        "MANAGEMENT_CHANGE": "Management / Governance Update",
        "REGULATORY_LEGAL": "Regulatory / Legal Update",
        "INVESTOR_MEETING": "Investor Meeting / Conference Call",
    }
    return labels.get(category, current)


def strip_exchange_boilerplate(company: str, details: str) -> str:
    value = clean_text(details)
    if not value:
        return ""
    company_pattern = re.escape(clean_text(company)) if company else r".+?"
    value = re.sub(
        rf"^{company_pattern}\s+has\s+informed\s+the\s+Exchange\s+(?:regarding|about)\s+",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.I)
    return clean_text(value)


def deterministic_summary(company: str, subject: str, details: str) -> str:
    subject = clean_text(subject)
    details = clean_text(details)
    concise = strip_exchange_boilerplate(company, details)
    title = extract_disclosure_title(details)
    if title:
        return truncate(f"{company} filed an official update titled ‘{title}’.", 320)
    if concise and concise.lower() != subject.lower():
        return truncate(f"{company}: {concise}", 320)
    if details:
        return truncate(details, 320)
    return truncate(f"{company} disclosed {subject} through an exchange filing.", 320)


def filing_cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def normalise_filing_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"(?<=\w)-\s+(?=\w)", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return clean_text(value)


def extract_pdf_text(content: bytes) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
        chunks: List[str] = []
        for page in list(reader.pages)[:8]:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if page_text:
                chunks.append(page_text)
            if sum(len(chunk) for chunk in chunks) >= MAX_FILING_TEXT_CHARS:
                break
        return normalise_filing_text(" ".join(chunks))[:MAX_FILING_TEXT_CHARS]
    except Exception:
        return ""


def fetch_filing_text(session: requests.Session, url: str) -> str:
    if not is_direct_filing_url(url):
        return ""
    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={
            **HEADERS,
            "Accept": "application/pdf,text/html,text/plain,*/*",
            "Referer": NSE_ANNOUNCEMENTS_PAGE,
        },
        stream=True,
    )
    response.raise_for_status()
    content_length = safe_float(response.headers.get("content-length"))
    if content_length and content_length > MAX_FILING_BYTES:
        return ""
    content = response.content
    if len(content) > MAX_FILING_BYTES:
        return ""
    content_type = clean_text(response.headers.get("content-type")).lower()
    if "pdf" in content_type or url.lower().split("?", 1)[0].endswith(".pdf"):
        return extract_pdf_text(content)
    decoded = content.decode(response.encoding or "utf-8", errors="ignore")
    decoded = re.sub(r"<(script|style)\b.*?</\1>", " ", decoded, flags=re.I | re.S)
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    return normalise_filing_text(decoded)[:MAX_FILING_TEXT_CHARS]


def filing_key_sentences(text: str, category: str, limit: int = 3) -> List[str]:
    cleaned = normalise_filing_text(text)
    if len(cleaned) < 80:
        return []
    category_terms = {
        "RESULTS": ("revenue", "income", "ebitda", "profit", "pat", "margin", "quarter", "year ended"),
        "ORDER_WIN": ("order", "contract", "awarded", "value", "crore", "execution"),
        "GUIDANCE": ("guidance", "outlook", "expects", "target", "growth", "margin", "capacity"),
        "EXPANSION": ("capacity", "plant", "facility", "commission", "investment", "production"),
        "ACQUISITION_PARTNERSHIP": ("acquisition", "stake", "partnership", "joint venture", "consideration"),
        "CREDIT_RATING": ("rating", "upgrade", "downgrade", "outlook", "reaffirmed"),
        "FUND_RAISE": ("fund", "issue", "allotment", "qip", "rights", "proceeds"),
        "MANAGEMENT_CHANGE": ("appointed", "resigned", "director", "officer", "auditor", "effective"),
        "REGULATORY_LEGAL": ("order", "penalty", "notice", "regulatory", "court", "tribunal"),
    }.get(
        category,
        ("revenue", "profit", "order", "capacity", "investment", "appointed", "penalty", "effective"),
    )
    noise = (
        "registered office", "corporate identity", "cin:", "www.", "email:", "telephone",
        "disclaimer", "safe harbour", "page ",
    )
    sentence_text = re.sub(r"\b(Rs|No|Ltd|Mr|Ms|Dr)\.", r"\1", cleaned)
    candidates: List[Tuple[int, int, str]] = []
    for idx, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\s+[•▪]\s+", sentence_text)):
        sentence = clean_text(sentence).strip(" -•")
        if len(sentence) < 35 or len(sentence) > 520:
            continue
        lower = sentence.lower()
        if any(token in lower for token in noise):
            continue
        score = sum(4 for token in category_terms if token in lower)
        if re.search(
            r"(?:₹|rs\.?|inr)\s*[\d,]+|\b[\d,.]+\s*(?:crore|cr|lakh|million|billion|%)",
            lower,
            re.I,
        ):
            score += 7
        if re.search(r"\b(?:q[1-4]|fy\s*\d{2,4}|quarter|year ended|effective from)\b", lower, re.I):
            score += 3
        if score > 0:
            candidates.append((score, -idx, sentence))
    candidates.sort(reverse=True)
    selected: List[Tuple[int, str]] = []
    seen: set[str] = set()
    for _score, neg_idx, sentence in candidates:
        fingerprint = re.sub(r"[^a-z0-9]", "", sentence.lower())[:100]
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        selected.append((-neg_idx, truncate(sentence, 360)))
        if len(selected) >= limit:
            break
    selected.sort(key=lambda item: item[0])
    return [sentence for _idx, sentence in selected]


def enrich_with_filing_text(items: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], int]:
    if limit <= 0:
        return items, 0
    cache_payload = safe_json_load(FILING_CACHE_FILE, {})
    cache = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
    if not isinstance(cache, dict):
        cache = {}
    session = build_session()
    extracted_count = 0
    attempted = 0
    for item in items:
        if attempted >= limit:
            break
        if item.get("sourceType") != "NSE Corporate Announcement":
            continue
        attachment = canonical_attachment(item.get("attachmentUrl") or item.get("sourceUrl"))
        if not attachment:
            continue
        generic = (
            clean_text(item.get("rawSubject") or item.get("subject")).lower() in GENERIC_SUBJECTS
            or len(clean_text(item.get("detailsText"))) < 180
        )
        key = filing_cache_key(attachment)
        cached = cache.get(key) if isinstance(cache.get(key), dict) else {}
        filing_text = clean_text(cached.get("text"))
        if not filing_text and not generic:
            continue
        if not filing_text:
            attempted += 1
            try:
                filing_text = fetch_filing_text(session, attachment)
            except Exception as exc:
                cache[key] = {
                    "url": attachment,
                    "text": "",
                    "error": truncate(clean_text(exc), 220),
                    "updatedAt": format_ist(),
                }
                continue
            cache[key] = {
                "url": attachment,
                "text": filing_text,
                "error": "",
                "updatedAt": format_ist(),
            }
            time.sleep(0.08)
        facts = filing_key_sentences(filing_text, clean_text(item.get("category")))
        if not facts:
            continue
        item["filingExtracted"] = True
        item["filingKeyFacts"] = facts
        item["summary"] = truncate(" ".join(facts), 460)
        item["detailsText"] = truncate(" ".join(facts), 1400)
        item["summaryBasis"] = "Official filing text"
        item["highlights"] = extract_highlights(" ".join(facts))
        item["subject"] = refine_subject(
            clean_text(item.get("subject")),
            " ".join(facts),
            clean_text(item.get("category")),
        )
        extracted_count += 1
    FILING_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FILING_CACHE_FILE.write_text(
        json.dumps({"updatedAt": format_ist(), "entries": cache}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return items, extracted_count

def safe_float(value: Any) -> Optional[float]:
    try:
        number = float(str(value).replace(",", "").strip())
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def extract_amounts_crore(text: str) -> List[float]:
    """Extract approximate INR amounts and normalise them to crore.

    The function intentionally ignores bare numbers. A currency/unit marker is
    required so dates and share quantities do not inflate materiality.
    """
    values: List[float] = []
    pattern = re.compile(
        r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(crore|crores|cr\.?|lakh|lakhs|million|billion)\b",
        flags=re.I,
    )
    for match in pattern.finditer(clean_text(text)):
        amount = safe_float(match.group(1))
        unit = match.group(2).lower().rstrip(".")
        if amount is None:
            continue
        if unit in {"crore", "crores", "cr"}:
            crore = amount
        elif unit in {"lakh", "lakhs"}:
            crore = amount / 100.0
        elif unit == "million":
            crore = amount / 10.0
        else:  # billion INR
            crore = amount * 100.0
        if crore > 0:
            values.append(round(crore, 4))
    return sorted(set(values), reverse=True)[:5]


def extracted_percentages(text: str) -> List[float]:
    values: List[float] = []
    for raw in re.findall(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%", text):
        value = safe_float(raw)
        if value is not None and 0 <= value <= 1000:
            values.append(value)
    return sorted(set(values), reverse=True)[:6]


def extract_per_share_rupees(text: str) -> List[float]:
    values: List[float] = []
    patterns = (
        r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+share|/\s*share)",
        r"dividend\s*(?:of|-)\s*(?:₹|rs\.?)?\s*([\d,]+(?:\.\d+)?)",
    )
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I):
            value = safe_float(raw)
            if value is not None and 0 < value < 100000:
                values.append(value)
    return sorted(set(values), reverse=True)[:5]


def extract_action_ratios(text: str) -> List[str]:
    ratios: List[str] = []
    for left, right in re.findall(r"\b(\d{1,4})\s*[:/]\s*(\d{1,4})\b", text):
        value = f"{int(left)}:{int(right)}"
        if value not in ratios:
            ratios.append(value)
    return ratios[:4]


def score_band(score: int) -> str:
    if score >= 75:
        return "High materiality"
    if score >= 55:
        return "Moderate materiality"
    if score >= 35:
        return "Low materiality"
    return "Informational"


def category_materiality_score(category: str, subject: str, matched_signals: Sequence[str]) -> Tuple[int, str]:
    base = CATEGORY_MATERIALITY_BASE.get(category, 8)
    subject_lower = subject.lower()
    bonus = min(5, len(set(matched_signals)))

    if category == "CORPORATE_ACTION":
        if "buyback" in subject_lower:
            base = 18
        elif "rights" in subject_lower:
            base = 16
        elif any(term in subject_lower for term in ("bonus", "split", "sub-division")):
            base = 14
        elif "dividend" in subject_lower:
            base = 10
        elif "record date" in subject_lower:
            base = 6

    # Generic recordings/schedules should not be mistaken for institutional
    # accumulation or a fresh business development.
    if category == "INVESTOR_MEETING":
        if any(term in subject_lower for term in ("recording", "transcript", "schedule", "intimation")):
            bonus = min(bonus, 2)
        if any(term in subject_lower for term in ("guidance", "outlook", "order book", "capacity")):
            bonus += 3

    score = min(35, base + bonus)
    return score, CATEGORY_MATERIALITY_REASON.get(category, CATEGORY_MATERIALITY_REASON["OTHER_MATERIAL"])


def evidence_specificity_score(subject: str, details: str, highlights: Sequence[str], source_url: str) -> Tuple[int, str]:
    score = 0
    reasons: List[str] = []
    length = len(clean_text(details))
    if length >= 300:
        score += 8
        reasons.append("detailed disclosure text")
    elif length >= 150:
        score += 6
        reasons.append("adequate disclosure detail")
    elif length >= 70:
        score += 4
        reasons.append("some supporting detail")
    elif length >= 25:
        score += 2
        reasons.append("limited supporting detail")
    else:
        reasons.append("very little supporting detail")

    fact_points = min(7, len(highlights) * 2)
    score += fact_points
    if fact_points:
        reasons.append(f"{len(highlights)} concrete fact(s) extracted")

    if is_direct_filing_url(source_url):
        score += 3
        reasons.append("direct source filing available")
    elif is_http_url(source_url):
        score += 1
        reasons.append("official source page available")
    if not any(term in subject.lower() for term in MATERIAL_GENERIC_SUBJECTS):
        score += 2
    return min(20, score), "; ".join(reasons)


def financial_magnitude_score(category: str, combined_text: str) -> Tuple[int, str, List[float], List[float], List[float], List[str]]:
    amounts = extract_amounts_crore(combined_text)
    percentages = extracted_percentages(combined_text)
    per_share_values = extract_per_share_rupees(combined_text)
    action_ratios = extract_action_ratios(combined_text)
    largest = amounts[0] if amounts else 0.0

    if largest >= 5000:
        score = 20
    elif largest >= 1000:
        score = 17
    elif largest >= 500:
        score = 14
    elif largest >= 100:
        score = 11
    elif largest >= 25:
        score = 8
    elif largest >= 5:
        score = 5
    elif largest > 0:
        score = 3
    else:
        score = 0

    # Results/guidance can be meaningful when growth or margin percentages are
    # available even when no absolute rupee value appears in the announcement.
    if category in {"RESULTS", "GUIDANCE"} and percentages:
        score = max(score, min(12, 4 + len(percentages) * 2))
    elif category == "CORPORATE_ACTION":
        if per_share_values:
            value = per_share_values[0]
            if value >= 100:
                score = max(score, 8)
            elif value >= 50:
                score = max(score, 7)
            elif value >= 20:
                score = max(score, 6)
            elif value >= 10:
                score = max(score, 5)
            elif value >= 5:
                score = max(score, 4)
            else:
                score = max(score, 3)
        if action_ratios:
            score = max(score, 6)
        if percentages:
            score = max(score, min(8, 2 + len(percentages) * 2))

    if largest:
        reason = f"largest extracted monetary value is approximately ₹{largest:,.2f} crore"
    elif per_share_values:
        reason = f"corporate action value is ₹{per_share_values[0]:,.2f} per share"
    elif action_ratios:
        reason = f"corporate action ratio extracted: {', '.join(action_ratios)}"
    elif percentages:
        reason = f"{len(percentages)} percentage metric(s) extracted, but no reliable rupee magnitude"
    else:
        reason = "no reliable monetary or percentage magnitude was disclosed"
    return min(20, score), reason, amounts, percentages, per_share_values, action_ratios


def market_confirmation_score(stock: Dict[str, Any]) -> Tuple[int, str, Dict[str, Any]]:
    score = 0
    reasons: List[str] = []
    change = safe_float(stock.get("changePct"))
    volume_ratio = safe_float(stock.get("volumeSurgeRatio"))
    strength = safe_float(stock.get("strengthScore"))
    momentum = safe_float(stock.get("momentumScore"))

    if change is not None:
        absolute = abs(change)
        if absolute >= 8:
            score += 7
        elif absolute >= 5:
            score += 5
        elif absolute >= 3:
            score += 3
        elif absolute >= 1.5:
            score += 2
        reasons.append(f"daily move {change:+.2f}%")

    if volume_ratio is not None:
        if volume_ratio >= 3:
            score += 6
        elif volume_ratio >= 2:
            score += 4
        elif volume_ratio >= 1.5:
            score += 2
        reasons.append(f"volume {volume_ratio:.2f}× 20-day average")

    if strength is not None and strength >= 80:
        score += 2
        reasons.append(f"strength score {strength:.1f}")
    elif momentum is not None and momentum >= 85:
        score += 2
        reasons.append(f"momentum score {momentum:.1f}")

    context = {
        "changePct": change,
        "volumeSurgeRatio": volume_ratio,
        "strengthScore": strength,
        "momentumScore": momentum,
        "momentumBias": clean_text(stock.get("bias")),
        "strengthSignal": clean_text(stock.get("signal")),
        "updatedAt": clean_text(stock.get("marketContextUpdatedAt")),
    }
    return min(15, score), "; ".join(reasons) or "no current price/volume confirmation available", context


def recency_urgency_score(published_dt: Optional[datetime], days_to_action: Optional[int] = None) -> Tuple[int, str]:
    if days_to_action is not None:
        days = max(0, int(days_to_action))
        if days <= 2:
            return 10, f"action is due in {days} day(s)"
        if days <= 7:
            return 8, f"action is due within {days} days"
        if days <= 15:
            return 6, f"action is due within {days} days"
        if days <= 30:
            return 4, f"action is due within {days} days"
        return 2, f"action is {days} days away"

    if not published_dt:
        return 2, "publication time unavailable"
    age_days = max(0.0, (now_ist() - published_dt.astimezone(IST)).total_seconds() / 86400)
    if age_days <= 1:
        return 10, "published within the last 24 hours"
    if age_days <= 3:
        return 8, f"published {age_days:.1f} days ago"
    if age_days <= 7:
        return 6, f"published {age_days:.1f} days ago"
    if age_days <= 30:
        return 3, f"published {age_days:.0f} days ago"
    return 1, f"published {age_days:.0f} days ago"


def data_confidence_score(subject: str, details: str, highlights: Sequence[str], source_url: str, source_type: str) -> Tuple[int, List[str]]:
    score = 15 if "NSE" in source_type.upper() else 8
    limitations: List[str] = []
    length = len(clean_text(details))
    if length >= 250:
        score += 30
    elif length >= 100:
        score += 22
    elif length >= 40:
        score += 12
    else:
        score += 4
        limitations.append("The filing text contains little detail.")
    score += min(25, len(highlights) * 6)
    if not highlights:
        limitations.append("No reliable amount, percentage or reporting period was extracted.")
    if is_direct_filing_url(source_url):
        score += 20
    elif is_http_url(source_url):
        score += 8
        limitations.append("A direct attachment was unavailable; the official NSE announcement page is linked instead.")
    else:
        limitations.append("A direct source filing link is unavailable.")
    if any(term in subject.lower() for term in MATERIAL_GENERIC_SUBJECTS):
        score -= 8
        limitations.append("The subject is generic and may omit the actual business impact.")
    return max(10, min(100, score)), limitations


def calculate_trigger_intelligence(
    *,
    category: str,
    subject: str,
    details: str,
    highlights: Sequence[str],
    matched_signals: Sequence[str],
    stock: Dict[str, Any],
    published_dt: Optional[datetime],
    source_url: str,
    source_type: str,
    days_to_action: Optional[int] = None,
) -> Dict[str, Any]:
    combined = clean_text(f"{subject} {details}")
    business, business_reason = category_materiality_score(category, subject, matched_signals)
    evidence, evidence_reason = evidence_specificity_score(subject, details, highlights, source_url)
    magnitude, magnitude_reason, amounts, percentages, per_share_values, action_ratios = financial_magnitude_score(category, combined)
    market, market_reason, market_context = market_confirmation_score(stock)
    recency, recency_reason = recency_urgency_score(published_dt, days_to_action)

    total = max(0, min(100, business + evidence + magnitude + market + recency))
    confidence, limitations = data_confidence_score(subject, details, highlights, source_url, source_type)
    band = score_band(total)

    if category == "INVESTOR_MEETING" and magnitude == 0:
        limitations.insert(0, "The event is a meeting/recording update, not evidence of institutional buying or a change in business fundamentals.")
    if market == 0:
        limitations.append("No unusual price or volume confirmation was available in the latest scanner data.")

    breakdown = [
        {"id": "businessMateriality", "label": "Business materiality", "score": business, "max": 35, "reason": business_reason},
        {"id": "evidenceSpecificity", "label": "Evidence specificity", "score": evidence, "max": 20, "reason": evidence_reason},
        {"id": "financialMagnitude", "label": "Financial magnitude", "score": magnitude, "max": 20, "reason": magnitude_reason},
        {"id": "marketConfirmation", "label": "Market confirmation", "score": market, "max": 15, "reason": market_reason},
        {"id": "recencyUrgency", "label": "Recency / urgency", "score": recency, "max": 10, "reason": recency_reason},
    ]
    strongest = sorted(breakdown, key=lambda row: row["score"] / max(1, row["max"]), reverse=True)[:2]
    drivers = [f"{row['label']}: {row['reason']}" for row in strongest if row["score"] > 0]
    explanation = (
        f"{band}. The score is {total}/100 from business materiality {business}/35, evidence {evidence}/20, "
        f"financial magnitude {magnitude}/20, market confirmation {market}/15 and recency {recency}/10."
    )
    return {
        "impactScore": total,
        "materialityBand": band,
        "dataConfidence": confidence,
        "scoreVersion": SCORING_MODEL_VERSION,
        "scoreBreakdown": breakdown,
        "scoreExplanation": explanation,
        "scoreDrivers": drivers,
        "scoreLimitations": list(dict.fromkeys(limitations))[:5],
        "extractedFacts": {
            "amountsCrore": amounts,
            "largestAmountCrore": amounts[0] if amounts else None,
            "percentages": percentages,
            "perShareRupees": per_share_values,
            "actionRatios": action_ratios,
            "highlightCount": len(highlights),
        },
        "marketContext": market_context,
    }


def announcement_id(symbol: str, subject: str, published_at: str, attachment: str) -> str:
    raw = "|".join((symbol.upper(), subject.lower(), published_at, attachment)).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:18]


def normalise_source_identity(value: Any) -> str:
    """Return a stable source identity without query strings or fragments."""
    url = clean_text(value)
    if not is_http_url(url):
        return url.lower()
    parsed = urlparse(url)
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
    return f"{parsed.netloc.lower()}{path.lower()}"


def stable_event_id(
    symbol: str,
    *,
    exchange_event_id: Any = "",
    source_url: Any = "",
    published_at: Any = "",
    raw_subject: Any = "",
    action_date: Any = "",
) -> str:
    """Build a URL identity that does not depend on derived category/score text.

    The immutable-ish source path + published timestamp + raw exchange subject
    are used as the primary identity. NSE sequence ids are retained as metadata
    and only used as a last-resort fallback. This keeps migrated and future cron
    rows on exactly the same canonical URL.
    """
    exchange_id = clean_text(exchange_event_id)
    source_identity = normalise_source_identity(source_url)
    # Source path + exchange timestamp + raw exchange subject are deliberately
    # the primary identity. Older retained rows did not store NSE seq_id, so
    # preferring seq_id would change their URL the first time a fresh cron row
    # arrived. seq_id is used only as a last-resort fallback.
    if source_identity or clean_text(published_at) or clean_text(raw_subject):
        raw = "|".join((
            symbol.upper(),
            source_identity,
            clean_text(published_at),
            clean_text(action_date),
            clean_text(raw_subject).lower(),
        ))
    else:
        raw = f"nse|{symbol.upper()}|{exchange_id or 'event'}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def ensure_stable_event_identity(item: Dict[str, Any]) -> str:
    existing = clean_text(item.get("stableEventId"))
    if existing:
        return existing
    source = item.get("attachmentUrl") or item.get("sourceUrl") or item.get("sourcePageUrl")
    token = stable_event_id(
        clean_text(item.get("symbol")),
        exchange_event_id=item.get("exchangeEventId"),
        source_url=source,
        published_at=item.get("publishedAt"),
        raw_subject=item.get("rawSubject") or item.get("subject"),
        action_date=item.get("actionDate"),
    )
    item["stableEventId"] = token
    return token


def normalize_announcement(row: Dict[str, Any], stock_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    symbol = clean_text(get_field(row, "SYMBOL", "symbol", "ticker")).upper()
    company = clean_text(get_field(row, "COMPANY NAME", "companyName", "company", "sm_name"))
    subject = clean_text(get_field(row, "SUBJECT", "subject", "purpose", "desc"))
    details = clean_text(
        get_field(
            row,
            "DETAILS", "detail", "description", "remarks", "longdesc", "announcement",
            "attchmntText", "attachmentText", "announcementText", "subjectDesc",
        )
    )
    attachment = find_attachment_url(row)
    published_raw = get_field(
        row,
        "BROADCAST DATE/TIME", "broadcastDate", "broadcastDateTime", "broadcast", "sort_date",
        "DISSEMINATION DATE/TIME", "disseminationDate", "date", "timestamp", "an_dt", "dt",
    )
    published_dt = parse_datetime_flexible(published_raw)

    if not symbol or not subject:
        return None

    raw_subject = subject
    exchange_event_id = clean_text(get_field(
        row,
        "seq_id", "seqId", "sequenceId", "announcementId", "announcement_id",
        "an_id", "annId", "recordId", "record_id",
    ))
    category, category_label, _category_weight, matched = classify_trigger(subject, details)
    subject = refine_subject(subject, details, category)
    if not is_material(subject, details, category):
        return None

    sentiment, _sentiment_adjustment, sentiment_terms = determine_sentiment(subject, details)
    stock = stock_map.get(symbol, {})
    company = company or stock.get("stockName") or symbol
    highlights = extract_highlights(f"{subject} {details}")
    if not published_dt:
        disclosed_match = re.search(
            r"\b(?:dated|date[d]?)\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
            details,
            flags=re.I,
        )
        if disclosed_match:
            try:
                published_dt = datetime.strptime(
                    disclosed_match.group(1), "%B %d, %Y"
                ).replace(hour=12, tzinfo=IST)
            except ValueError:
                published_dt = None
    published_iso = iso_datetime(published_dt) or now_ist().isoformat(timespec="seconds")
    source_page = f"{NSE_ANNOUNCEMENTS_PAGE}?symbol={quote(symbol)}&tabIndex=equity"
    summary = deterministic_summary(company, subject, details)
    source_url = attachment or source_page
    matched_signals = list(dict.fromkeys(matched + sentiment_terms))[:6]
    intelligence = calculate_trigger_intelligence(
        category=category,
        subject=subject,
        details=details,
        highlights=highlights,
        matched_signals=matched_signals,
        stock=stock,
        published_dt=published_dt,
        source_url=source_url,
        source_type="NSE Corporate Announcement",
    )

    item = {
        "id": announcement_id(symbol, subject, published_iso, attachment),
        "exchangeEventId": exchange_event_id,
        "stableEventId": stable_event_id(
            symbol,
            exchange_event_id=exchange_event_id,
            source_url=attachment or source_page,
            published_at=published_iso,
            raw_subject=raw_subject,
        ),
        "symbol": symbol,
        "stockName": stock.get("stockName") or company,
        "companyName": company,
        "category": category,
        "categoryLabel": category_label,
        "sentiment": sentiment,
        "subject": subject,
        "rawSubject": raw_subject,
        "summary": summary,
        "detailsText": truncate(details, 1200),
        "summaryBasis": "Exchange announcement text",
        "filingExtracted": False,
        "filingKeyFacts": [],
        "whyItMatters": WHY_IT_MATTERS[category],
        "riskNote": RISK_NOTES[category],
        "highlights": highlights,
        "matchedSignals": matched_signals,
        "publishedAt": published_iso,
        "publishedDisplay": published_dt.strftime("%d-%b-%Y %H:%M IST") if published_dt else "Latest filing",
        "sourceType": "NSE Corporate Announcement",
        "sourceUrl": source_url,
        "sourcePageUrl": source_page,
        "attachmentUrl": attachment,
        "sourceLinkType": "original-filing" if attachment else "nse-announcement-page",
        "cmp": stock.get("cmp"),
        "changePct": stock.get("changePct"),
        "indices": stock.get("indices") or [],
        "isFree": bool(stock.get("isFree")),
        "accessTier": stock.get("accessTier") or "premium",
        "profileUrl": stock.get("profileUrl") or "/technical-analysis/",
        "triggerUrl": f"/stock-triggers/?symbol={quote(symbol)}",
        "aiEnhanced": False,
    }
    item.update(intelligence)
    return item


def corporate_action_triggers(stock_map: Dict[str, Dict[str, Any]], horizon_days: int = 45) -> List[Dict[str, Any]]:
    payload = safe_json_load(CORPORATE_ACTIONS_FILE, {})
    actions = payload.get("freshActions") or payload.get("actions") or [] if isinstance(payload, dict) else []
    today = now_ist().date()
    output: List[Dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        symbol = clean_text(action.get("symbol")).upper()
        purpose = clean_text(action.get("purpose"))
        event = clean_text(action.get("eventLabel") or action.get("eventType") or "Corporate Action")
        action_date = parse_datetime_flexible(action.get("exDate") or action.get("recordDate"))
        if not symbol or not action_date:
            continue
        days = (action_date.date() - today).days
        if days < 0 or days > horizon_days:
            continue
        stock = stock_map.get(symbol, {})
        company = clean_text(action.get("stockName") or action.get("companyName")) or stock.get("stockName") or symbol
        subject = f"{event}: {purpose}" if purpose else event
        published_at = action_date.replace(hour=0, minute=0, second=0)
        source_url = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
        summary = truncate(
            f"{company} has an upcoming {event.lower()} event. {purpose}. "
            f"The stated action date is {action_date.strftime('%d-%b-%Y')}.",
            300,
        )
        details = clean_text(f"{event}. {purpose}. Action date {action_date.strftime('%d-%b-%Y')}")
        highlights = extract_highlights(details)
        if action_date.strftime("%d-%b-%Y") not in highlights:
            highlights.append(action_date.strftime("%d-%b-%Y"))
        matched_signals = [event.lower()] + [term for term in ("dividend", "bonus", "split", "buyback", "rights", "record date") if term in details.lower()]
        intelligence = calculate_trigger_intelligence(
            category="CORPORATE_ACTION",
            subject=subject,
            details=details,
            highlights=highlights,
            matched_signals=matched_signals,
            stock=stock,
            published_dt=published_at,
            source_url=source_url,
            source_type="NSE Corporate Action",
            days_to_action=days,
        )
        item = {
            "id": announcement_id(symbol, subject, iso_datetime(published_at), source_url),
            "exchangeEventId": "",
            "stableEventId": stable_event_id(
                symbol,
                source_url=source_url,
                published_at=iso_datetime(published_at),
                raw_subject=subject,
                action_date=action_date.strftime("%Y-%m-%d"),
            ),
            "symbol": symbol,
            "stockName": stock.get("stockName") or company,
            "companyName": company,
            "category": "CORPORATE_ACTION",
            "categoryLabel": "Corporate Action",
            "sentiment": "Neutral",
            "subject": subject,
            "summary": summary,
            "detailsText": truncate(details, 1200),
            "whyItMatters": WHY_IT_MATTERS["CORPORATE_ACTION"],
            "riskNote": RISK_NOTES["CORPORATE_ACTION"],
            "highlights": highlights,
            "matchedSignals": list(dict.fromkeys(matched_signals))[:6],
            "publishedAt": iso_datetime(published_at),
            "publishedDisplay": f"Action date {action_date.strftime('%d-%b-%Y')}",
            "sourceType": "NSE Corporate Action",
            "sourceUrl": source_url,
            "sourcePageUrl": source_url,
            "attachmentUrl": "",
            "cmp": stock.get("cmp"),
            "changePct": stock.get("changePct"),
            "indices": stock.get("indices") or [],
            "isFree": bool(stock.get("isFree")),
            "accessTier": stock.get("accessTier") or "premium",
            "profileUrl": stock.get("profileUrl") or "/technical-analysis/",
            "triggerUrl": f"/stock-triggers/?symbol={quote(symbol)}",
            "actionDate": action_date.strftime("%Y-%m-%d"),
            "daysToAction": days,
            "aiEnhanced": False,
        }
        item.update(intelligence)
        output.append(item)
    return output


def slugify(value: Any, fallback: str = "item") -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def attach_public_urls(items: Iterable[Dict[str, Any]]) -> None:
    """Attach stable, descriptive public URLs.

    The URL intentionally excludes the derived category. Classification can
    improve on a later run; excluding it keeps the canonical URL unchanged.
    Legacy URLs are retained so the page builder can publish permanent 301
    redirects rather than allowing indexed URLs to become 404s.
    """
    for item in items:
        symbol = clean_text(item.get("symbol")).upper()
        published = parse_iso(item.get("publishedAt"))
        action = parse_datetime_flexible(item.get("actionDate"))
        reference = action or published or now_ist()
        date_part = reference.strftime("%Y-%m-%d")
        company_slug = slugify(item.get("stockName") or item.get("companyName") or symbol, symbol.lower() or "stock")
        stable_id = ensure_stable_event_identity(item)

        # Company + date remain human-readable; the short stable token prevents
        # collisions when a company has multiple filings on the same day.
        event_slug = f"{company_slug}-{date_part}-{stable_id}"
        new_event_url = f"/stock-triggers/events/{event_slug}/"
        old_event_url = clean_text(item.get("eventUrl"))
        legacy = [clean_text(value) for value in (item.get("legacyEventUrls") or []) if clean_text(value)]
        if old_event_url.startswith("/stock-triggers/events/") and old_event_url != new_event_url:
            legacy.append(old_event_url)
        item["legacyEventUrls"] = list(dict.fromkeys(legacy))[-8:]
        item["eventSlug"] = event_slug
        item["eventUrl"] = new_event_url
        item["stockHubUrl"] = f"/stocks/{slugify(symbol, 'stock')}/"
        category_slug = slugify(item.get("category") or "material-update")
        item["categoryUrl"] = f"/stock-triggers/category/{category_slug}/"
        item["triggerUrl"] = item["stockHubUrl"]


def parse_iso(value: Any) -> Optional[datetime]:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except ValueError:
        return parse_datetime_flexible(text)


def sanitise_trigger_source(item: Dict[str, Any]) -> None:
    attachment = canonical_attachment(item.get("attachmentUrl"))
    if not attachment:
        candidate = clean_text(item.get("sourceUrl"))
        attachment = candidate if is_direct_filing_url(candidate) else ""
    page = clean_text(item.get("sourcePageUrl"))
    if not is_http_url(page):
        symbol = clean_text(item.get("symbol")).upper()
        page = (
            f"{NSE_ANNOUNCEMENTS_PAGE}?symbol={quote(symbol)}&tabIndex=equity"
            if symbol
            else NSE_ANNOUNCEMENTS_PAGE
        )
    item["attachmentUrl"] = attachment
    item["sourcePageUrl"] = page
    item["sourceUrl"] = attachment or page
    item["sourceLinkType"] = "original-filing" if attachment else "nse-announcement-page"


def repair_legacy_announcement(item: Dict[str, Any]) -> None:
    if clean_text(item.get("sourceType")) != "NSE Corporate Announcement":
        return
    sanitise_trigger_source(item)
    details = clean_text(item.get("detailsText") or item.get("summary"))
    category = clean_text(item.get("category"))
    item["subject"] = refine_subject(clean_text(item.get("subject")), details, category)
    if not item.get("filingExtracted"):
        item["summary"] = deterministic_summary(
            clean_text(item.get("companyName") or item.get("stockName") or item.get("symbol")),
            clean_text(item.get("subject")),
            details,
        )
        item.setdefault("summaryBasis", "Exchange announcement text")
        item.setdefault("filingKeyFacts", [])
    if clean_text(item.get("publishedDisplay")) in {"", "Latest filing"}:
        disclosed_match = re.search(
            r"\b(?:dated|date[d]?)\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})",
            details,
            flags=re.I,
        )
        if disclosed_match:
            try:
                dt = datetime.strptime(
                    disclosed_match.group(1), "%B %d, %Y"
                ).replace(hour=12, tzinfo=IST)
                item["publishedAt"] = iso_datetime(dt)
                item["publishedDisplay"] = f"Filing dated {dt.strftime('%d-%b-%Y')}"
            except ValueError:
                pass


def semantic_trigger_key(item: Dict[str, Any]) -> str:
    """Deduplicate the same disclosure even if its category changes later."""
    stable_id = ensure_stable_event_identity(item)
    symbol = clean_text(item.get("symbol")).upper()
    return f"{symbol}|{stable_id}"


def merge_with_previous(new_items: Iterable[Dict[str, Any]], retention_days: int) -> List[Dict[str, Any]]:
    previous = safe_json_load(OUTPUT_FILE, {})
    previous_items = previous.get("triggers", []) if isinstance(previous, dict) else []
    cutoff = now_ist() - timedelta(days=retention_days)

    merged: Dict[str, Dict[str, Any]] = {}
    for item in list(previous_items) + list(new_items):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if clean_text(item.get("sourceType")) == "NSE Corporate Announcement":
            repair_legacy_announcement(item)
        ensure_stable_event_identity(item)
        published = parse_iso(item.get("publishedAt"))
        action_date = parse_datetime_flexible(item.get("actionDate"))
        reference = action_date or published
        if reference and reference < cutoff:
            continue
        # Fresh items are iterated after retained items. Prefer fresh rows, but
        # never replace a richer filing-extracted record with a thinner copy.
        key = semantic_trigger_key(item)
        previous_item = merged.get(key)
        if previous_item is None:
            merged[key] = item
            continue
        previous_richness = (
            1 if previous_item.get("filingExtracted") else 0,
            len(clean_text(previous_item.get("detailsText"))),
            int(previous_item.get("dataConfidence") or 0),
        )
        current_richness = (
            1 if item.get("filingExtracted") else 0,
            len(clean_text(item.get("detailsText"))),
            int(item.get("dataConfidence") or 0),
        )
        winner = item if current_richness >= previous_richness else previous_item
        loser = previous_item if winner is item else item
        legacy_urls = [
            clean_text(value)
            for value in (winner.get("legacyEventUrls") or []) + (loser.get("legacyEventUrls") or [])
            if clean_text(value)
        ]
        loser_url = clean_text(loser.get("eventUrl"))
        if loser_url.startswith("/stock-triggers/events/"):
            legacy_urls.append(loser_url)
        winner["legacyEventUrls"] = list(dict.fromkeys(legacy_urls))[-8:]
        merged[key] = winner

    def sort_key(item: Dict[str, Any]) -> Tuple[int, float, int]:
        # Fresh announcements appear first (newest first). Upcoming corporate
        # actions follow in nearest-date order so a distant ex-date does not hide
        # an action scheduled for tomorrow.
        score = int(item.get("impactScore") or 0)
        if item.get("sourceType") == "NSE Corporate Announcement":
            dt = parse_iso(item.get("publishedAt")) or datetime(1970, 1, 1, tzinfo=IST)
            return (0, -dt.timestamp(), -score)
        action_dt = parse_datetime_flexible(item.get("actionDate"))
        days = int(item.get("daysToAction") if item.get("daysToAction") is not None else 999999)
        if days < 0:
            days = 999999 + abs(days)
        return (1, float(days), -score)

    return sorted(merged.values(), key=sort_key)


def refresh_trigger_intelligence(items: Iterable[Dict[str, Any]], stock_map: Dict[str, Dict[str, Any]]) -> None:
    """Upgrade current and retained records to the latest transparent model.

    Retained records were produced by earlier daily runs. Recalculating them
    prevents old static scores from remaining in the feed for 120 days.
    """
    labels = {code: label for code, label, _keywords, _weight in CATEGORY_RULES}
    labels["OTHER_MATERIAL"] = "Other Material Update"

    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = clean_text(item.get("symbol")).upper()
        stock = stock_map.get(symbol, {})
        subject = clean_text(item.get("subject"))
        details = clean_text(item.get("detailsText") or item.get("summary"))
        source_type = clean_text(item.get("sourceType"))

        if source_type == "NSE Corporate Announcement":
            repair_legacy_announcement(item)
            subject = clean_text(item.get("subject"))
            details = clean_text(item.get("detailsText") or item.get("summary"))
            category, category_label, _weight, matched = classify_trigger(subject, details)
            item["category"] = category
            item["categoryLabel"] = category_label
            if not item.get("aiEnhanced"):
                sentiment, _adjustment, sentiment_terms = determine_sentiment(subject, details)
                item["sentiment"] = sentiment
            else:
                sentiment_terms = []
            item["matchedSignals"] = list(dict.fromkeys(matched + sentiment_terms + list(item.get("matchedSignals") or [])))[:6]
            item["whyItMatters"] = WHY_IT_MATTERS.get(category, WHY_IT_MATTERS["OTHER_MATERIAL"])
            item["riskNote"] = RISK_NOTES.get(category, RISK_NOTES["OTHER_MATERIAL"])
        else:
            category = clean_text(item.get("category")) or "OTHER_MATERIAL"
            item["categoryLabel"] = labels.get(category, clean_text(item.get("categoryLabel")) or "Other Material Update")

        highlights = list(item.get("highlights") or [])
        if not highlights:
            highlights = extract_highlights(f"{subject} {details}")
            item["highlights"] = highlights

        source_url = clean_text(item.get("sourceUrl") or item.get("sourcePageUrl"))
        days_to_action = item.get("daysToAction")
        if days_to_action is None and item.get("actionDate"):
            action_dt = parse_datetime_flexible(item.get("actionDate"))
            if action_dt:
                days_to_action = (action_dt.date() - now_ist().date()).days
                item["daysToAction"] = days_to_action

        intelligence = calculate_trigger_intelligence(
            category=clean_text(item.get("category")) or "OTHER_MATERIAL",
            subject=subject,
            details=details,
            highlights=highlights,
            matched_signals=list(item.get("matchedSignals") or []),
            stock=stock,
            published_dt=parse_iso(item.get("publishedAt")),
            source_url=source_url,
            source_type=source_type,
            days_to_action=days_to_action,
        )
        item.update(intelligence)

        # Refresh market snapshot fields from the latest scanner files even for
        # retained historical trigger records.
        for key in ("cmp", "changePct", "indices", "isFree", "accessTier", "profileUrl"):
            if stock.get(key) not in (None, "", []):
                item[key] = stock.get(key)


def summarise(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    category_counts = Counter(item.get("categoryLabel") or "Other" for item in items)
    sentiment_counts = Counter(item.get("sentiment") or "Neutral" for item in items)
    symbols = {item.get("symbol") for item in items if item.get("symbol")}
    latest_date = ""
    for item in items:
        dt = parse_iso(item.get("publishedAt"))
        if dt and (not latest_date or dt.isoformat() > latest_date):
            latest_date = dt.isoformat(timespec="seconds")
    return {
        "totalTriggers": len(items),
        "trackedStocks": len(symbols),
        "highImpactCount": sum(1 for item in items if int(item.get("impactScore") or 0) >= 75),
        "informationalCount": sum(1 for item in items if int(item.get("impactScore") or 0) < 35),
        "averageMaterialityScore": round(
            sum(int(item.get("impactScore") or 0) for item in items) / len(items), 1
        ) if items else 0,
        "averageDataConfidence": round(
            sum(int(item.get("dataConfidence") or 0) for item in items) / len(items), 1
        ) if items else 0,
        "positiveCount": sentiment_counts.get("Positive", 0),
        "cautionCount": sentiment_counts.get("Caution", 0),
        "latestPublishedAt": latest_date,
        "categoryCounts": dict(category_counts.most_common()),
        "sentimentCounts": dict(sentiment_counts),
    }


def gemini_enabled() -> bool:
    return (
        os.getenv("AIT_TRIGGER_AI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
        and bool(os.getenv("GEMINI_API_KEY", "").strip())
    )


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def ai_enrich_item(item: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = (os.getenv("GEMINI_MODEL", "") or "gemini-2.5-flash").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        "You are summarising an Indian listed-company exchange filing for an educational stock trigger feed. "
        "Use only the supplied filing text. Do not infer numbers, recommendations or price targets. "
        "Return strict JSON with keys summary, whyItMatters, riskNote, sentiment. sentiment must be one of "
        "Positive, Neutral, Mixed, Caution. Keep each text field under 55 words.\n\n"
        f"Company: {item.get('companyName')}\n"
        f"Subject: {item.get('subject')}\n"
        f"Current deterministic summary: {item.get('summary')}\n"
        f"Category: {item.get('categoryLabel')}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    response = requests.post(endpoint, json=payload, timeout=25)
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = extract_json_object(text)
    if not parsed:
        return item
    for key in ("summary", "whyItMatters", "riskNote"):
        value = clean_text(parsed.get(key))
        if value:
            item[key] = truncate(value, 360)
    sentiment = clean_text(parsed.get("sentiment")).title()
    if sentiment in {"Positive", "Neutral", "Mixed", "Caution"}:
        item["sentiment"] = sentiment
    item["aiEnhanced"] = True
    return item


def enrich_with_ai(items: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], int]:
    if not gemini_enabled() or limit <= 0:
        return items, 0
    enriched = 0
    for item in items[:limit]:
        if item.get("sourceType") != "NSE Corporate Announcement":
            continue
        try:
            ai_enrich_item(item)
            if item.get("aiEnhanced"):
                enriched += 1
        except Exception as exc:  # AI must never break the daily data pipeline.
            print(f"AI enrichment skipped for {item.get('symbol')}: {exc}")
        time.sleep(0.15)
    return items, enriched


def record_job_run(record: Dict[str, Any], keep: int = 60) -> None:
    payload = safe_json_load(JOB_RUNS_FILE, {})
    rows = payload.get("runs", []) if isinstance(payload, dict) else []
    rows = [row for row in rows if isinstance(row, dict)]
    rows.insert(0, record)
    JOB_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOB_RUNS_FILE.write_text(
        json.dumps({"updatedAt": record.get("finishedAt"), "runs": rows[:keep]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate dynamic stock trigger intelligence JSON.")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="NSE announcement lookback window.")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS, help="History retained in output JSON.")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Maximum trigger rows written.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated stock symbols for testing.")
    parser.add_argument("--source-file", default="", help="Optional CSV/JSON announcement fixture instead of NSE.")
    parser.add_argument("--offline", action="store_true", help="Skip NSE request; rebuild from local data and previous JSON.")
    parser.add_argument("--ai-limit", type=int, default=30, help="Maximum fresh announcements sent to optional Gemini enrichment.")
    parser.add_argument(
        "--filing-extract-limit",
        type=int,
        default=DEFAULT_FILING_EXTRACT_LIMIT,
        help="Maximum direct filings downloaded for text extraction per run.",
    )
    parser.add_argument(
        "--skip-filing-extract",
        action="store_true",
        help="Skip direct PDF/HTML filing text extraction.",
    )
    parser.add_argument("--write-empty-on-fail", action="store_true", help="Write a valid empty file only when no previous/local data exists.")
    parser.add_argument("--skip-pages", action="store_true", help="Write JSON only; do not rebuild event, stock and category pages.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_started = now_ist()
    stock_map = load_stock_map()
    today = now_ist().date()
    from_date = today - timedelta(days=max(1, args.days))
    symbols = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}

    source_mode = "NSE Corporate Announcements API"
    source_url = NSE_ANNOUNCEMENTS_API
    source_error = ""
    raw_rows: List[Dict[str, Any]] = []

    try:
        if args.source_file:
            raw_rows = load_source_file(Path(args.source_file))
            source_mode = "Local announcement fixture"
            source_url = str(Path(args.source_file))
        elif args.offline:
            source_mode = "Offline/local fallback"
        else:
            raw_rows, source_url = fetch_nse_announcements(from_date, today)
    except Exception as exc:
        source_error = clean_text(exc)
        source_mode = "Fallback: previous data + corporate actions"
        print(f"WARNING: NSE announcements unavailable: {source_error}", file=sys.stderr)

    announcement_items: List[Dict[str, Any]] = []
    for row in raw_rows:
        item = normalize_announcement(row, stock_map)
        if not item:
            continue
        if symbols and item["symbol"] not in symbols:
            continue
        announcement_items.append(item)

    action_items = corporate_action_triggers(stock_map)
    if symbols:
        action_items = [item for item in action_items if item["symbol"] in symbols]

    fresh_items = announcement_items + action_items
    filing_extracted_count = 0
    if not args.skip_filing_extract:
        fresh_items, filing_extracted_count = enrich_with_filing_text(
            fresh_items,
            max(0, args.filing_extract_limit),
        )
    fresh_items, ai_count = enrich_with_ai(fresh_items, max(0, args.ai_limit))
    merged = merge_with_previous(fresh_items, max(1, args.retention_days))
    refresh_trigger_intelligence(merged, stock_map)
    merged = merged[: max(1, args.max_items)]
    attach_public_urls(merged)

    if not merged and source_error and not args.write_empty_on_fail:
        raise SystemExit(
            "No trigger data could be generated and --write-empty-on-fail was not supplied. "
            "The previous output was not overwritten."
        )

    generated = now_ist()
    source_healthy = not bool(source_error) and not args.offline
    if source_healthy:
        source_note = (
            "Fresh NSE corporate announcements are classified into business triggers and merged with upcoming "
            "corporate actions. Short transformed summaries are provided for discovery; always open the original filing."
        )
    elif args.offline:
        source_note = (
            "This packaged build was generated in offline mode from the local corporate-action dataset. "
            "The scheduled GitHub Actions run will attempt to replace it with fresh NSE announcements."
        )
    else:
        source_note = (
            "The latest NSE request failed, so recent previously generated triggers were preserved and local "
            "corporate-action data was rebuilt."
        )

    job_run_id = f"stock-triggers-{generated.strftime('%Y%m%dT%H%M%S%z')}"
    payload = {
        "toolName": "AIT Stock Trigger Intelligence",
        "jobRunId": job_run_id,
        "updatedAt": format_ist(generated),
        "generatedAt": generated.isoformat(timespec="seconds"),
        "fromDate": from_date.strftime("%d-%b-%Y"),
        "toDate": today.strftime("%d-%b-%Y"),
        "lookbackDays": max(1, args.days),
        "retentionDays": max(1, args.retention_days),
        "sourceMode": source_mode,
        "sourceUrl": source_url,
        "sourceHealthy": source_healthy,
        "sourceError": source_error,
        "aiEnabled": gemini_enabled(),
        "aiEnhancedCount": ai_count,
        "filingExtractedCount": filing_extracted_count,
        "filingExtractionAvailable": PdfReader is not None,
        "sourceNote": source_note,
        "scoringModel": {
            "version": SCORING_MODEL_VERSION,
            "name": "AIT five-factor materiality model",
            "total": 100,
            "factors": [
                {"id": "businessMateriality", "label": "Business materiality", "max": 35},
                {"id": "evidenceSpecificity", "label": "Evidence specificity", "max": 20},
                {"id": "financialMagnitude", "label": "Financial magnitude", "max": 20},
                {"id": "marketConfirmation", "label": "Market confirmation", "max": 15},
                {"id": "recencyUrgency", "label": "Recency / urgency", "max": 10},
            ],
            "bands": [
                {"label": "High materiality", "min": 75},
                {"label": "Moderate materiality", "min": 55},
                {"label": "Low materiality", "min": 35},
                {"label": "Informational", "min": 0},
            ],
        },
        "summary": summarise(merged),
        "categories": [
            {"id": code, "label": label}
            for code, label, _keywords, _weight in CATEGORY_RULES
        ] + [{"id": "OTHER_MATERIAL", "label": "Other Material Update"}],
        "triggers": merged,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(OUTPUT_FILE)

    record_job_run({
        "id": job_run_id,
        "jobName": "stock-trigger-intelligence",
        "status": "healthy" if source_healthy else ("offline" if args.offline else "fallback"),
        "startedAt": run_started.isoformat(timespec="seconds"),
        "finishedAt": generated.isoformat(timespec="seconds"),
        "sourceMode": source_mode,
        "sourceHealthy": source_healthy,
        "sourceError": source_error,
        "announcementsFetched": len(raw_rows),
        "announcementsPublished": len(announcement_items),
        "corporateActionsPublished": len(action_items),
        "totalTriggersPublished": len(merged),
        "aiEnhancedCount": ai_count,
    })

    print(f"Wrote {len(merged)} stock triggers to {OUTPUT_FILE}")
    print(f"Fresh announcements: {len(announcement_items)}")
    print(f"Upcoming corporate actions: {len(action_items)}")
    print(f"Source mode: {source_mode}")
    if source_error:
        print(f"Source warning: {source_error}")

    if not args.skip_pages:
        try:
            from BuildStockTriggerPages import build_pages
            page_stats = build_pages(payload)
            print(
                "Generated pages: "
                f"{page_stats.get('events', 0)} events, "
                f"{page_stats.get('stocks', 0)} stock hubs, "
                f"{page_stats.get('categories', 0)} categories"
            )
        except Exception as exc:
            raise SystemExit(f"Stock trigger JSON was written, but public page generation failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
