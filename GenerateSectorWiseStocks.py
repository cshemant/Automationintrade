from __future__ import annotations

import json
import re
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
MARKET_DATA = ROOT / "market-data"
STRENGTH_FILE = MARKET_DATA / "stock-strength-ranker.json"
SECTOR_FILE = MARKET_DATA / "sector-wise-stocks.json"
SECTOR_DIR = ROOT / "markets" / "sector"
LIVE_JS = SECTOR_DIR / "sector-live.js"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_money(value: Any) -> str:
    v = num(value)
    return "₹" + format_indian(v)


def format_indian(value: float) -> str:
    # Python has no built-in en-IN grouping without locale setup; this keeps output stable on GitHub Actions.
    s = f"{value:.2f}"
    whole, dec = s.split(".")
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    if len(whole) <= 3:
        return sign + whole + "." + dec
    last3 = whole[-3:]
    rest = whole[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return sign + ",".join(groups + [last3]) + "." + dec


def fmt_pct(value: Any, signed: bool = True) -> str:
    v = num(value)
    prefix = "+" if signed and v > 0 else ""
    return f"{prefix}{v:.2f}%"


def class_for_pct(value: Any) -> str:
    return "is-positive" if num(value) >= 0 else "is-negative"


def strong_count(stocks: List[Dict[str, Any]]) -> int:
    return sum(1 for s in stocks if num(s.get("strengthScore")) >= 70)


def avg_strength(stocks: List[Dict[str, Any]]) -> float:
    vals = [num(s.get("strengthScore")) for s in stocks if s.get("strengthScore") is not None]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def merge_sector_data() -> Dict[str, Any]:
    if not STRENGTH_FILE.exists():
        raise FileNotFoundError(f"Missing latest stock strength file: {STRENGTH_FILE}")
    if not SECTOR_FILE.exists():
        raise FileNotFoundError(f"Missing sector mapping file: {SECTOR_FILE}")

    strength = read_json(STRENGTH_FILE)
    old_sector = read_json(SECTOR_FILE)
    latest_by_symbol = {normalize_symbol(s.get("symbol")): s for s in strength.get("stocks", [])}

    sectors = []
    total_count = 0
    for sector in old_sector.get("sectors", []):
        slug = sector.get("slug")
        name = sector.get("name")
        updated_stocks: List[Dict[str, Any]] = []
        seen = set()
        for old_stock in sector.get("stocks", []):
            symbol = normalize_symbol(old_stock.get("symbol"))
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            fresh = dict(latest_by_symbol.get(symbol, old_stock))
            # Preserve sector and visibility metadata from the sector mapping.
            fresh["symbol"] = fresh.get("symbol") or old_stock.get("symbol")
            fresh["stockName"] = fresh.get("stockName") or old_stock.get("stockName")
            fresh["isFree"] = old_stock.get("isFree", fresh.get("isFree", False))
            fresh["sectorSlug"] = slug
            fresh["sectorName"] = name
            updated_stocks.append(fresh)

        updated_stocks.sort(key=lambda s: num(s.get("strengthScore")), reverse=True)
        for i, s in enumerate(updated_stocks, start=1):
            s["sectorRank"] = i

        count = len(updated_stocks)
        total_count += count
        sectors.append({
            "slug": slug,
            "name": name,
            "stockCount": count,
            "avgStrength": avg_strength(updated_stocks),
            "strongCount": strong_count(updated_stocks),
            "stocks": updated_stocks,
        })

    sectors.sort(key=lambda s: str(s.get("name", "")).lower())
    return {
        "toolName": "Sector Wise Stocks",
        "updatedAt": strength.get("updatedAt") or strength.get("generatedAt") or old_sector.get("updatedAt") or datetime.now().strftime("%d-%b-%Y %H:%M IST"),
        "sourceNote": "Auto-generated from latest market-data/stock-strength-ranker.json. Sector classification is preserved from market-data/sector-wise-stocks.json.",
        "sectorCount": len(sectors),
        "stockCount": total_count,
        "sectors": sectors,
    }


def extract_header_footer() -> tuple[str, str]:
    sample = SECTOR_DIR / "index.html"
    if not sample.exists():
        sample = ROOT / "index.html"
    text = sample.read_text(encoding="utf-8")
    header_match = re.search(r"<header class=\"site-header\">.*?</header>", text, re.S)
    footer_match = re.search(r"<footer class=\"site-footer.*?</html>", text, re.S)
    if not header_match or not footer_match:
        raise RuntimeError("Could not extract common header/footer for sector pages.")
    return header_match.group(0), footer_match.group(0)


def render_sector_index(data: Dict[str, Any], header: str, footer: str) -> str:
    rows = []
    for sector in data["sectors"]:
        stocks = sector.get("stocks", [])
        top = stocks[0].get("stockName", "-") if stocks else "-"
        rows.append(f'''      <a class="sector-list-row" href="/markets/sector/{esc(sector['slug'])}/" data-sector-name="{esc(str(sector['name']).lower())}">
        <span class="sector-name">{esc(sector['name'])}</span>
        <span>{sector['stockCount']} stocks</span>
        <span>{sector['avgStrength']}</span>
        <span>{esc(top)}</span>
      </a>''')

    description = "Browse Indian stocks by sector with company names, stock count, average AIT strength score, top stocks and links to sector-wise stock pages."
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Sector Wise Stocks in India | Automation In Trade</title>
<meta name="description" content="{esc(description)}"/>
<meta name="keywords" content="sector wise stocks, Indian stock sectors, NSE sector stocks, sector stock list India, stocks by industry sector"/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;family=Manrope:wght@500;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="/style.css?v=142" rel="stylesheet"/>
<link href="https://automationintrade.com/markets/sector/" rel="canonical"/>
<meta property="og:title" content="Sector Wise Stocks in India | Automation In Trade"/>
<meta property="og:description" content="Browse sector-wise Indian stocks with AIT strength data and links to detailed sector pages."/>
<meta property="og:url" content="https://automationintrade.com/markets/sector/"/>
<meta property="og:type" content="website"/>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"CollectionPage","name":"Sector Wise Stocks in India","url":"https://automationintrade.com/markets/sector/","description":"Browse Indian stocks by sector with stock counts and AIT strength data."}}</script>
</head>
<body>
{header}
<main>
<section class="sector-page-wrap section-padding" data-sector-index="true">
  <div class="sector-breadcrumbs"><a href="/">Home</a><span>›</span><span>Markets</span></div>
  <div class="sector-heading-row">
    <div>
      <h1>Sector wise stocks</h1>
      <p class="sector-count">{data['sectorCount']} sectors · {data['stockCount']} stocks</p>
      <p class="sector-intro">Browse listed companies grouped by sector. Open any sector page to view stocks with CMP, daily move, 52-week correction, AIT strength score and research links.</p>
    </div>
    <div class="sector-data-note">Updated: {esc(data['updatedAt'])}<br/>Source: Latest AIT stock strength universe</div>
  </div>
  <div class="sector-search-box"><input id="sectorSearchInput" type="search" placeholder="Search sector name..." aria-label="Search sector name"></div>
  <div class="sector-list-card">
    <div class="sector-list-header"><span>Sector</span><span>Companies</span><span>Avg AIT Score</span><span>Top strength stock</span></div>
    <div id="sectorListRows">
{chr(10).join(rows)}
    </div>
  </div>
  <section class="sector-info-block">
    <h2>How this sector list helps traders</h2>
    <p>Most sector pages only show company names. This page adds an Automation In Trade layer by connecting sector groups with momentum, 52-week correction and strength score data. It helps you quickly understand where strength or weakness is concentrated before opening individual charts.</p>
  </section>
</section>
</main>
<script src="/markets/sector/sector-live.js?v=142"></script>
{footer}'''


def render_stock_rows(stocks: List[Dict[str, Any]]) -> str:
    rows = []
    for idx, stock in enumerate(stocks, start=1):
        ch = num(stock.get("changePct"))
        down = num(stock.get("downFromHighPct"))
        sym = stock.get("symbol", "")
        rows.append(f'''        <tr>
          <td class="sector-rank">{idx}</td>
          <td><strong>{esc(stock.get('stockName'))}</strong><small>{esc(sym)}</small></td>
          <td>{fmt_money(stock.get('cmp'))}</td>
          <td class="{class_for_pct(ch)}">{fmt_pct(ch)}</td>
          <td>{fmt_money(stock.get('high52'))}</td>
          <td class="{class_for_pct(down)}">{fmt_pct(down)}</td>
          <td><span class="sector-score-pill">{num(stock.get('strengthScore')):.1f}</span></td>
          <td>{esc(stock.get('signal'))}</td>
          <td><a class="sector-table-link" href="/?stock={esc(sym)}&amp;research=technical-analysis">Analyze</a></td>
        </tr>''')
    return "\n".join(rows)


def render_sector_page(sector: Dict[str, Any], data: Dict[str, Any], header: str, footer: str) -> str:
    name = sector["name"]
    slug = sector["slug"]
    stocks = sector.get("stocks", [])
    top = stocks[0].get("stockName", "-") if stocks else "-"
    title = f"{name} Stocks in India | Sector Wise List"
    desc = f"Explore {sector['stockCount']} {name} stocks with CMP, daily move, 52-week correction, AIT strength score and research links."
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"/>
<meta name="keywords" content="{esc(name)} stocks, {esc(str(name).lower())} sector stocks India, NSE sector stocks"/>
<meta name="robots" content="index, follow, max-image-preview:large"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&amp;family=Manrope:wght@500;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="/style.css?v=142" rel="stylesheet"/>
<link href="https://automationintrade.com/markets/sector/{esc(slug)}/" rel="canonical"/>
<meta property="og:title" content="{esc(name)} Stocks in India"/>
<meta property="og:description" content="{esc(desc)}"/>
<meta property="og:url" content="https://automationintrade.com/markets/sector/{esc(slug)}/"/>
<meta property="og:type" content="website"/>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"CollectionPage","name":"{esc(name)} Stocks in India","url":"https://automationintrade.com/markets/sector/{esc(slug)}/","description":"{esc(desc)}"}}</script>
</head>
<body>
{header}
<main>
<section class="sector-page-wrap section-padding" data-sector-detail="{esc(slug)}">
  <div class="sector-breadcrumbs"><a href="/">Home</a><span>›</span><a href="/markets/sector/">Markets</a><span>›</span><span>Sectors</span></div>
  <div class="sector-heading-row">
    <div>
      <h1>{esc(name)} stocks</h1>
      <p class="sector-count">{sector['stockCount']} companies · Average AIT score {sector['avgStrength']}</p>
      <p class="sector-intro">Explore the list of {esc(str(name).lower())} stocks with live-style research snapshot values from the Automation In Trade universe. Use this page to compare sector constituents before opening individual stock analysis.</p>
    </div>
    <div class="sector-data-note">Strongest in this group:<br/><strong>{esc(top)}</strong></div>
  </div>
  <div class="sector-stats-grid">
    <div><span>Stocks tracked</span><strong>{sector['stockCount']}</strong></div>
    <div><span>Avg AIT score</span><strong>{sector['avgStrength']}</strong></div>
    <div><span>Strong stocks</span><strong>{sector['strongCount']}</strong></div>
    <div><span>Updated</span><strong>{esc(data['updatedAt'])}</strong></div>
  </div>
  <div class="sector-search-box"><input id="stockSectorSearch" type="search" placeholder="Search company or symbol..." aria-label="Search company or symbol"></div>
  <div class="sector-table-card">
    <table class="sector-stock-table">
      <thead><tr><th>#</th><th>Company</th><th>CMP</th><th>1D</th><th>52W High</th><th>From High</th><th>AIT Score</th><th>Signal</th><th>Research</th></tr></thead>
      <tbody id="sectorStockRows">
{render_stock_rows(stocks)}
      </tbody>
    </table>
  </div>
  <section class="sector-info-block">
    <h2>How to read this sector page</h2>
    <p>The table is designed for quick screening. A high AIT score points to relative strength, while a larger 52-week correction highlights stocks trading far below their yearly high. Do not treat this as a buy or sell call. Use it as the first layer before checking price action, results, support-resistance and market mood.</p>
    <p><a class="btn btn-secondary" href="/markets/sector/">Back to all sectors</a> <a class="btn btn-primary" href="/market-tools/stock-strength-ranker/">Open Stock Strength Ranker</a></p>
  </section>
</section>
</main>
<script src="/markets/sector/sector-live.js?v=142"></script>
{footer}'''


def write_live_js() -> None:
    LIVE_JS.parent.mkdir(parents=True, exist_ok=True)
    LIVE_JS.write_text(r'''
(function(){
  const DATA_URL = '/market-data/sector-wise-stocks.json?ts=' + Date.now();
  const money = (v) => '₹' + Number(v || 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const pct = (v) => (Number(v || 0) > 0 ? '+' : '') + Number(v || 0).toFixed(2) + '%';
  const cls = (v) => Number(v || 0) >= 0 ? 'is-positive' : 'is-negative';
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  function bindIndexSearch(){
    const input = document.getElementById('sectorSearchInput');
    const rows = [...document.querySelectorAll('.sector-list-row')];
    if(input) input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      rows.forEach(row => { row.style.display = !q || (row.dataset.sectorName || '').includes(q) ? 'grid' : 'none'; });
    });
  }

  function bindStockSearch(){
    const input = document.getElementById('stockSectorSearch');
    const rows = [...document.querySelectorAll('#sectorStockRows tr')];
    if(input) input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      rows.forEach(row => { row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none'; });
    });
  }

  function renderIndex(data){
    const wrap = document.querySelector('[data-sector-index]');
    if(!wrap) return;
    const count = wrap.querySelector('.sector-count');
    if(count) count.textContent = `${data.sectorCount || 0} sectors · ${data.stockCount || 0} stocks`;
    const note = wrap.querySelector('.sector-data-note');
    if(note) note.innerHTML = `Updated: ${esc(data.updatedAt || '')}<br>Source: Latest AIT stock strength universe`;
    const rows = document.getElementById('sectorListRows');
    if(!rows) return;
    rows.innerHTML = (data.sectors || []).map(sector => {
      const top = (sector.stocks && sector.stocks[0]) ? sector.stocks[0].stockName : '-';
      return `<a class="sector-list-row" href="/markets/sector/${esc(sector.slug)}/" data-sector-name="${esc(String(sector.name || '').toLowerCase())}">
        <span class="sector-name">${esc(sector.name)}</span>
        <span>${sector.stockCount || 0} stocks</span>
        <span>${Number(sector.avgStrength || 0).toFixed(1)}</span>
        <span>${esc(top)}</span>
      </a>`;
    }).join('');
    bindIndexSearch();
  }

  function renderDetail(data){
    const wrap = document.querySelector('[data-sector-detail]');
    if(!wrap) return;
    const slug = wrap.dataset.sectorDetail;
    const sector = (data.sectors || []).find(s => s.slug === slug);
    if(!sector) return;
    const top = (sector.stocks && sector.stocks[0]) ? sector.stocks[0].stockName : '-';
    const count = wrap.querySelector('.sector-count');
    if(count) count.textContent = `${sector.stockCount || 0} companies · Average AIT score ${Number(sector.avgStrength || 0).toFixed(1)}`;
    const note = wrap.querySelector('.sector-data-note');
    if(note) note.innerHTML = `Strongest in this group:<br><strong>${esc(top)}</strong>`;
    const stats = wrap.querySelector('.sector-stats-grid');
    if(stats) stats.innerHTML = `
      <div><span>Stocks tracked</span><strong>${sector.stockCount || 0}</strong></div>
      <div><span>Avg AIT score</span><strong>${Number(sector.avgStrength || 0).toFixed(1)}</strong></div>
      <div><span>Strong stocks</span><strong>${sector.strongCount || 0}</strong></div>
      <div><span>Updated</span><strong>${esc(data.updatedAt || '')}</strong></div>`;
    const body = document.getElementById('sectorStockRows');
    if(body) body.innerHTML = (sector.stocks || []).map((stock, i) => {
      const change = Number(stock.changePct || 0);
      const down = Number(stock.downFromHighPct || 0);
      const symbol = stock.symbol || '';
      return `<tr>
        <td class="sector-rank">${i + 1}</td>
        <td><strong>${esc(stock.stockName)}</strong><small>${esc(symbol)}</small></td>
        <td>${money(stock.cmp)}</td>
        <td class="${cls(change)}">${pct(change)}</td>
        <td>${money(stock.high52)}</td>
        <td class="${cls(down)}">${pct(down)}</td>
        <td><span class="sector-score-pill">${Number(stock.strengthScore || 0).toFixed(1)}</span></td>
        <td>${esc(stock.signal)}</td>
        <td><a class="sector-table-link" href="/?stock=${encodeURIComponent(symbol)}&research=technical-analysis">Analyze</a></td>
      </tr>`;
    }).join('');
    bindStockSearch();
  }

  fetch(DATA_URL, {cache: 'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => { renderIndex(data); renderDetail(data); })
    .catch(() => { bindIndexSearch(); bindStockSearch(); });
})();
'''.strip() + "\n", encoding="utf-8")


def write_pages(data: Dict[str, Any]) -> None:
    header, footer = extract_header_footer()
    SECTOR_DIR.mkdir(parents=True, exist_ok=True)
    (SECTOR_DIR / "index.html").write_text(render_sector_index(data, header, footer), encoding="utf-8")
    for sector in data["sectors"]:
        folder = SECTOR_DIR / sector["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(render_sector_page(sector, data, header, footer), encoding="utf-8")
    write_live_js()


def main() -> int:
    data = merge_sector_data()
    write_json(SECTOR_FILE, data)
    write_pages(data)
    print("Sector-wise stock data rebuilt from latest stock-strength-ranker.json")
    print(f"Updated JSON: {SECTOR_FILE.relative_to(ROOT)}")
    print(f"Updated pages: {SECTOR_DIR.relative_to(ROOT)}/")
    print(f"Updated live JS: {LIVE_JS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
