"""
GenerateStockResearchIndex.py

Builds the static stock search JSON used by the Automation In Trade homepage.
The website does NOT run Python in the browser. Python/GitHub Actions generate
small JSON outputs, and the HTML card replaces values dynamically.

Preferred output data paths:
  stock-research-data/price-action/{SYMBOL}.json
  stock-research-data/results/{SYMBOL}.json
  stock-research-data/technical-analysis/{SYMBOL}.json

Legacy image paths are still detected for reference, but the homepage renders
HTML from JSON first, so heavy images are not required.
"""

import json
from pathlib import Path
from datetime import datetime

WEBSITE_ROOT = Path(__file__).resolve().parent
MARKET_DATA_DIR = WEBSITE_ROOT / "market-data"
OUTPUT_FILE = MARKET_DATA_DIR / "stock-research-index.json"
DATA_BASE = WEBSITE_ROOT / "stock-research-data"

TOOL_CONFIG = {
    "price-action": {
        "key": "priceAction",
        "label": "Price Action",
        "folder": "price-action",
        "summary": "Buy zone, target, stop-loss and trend-level view generated from JSON.",
    },
    "results": {
        "key": "results",
        "label": "Results",
        "folder": "results",
        "summary": "Quarterly result quality scorecard with revenue, profit, margin and reaction view.",
    },
    "technical-analysis": {
        "key": "technicalAnalysis",
        "label": "Technical Analysis",
        "folder": "technical-analysis",
        "summary": "Technical view with trend, RSI, volume, support/resistance and action zones.",
    },
}

FREE_RESEARCH_INDICES = {"NIFTY 50", "NIFTY BANK", "BANK NIFTY"}


def is_free_research_stock(item: dict) -> bool:
    indices = {str(x or "").strip().upper() for x in item.get("indices", [])}
    return bool(indices & FREE_RESEARCH_INDICES)


def locked_output_info(tool_id: str):
    cfg = TOOL_CONFIG[tool_id]
    return {
        "available": False,
        "premium": True,
        "title": cfg["label"],
        "summary": "Premium Research Tools access required.",
        "dataPath": "",
        "legacyImage": "",
        "source": "premium-locked",
        "data": None,
    }


def safe_symbol(value: str) -> str:
    return str(value or "").strip().upper().replace("/", "_").replace("\\", "_")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_stock_universe():
    stocks = {}
    high_low_dir = MARKET_DATA_DIR / "52-week-high-low"
    if high_low_dir.exists():
        for path in high_low_dir.glob("*.json"):
            data = load_json(path)
            if not data:
                continue
            index_name = data.get("indexName") or path.stem
            for row in data.get("stocks", []):
                symbol = safe_symbol(row.get("symbol"))
                if not symbol:
                    continue
                item = stocks.setdefault(symbol, {
                    "symbol": symbol,
                    "stockName": row.get("stockName") or symbol,
                    "indices": [],
                    "cmp": row.get("cmp"),
                    "changePct": row.get("changePct"),
                    "updatedAt": data.get("updatedAt", ""),
                })
                if row.get("stockName"):
                    item["stockName"] = row.get("stockName")
                if index_name not in item["indices"]:
                    item["indices"].append(index_name)
                if row.get("cmp") is not None:
                    item["cmp"] = row.get("cmp")
                if row.get("changePct") is not None:
                    item["changePct"] = row.get("changePct")

    # Also include any symbols for which generated JSON or legacy image files already exist.
    for cfg in TOOL_CONFIG.values():
        folder = DATA_BASE / cfg["folder"]
        if not folder.exists():
            continue
        for file in list(folder.glob("*.json")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.jpg")) + list(folder.glob("*.webp")) + list(folder.glob("*.png")):
            symbol = safe_symbol(file.stem)
            stocks.setdefault(symbol, {
                "symbol": symbol,
                "stockName": symbol,
                "indices": [],
                "cmp": None,
                "changePct": None,
                "updatedAt": "",
            })
    return stocks


def output_info(symbol: str, tool_id: str):
    cfg = TOOL_CONFIG[tool_id]
    folder = DATA_BASE / cfg["folder"]
    public_folder = f"/stock-research-data/{cfg['folder']}"
    data_path = folder / f"{symbol}.json"
    data = load_json(data_path) if data_path.exists() else None

    # Legacy image reference only. Homepage uses JSON data; it does not need to load this image.
    legacy_image = ""
    for ext in ["jpeg", "jpg", "webp", "png"]:
        candidate = folder / f"{symbol}.{ext}"
        if candidate.exists():
            legacy_image = f"{public_folder}/{symbol}.{ext}"
            break

    return {
        "available": bool(data),
        "title": cfg["label"],
        "summary": cfg["summary"],
        "dataPath": f"{public_folder}/{symbol}.json",
        "legacyImage": legacy_image,
        "source": "pre-generated-json" if data else ("legacy-image-only" if legacy_image else "expected-json-path"),
        "data": data,
    }


def main():
    stocks = load_stock_universe()
    output_stocks = []
    for symbol in sorted(stocks):
        item = stocks[symbol]
        is_free = is_free_research_stock(item)
        base = {
            "symbol": item.get("symbol") or symbol,
            "stockName": item.get("stockName") or symbol,
            "accessTier": "free" if is_free else "premium",
            "isFree": is_free,
        }

        if is_free:
            base.update({
                "indices": item.get("indices", []),
                "cmp": item.get("cmp"),
                "changePct": item.get("changePct"),
                "updatedAt": item.get("updatedAt", ""),
                "priceAction": output_info(symbol, "price-action"),
                "results": output_info(symbol, "results"),
                "technicalAnalysis": output_info(symbol, "technical-analysis"),
            })
        else:
            # Keep only searchable identity in the public index. Detailed values stay locked.
            base.update({
                "indices": [],
                "priceAction": locked_output_info("price-action"),
                "results": locked_output_info("results"),
                "technicalAnalysis": locked_output_info("technical-analysis"),
            })

        output_stocks.append(base)

    payload = {
        "updatedAt": datetime.now().strftime("%d-%b-%Y %H:%M IST"),
        "sourceNote": "Generated by GenerateStockResearchIndex.py. Free research is enabled only for NIFTY 50 and Bank Nifty stocks; other stock research is premium-locked.",
        "tools": [
            {"id": tool_id, "label": cfg["label"], "description": cfg["summary"]}
            for tool_id, cfg in TOOL_CONFIG.items()
        ],
        "stocks": output_stocks,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Wrote {OUTPUT_FILE} with {len(output_stocks)} stocks")


if __name__ == "__main__":
    main()
