"""
GenerateCorporateActionsJson.py

Corporate action JSON generator for Automation In Trade.

What this script does:
- Pulls NSE corporate actions for Equity segment.
- Classifies the action type: Dividend, Bonus, Split, Buyback, Rights, Record Date, Other.
- Matches symbols with the website's existing market universe from:
      market-data/stock-strength-ranker.json
      market-data/52-week-high-low/*.json
- Publishes a clean JSON file consumed by:
      /market-tools/corporate-actions/

Common commands:
  python GenerateCorporateActionsJson.py
  python GenerateCorporateActionsJson.py --window next-3-months
  python GenerateCorporateActionsJson.py --window last-12-months
  python GenerateCorporateActionsJson.py --include-all-symbols

Notes:
- NSE occasionally blocks automated requests. If live NSE fetch fails, this script
  preserves the previous corporate-actions.json instead of publishing blanks.
- Educational data only. Always verify corporate actions on the official exchange
  or company filing before making any investment or trading decision.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

WEBSITE_ROOT = Path(".")
CORPORATE_ACTIONS_FILE = WEBSITE_ROOT / "market-data" / "corporate-actions.json"
STOCK_STRENGTH_FILE = WEBSITE_ROOT / "market-data" / "stock-strength-ranker.json"
INDEX_JSON_FOLDER = WEBSITE_ROOT / "market-data" / "52-week-high-low"

NSE_HOME_URL = "https://www.nseindia.com/"
NSE_ACTIONS_PAGE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
NSE_CORPORATE_ACTIONS_API = "https://www.nseindia.com/api/corporates-corporateActions"

REQUEST_TIMEOUT = 25
MAX_NSE_RETRIES = 3

KEEP_EVENT_TYPES = {"DIVIDEND", "BONUS", "SPLIT", "BUYBACK", "RIGHTS", "RECORD_DATE"}

WINDOWS = {
    "today": (0, 0),
    "next-1-week": (0, 7),
    "next-15-days": (0, 15),
    "next-1-month": (0, 31),
    "next-3-months": (0, 92),
    "last-1-week": (-7, 0),
    "last-15-days": (-15, 0),
    "last-1-month": (-31, 0),
    "last-3-months": (-92, 0),
    "last-12-months": (-365, 0),
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_symbol(symbol: Any) -> str:
    return normalize_text(symbol).upper()


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        cleaned = str(value).replace(",", "").replace("₹", "").strip()
        return float(cleaned)
    except Exception:
        return None


def format_timestamp() -> str:
    return datetime.now().strftime("%d-%b-%Y %H:%M IST")


def read_json_file(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"Could not read {path}: {exc}")
    return fallback


def classify_event_type(purpose: Any) -> str:
    p = normalize_text(purpose).lower()

    if "buy back" in p or "buyback" in p:
        return "BUYBACK"
    if "bonus" in p:
        return "BONUS"
    if "split" in p or "sub-division" in p or "sub division" in p or "face value split" in p:
        return "SPLIT"
    if "rights" in p or "right issue" in p:
        return "RIGHTS"
    if "dividend" in p:
        return "DIVIDEND"
    if "record" in p:
        return "RECORD_DATE"
    return "OTHER"


def clean_event_label(event_type: str) -> str:
    return {
        "DIVIDEND": "Dividend",
        "BONUS": "Bonus",
        "SPLIT": "Split",
        "BUYBACK": "Buyback",
        "RIGHTS": "Rights",
        "RECORD_DATE": "Record Date",
        "OTHER": "Other",
    }.get(event_type, "Other")


def parse_date(value: Any) -> Optional[datetime]:
    value = normalize_text(value)
    if not value or value in {"-", "--", "NA", "N.A."}:
        return None

    for fmt in ["%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%d-%B-%Y"]:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None


def format_date_for_nse(value: datetime) -> str:
    return value.strftime("%d-%m-%Y")


def output_date(value: Any) -> str:
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime("%d-%b-%Y")
    return normalize_text(value)


def resolve_date_window(window: str, from_date: str = "", to_date: str = "") -> Tuple[datetime, datetime]:
    if from_date and to_date:
        start = parse_date(from_date)
        end = parse_date(to_date)
        if not start or not end:
            raise ValueError("Custom dates must be parseable, for example 01-07-2026")
        return start, end

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_offset, end_offset = WINDOWS.get(window, WINDOWS["last-12-months"])
    return today + timedelta(days=start_offset), today + timedelta(days=end_offset)


def create_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Referer": NSE_ACTIONS_PAGE_URL,
        "Connection": "keep-alive",
    })

    # Warm cookies. NSE often needs this before API calls work.
    try:
        session.get(NSE_HOME_URL, timeout=REQUEST_TIMEOUT)
        time.sleep(0.7)
        session.get(NSE_ACTIONS_PAGE_URL, timeout=REQUEST_TIMEOUT)
        time.sleep(0.7)
    except Exception as exc:
        print(f"NSE cookie warm-up warning: {exc}")

    return session


def fetch_nse_corporate_actions(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    last_error = None

    for attempt in range(1, MAX_NSE_RETRIES + 1):
        try:
            session = create_nse_session()
            params = {
                "index": "equities",
                "from_date": format_date_for_nse(start),
                "to_date": format_date_for_nse(end),
            }
            response = session.get(NSE_CORPORATE_ACTIONS_API, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code in {401, 403}:
                time.sleep(1.2 * attempt)
                session = create_nse_session()
                response = session.get(NSE_CORPORATE_ACTIONS_API, params=params, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                return [row for row in data if isinstance(row, dict)]

            if isinstance(data, dict):
                rows = data.get("data") or data.get("rows") or data.get("corporateActions") or []
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]

            return []
        except Exception as exc:
            last_error = exc
            print(f"NSE corporate actions fetch failed, attempt {attempt}: {exc}")
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"NSE corporate actions fetch failed: {last_error}")


def row_value(row: Dict[str, Any], possible_keys: Iterable[str]) -> str:
    lower_map = {str(k).lower().replace("_", "").replace(" ", ""): v for k, v in row.items()}
    for key in possible_keys:
        direct = row.get(key)
        if direct not in (None, ""):
            return normalize_text(direct)
        normalized = key.lower().replace("_", "").replace(" ", "")
        if normalized in lower_map and lower_map[normalized] not in (None, ""):
            return normalize_text(lower_map[normalized])
    return ""


def load_stock_universe() -> Dict[str, Dict[str, Any]]:
    universe: Dict[str, Dict[str, Any]] = {}

    strength_payload = read_json_file(STOCK_STRENGTH_FILE, {})
    for row in strength_payload.get("stocks", []) if isinstance(strength_payload, dict) else []:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol:
            continue
        universe[symbol] = {
            "symbol": symbol,
            "stockName": normalize_text(row.get("stockName")) or symbol,
            "indices": list(dict.fromkeys(row.get("indices") or [])),
            "cmp": safe_float(row.get("cmp")),
            "strengthScore": safe_float(row.get("strengthScore")),
        }

    if INDEX_JSON_FOLDER.exists():
        for path in sorted(INDEX_JSON_FOLDER.glob("*.json")):
            payload = read_json_file(path, {})
            index_name = normalize_text(payload.get("indexName")) if isinstance(payload, dict) else ""
            for row in payload.get("stocks", []) if isinstance(payload, dict) else []:
                if not isinstance(row, dict):
                    continue
                symbol = normalize_symbol(row.get("symbol"))
                if not symbol:
                    continue
                item = universe.setdefault(symbol, {
                    "symbol": symbol,
                    "stockName": normalize_text(row.get("stockName")) or symbol,
                    "indices": [],
                    "cmp": safe_float(row.get("cmp")),
                    "strengthScore": None,
                })
                if not item.get("stockName") or item.get("stockName") == symbol:
                    item["stockName"] = normalize_text(row.get("stockName")) or symbol
                if index_name and index_name not in item["indices"]:
                    item["indices"].append(index_name)
                if item.get("cmp") is None:
                    item["cmp"] = safe_float(row.get("cmp"))

    return universe


def build_action_view(event_type: str, days_to_ex: Optional[int], purpose: str) -> str:
    if days_to_ex is not None:
        if days_to_ex > 0:
            timing = f"Upcoming in {days_to_ex} day{'s' if days_to_ex != 1 else ''}"
        elif days_to_ex == 0:
            timing = "Ex-date today"
        else:
            timing = f"Recent: {abs(days_to_ex)} day{'s' if abs(days_to_ex) != 1 else ''} ago"
    else:
        timing = "Record-date watch"

    label = clean_event_label(event_type)
    p = normalize_text(purpose).lower()

    if event_type == "DIVIDEND":
        return f"{timing}. Dividend event; check yield, ex-date and record date before planning."
    if event_type == "BONUS":
        return f"{timing}. Bonus issue; price normally adjusts on ex-date, so verify ratio and record date."
    if event_type == "SPLIT":
        return f"{timing}. Stock split; quantity and price adjust, business value does not change automatically."
    if event_type == "BUYBACK":
        return f"{timing}. Buyback event; verify tender/open-market route and entitlement details."
    if event_type == "RIGHTS":
        return f"{timing}. Rights issue; check eligibility, ratio, price and application dates."
    if "record" in p:
        return f"{timing}. Record-date based event; confirm details from official filing."
    return f"{timing}. {label} event; use this as a tracking alert, not a trade signal."


def normalize_corporate_action_row(row: Dict[str, Any], universe: Dict[str, Dict[str, Any]], include_all_symbols: bool) -> Optional[Dict[str, Any]]:
    symbol = normalize_symbol(row_value(row, ["symbol", "Symbol", "SYMBOL"]))
    if not symbol:
        return None

    if not include_all_symbols and symbol not in universe:
        return None

    company_name = row_value(row, ["companyName", "Company Name", "company", "compName", "issuer"])
    purpose = row_value(row, ["purpose", "Purpose", "subject"])
    event_type = classify_event_type(purpose)

    ex_date_raw = row_value(row, ["exDate", "Ex-Date", "exDateText", "ex_date", "Ex Date"])
    record_date_raw = row_value(row, ["recordDate", "Record Date", "recDate", "record_date"])

    # Keep business-relevant rows. Record-date-only rows are also retained.
    has_record_date = bool(record_date_raw)
    if event_type not in KEEP_EVENT_TYPES and not has_record_date:
        return None
    if event_type == "OTHER" and has_record_date:
        event_type = "RECORD_DATE"

    ex_date = parse_date(ex_date_raw)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_to_ex = (ex_date - today).days if ex_date else None

    if days_to_ex is None:
        date_bucket = "No Ex-Date"
    elif days_to_ex < 0:
        date_bucket = "Recent"
    elif days_to_ex == 0:
        date_bucket = "Today"
    else:
        date_bucket = "Upcoming"

    u = universe.get(symbol, {})
    stock_name = normalize_text(u.get("stockName")) or company_name or symbol
    indices = list(dict.fromkeys(u.get("indices") or []))

    return {
        "symbol": symbol,
        "stockName": stock_name,
        "companyName": company_name or stock_name,
        "indices": indices,
        "series": row_value(row, ["series", "Series"]),
        "eventType": event_type,
        "eventLabel": clean_event_label(event_type),
        "purpose": purpose,
        "faceValue": row_value(row, ["faceValue", "Face Value", "face_value"]),
        "exDate": output_date(ex_date_raw),
        "recordDate": output_date(record_date_raw),
        "bookClosureStartDate": output_date(row_value(row, ["bcStartDate", "Book Closure Start Date", "bookClosureStartDate"])),
        "bookClosureEndDate": output_date(row_value(row, ["bcEndDate", "Book Closure End Date", "bookClosureEndDate"])),
        "dateBucket": date_bucket,
        "daysToExDate": days_to_ex,
        "cmp": u.get("cmp"),
        "strengthScore": u.get("strengthScore"),
        "actionView": build_action_view(event_type, days_to_ex, purpose),
    }


def sort_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(row: Dict[str, Any]):
        days = row.get("daysToExDate")
        if days is None:
            return (2, 999999, row.get("symbol", ""))
        if days >= 0:
            return (0, days, row.get("symbol", ""))
        return (1, abs(days), row.get("symbol", ""))

    return sorted(actions, key=key)


def build_summary(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    event_counts: Dict[str, int] = {}
    upcoming_count = 0
    recent_count = 0
    record_date_count = 0

    for row in actions:
        event_counts[row.get("eventLabel") or "Other"] = event_counts.get(row.get("eventLabel") or "Other", 0) + 1
        bucket = row.get("dateBucket")
        if bucket in {"Upcoming", "Today"}:
            upcoming_count += 1
        elif bucket == "Recent":
            recent_count += 1
        if row.get("recordDate"):
            record_date_count += 1

    return {
        "totalActions": len(actions),
        "upcomingCount": upcoming_count,
        "recentCount": recent_count,
        "recordDateCount": record_date_count,
        "eventCounts": event_counts,
    }


def write_payload(payload: Dict[str, Any]) -> None:
    CORPORATE_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CORPORATE_ACTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved: {CORPORATE_ACTIONS_FILE}")


def build_empty_payload(window: str, start: datetime, end: datetime, message: str = "") -> Dict[str, Any]:
    return {
        "toolName": "Corporate Actions Tracker",
        "updatedAt": format_timestamp(),
        "generatedAt": format_timestamp(),
        "window": window,
        "fromDate": start.strftime("%d-%b-%Y"),
        "toDate": end.strftime("%d-%b-%Y"),
        "sourceNote": (
            "Corporate action JSON was generated, but no rows are available yet. "
            "Run GenerateCorporateActionsJson.py after NSE data is reachable. Educational use only."
        ),
        "warning": message,
        "summary": {
            "totalActions": 0,
            "upcomingCount": 0,
            "recentCount": 0,
            "recordDateCount": 0,
            "eventCounts": {},
        },
        "actions": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate market-data/corporate-actions.json")
    parser.add_argument(
        "--window",
        default="last-12-months",
        choices=sorted(WINDOWS.keys()),
        help="Date window for NSE corporate actions. Default: last-12-months.",
    )
    parser.add_argument("--from-date", default="", help="Optional custom start date, e.g. 01-07-2026")
    parser.add_argument("--to-date", default="", help="Optional custom end date, e.g. 30-09-2026")
    parser.add_argument(
        "--include-all-symbols",
        action="store_true",
        help="Include NSE rows outside the website's existing index universe.",
    )
    parser.add_argument(
        "--write-empty-on-fail",
        action="store_true",
        help="Write an empty JSON if NSE fetch fails and no previous JSON exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start, end = resolve_date_window(args.window, args.from_date, args.to_date)
    previous = read_json_file(CORPORATE_ACTIONS_FILE, {})

    print("Updating corporate actions JSON")
    print(f"Window: {start.strftime('%d-%m-%Y')} to {end.strftime('%d-%m-%Y')}")

    universe = load_stock_universe()
    print(f"Website stock universe: {len(universe)} symbols")

    try:
        raw_rows = fetch_nse_corporate_actions(start, end)
        print(f"NSE corporate action rows fetched: {len(raw_rows)}")
    except Exception as exc:
        print(f"Corporate action update failed: {exc}")
        if isinstance(previous, dict) and previous.get("actions"):
            previous["sourceNote"] = (
                previous.get("sourceNote", "")
                + " Previous JSON preserved because latest NSE fetch failed."
            ).strip()
            write_payload(previous)
            return 0
        if args.write_empty_on_fail:
            write_payload(build_empty_payload(args.window, start, end, str(exc)))
            return 0
        raise

    actions: List[Dict[str, Any]] = []
    seen = set()

    for raw in raw_rows:
        item = normalize_corporate_action_row(raw, universe, include_all_symbols=args.include_all_symbols)
        if not item:
            continue
        unique_key = (
            item.get("symbol"),
            item.get("eventType"),
            item.get("purpose"),
            item.get("exDate"),
            item.get("recordDate"),
        )
        if unique_key in seen:
            continue
        seen.add(unique_key)
        actions.append(item)

    actions = sort_actions(actions)

    payload = {
        "toolName": "Corporate Actions Tracker",
        "updatedAt": format_timestamp(),
        "generatedAt": format_timestamp(),
        "window": args.window,
        "fromDate": start.strftime("%d-%b-%Y"),
        "toDate": end.strftime("%d-%b-%Y"),
        "sourceNote": (
            "Generated from NSE corporate actions and matched with Automation In Trade market universe. "
            "Focus events: dividend, bonus, split, buyback, rights and record-date rows. "
            "Values may be delayed. Educational use only."
        ),
        "summary": build_summary(actions),
        "actions": actions,
    }

    write_payload(payload)
    print(f"Matched corporate action rows saved: {len(actions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
