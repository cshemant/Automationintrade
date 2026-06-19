"""
UpdateAllData.py

One-command update runner for Automation In Trade.

Use this file instead of remembering multiple scripts.

Most common commands:

  python UpdateAllData.py
  python UpdateAllData.py --mode all

What --mode all does:
  1) Updates Daily Market / scanner JSON via GenerateMarketToolsJson.py --mode all
  2) Generates Price Action research-card JSON via GeneratePriceActionJson.py
  3) Generates Results research-card JSON via GenerateResultsJson.py
  4) Generates Technical Analysis research-card JSON via GenerateTechnicalAnalysisJson.py
  5) Rebuilds homepage stock search index via GenerateStockResearchIndex.py

Useful testing commands:

  python UpdateAllData.py --mode research --symbols MUTHOOTFIN,RELIANCE,TCS
  python UpdateAllData.py --mode technical-analysis --limit 20
  python UpdateAllData.py --mode price-action --symbols AXISBANK,M&M
  python UpdateAllData.py --mode results --symbols RELIANCE,TCS
  python UpdateAllData.py --mode stock-index

Notes:
- This runner updates market tools plus all homepage stock-research JSON generators.
- Use --symbols for quick testing on selected stocks.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent

MARKET_MODES = {
    "52w",
    "market-snapshot",
    "fii-dii",
    "index-performance",
    "stock-strength",
    "momentum-scanner",
    "volume-surge",
    "near-breakout",
}


def run_step(label: str, command: List[str]) -> None:
    """Run one update step and stop immediately if it fails."""
    print("\n" + "=" * 72)
    print(f"STEP: {label}")
    print("CMD : " + " ".join(command))
    print("=" * 72)

    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(f"\n❌ Failed: {label} (exit code {completed.returncode})")
    print(f"✅ Completed: {label}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all Automation In Trade JSON update scripts with one command."
    )
    parser.add_argument(
        "--mode",
        default="all",
        choices=[
            "all",
            "market",
            "research",
            "price-action",
            "results",
            "technical-analysis",
            "stock-index",
            *sorted(MARKET_MODES),
        ],
        help=(
            "all = market tools + price-action JSON + results JSON + technical-analysis JSON + stock search index. "
            "market = only GenerateMarketToolsJson.py --mode all + stock index. "
            "research = price-action + results + technical-analysis + stock index. "
            "price-action/results/technical-analysis = only that research JSON + stock index. "
            "stock-index = rebuild search index only. "
            "Other values are passed to GenerateMarketToolsJson.py --mode."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=80,
        help="Batch size for GenerateTechnicalAnalysisJson.py. Default: 80.",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbols for quick research testing across Price Action, Results, and Technical Analysis, e.g. RELIANCE,TCS,M&M.",
    )
    parser.add_argument(
        "--technical-symbols",
        default="",
        help="Backward-compatible alias for technical-analysis symbol testing. Prefer --symbols.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional symbol limit for research JSON testing.",
    )
    parser.add_argument(
        "--skip-technical",
        action="store_true",
        help="Use with --mode all if you want to skip Technical Analysis JSON generation.",
    )
    parser.add_argument(
        "--skip-price-action",
        action="store_true",
        help="Use with --mode all if you want to skip Price Action JSON generation.",
    )
    parser.add_argument(
        "--skip-results",
        action="store_true",
        help="Use with --mode all if you want to skip Results JSON generation.",
    )
    return parser.parse_args()


def run_market(mode: str) -> None:
    run_step(
        f"Market tools JSON ({mode})",
        [sys.executable, "GenerateMarketToolsJson.py", "--mode", mode],
    )


def _selected_symbols(args: argparse.Namespace) -> str:
    return (args.symbols or args.technical_symbols or "").strip()


def run_price_action(args: argparse.Namespace) -> None:
    cmd = [sys.executable, "GeneratePriceActionJson.py"]
    symbols = _selected_symbols(args)
    if symbols:
        cmd += ["--symbols", symbols]
    if args.limit and args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    run_step("Price Action research JSON", cmd)


def run_results(args: argparse.Namespace) -> None:
    cmd = [sys.executable, "GenerateResultsJson.py"]
    symbols = _selected_symbols(args)
    if symbols:
        cmd += ["--symbols", symbols]
    if args.limit and args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    run_step("Results research JSON", cmd)


def run_technical(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "GenerateTechnicalAnalysisJson.py",
        "--batch-size",
        str(args.batch_size),
    ]
    symbols = _selected_symbols(args)
    if symbols:
        cmd += ["--symbols", symbols]
    if args.limit and args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    run_step("Technical Analysis research JSON", cmd)


def run_stock_index() -> None:
    run_step("Homepage stock research search index", [sys.executable, "GenerateStockResearchIndex.py"])


def main() -> int:
    args = parse_args()
    mode = args.mode

    print("Automation In Trade one-command update")
    print(f"Root: {ROOT}")
    print(f"Mode: {mode}")

    if mode == "all":
        run_market("all")
        if not args.skip_price_action:
            run_price_action(args)
        if not args.skip_results:
            run_results(args)
        if not args.skip_technical:
            run_technical(args)
        run_stock_index()

    elif mode == "market":
        run_market("all")
        run_stock_index()

    elif mode == "research":
        run_price_action(args)
        run_results(args)
        run_technical(args)
        run_stock_index()

    elif mode == "price-action":
        run_price_action(args)
        run_stock_index()

    elif mode == "results":
        run_results(args)
        run_stock_index()

    elif mode == "technical-analysis":
        run_technical(args)
        run_stock_index()

    elif mode == "stock-index":
        run_stock_index()

    elif mode in MARKET_MODES:
        run_market(mode)
        # Rebuilding the index is cheap and keeps homepage search in sync
        # when 52w/index universe data changes.
        run_stock_index()

    else:  # Defensive fallback; argparse choices should prevent this.
        raise SystemExit(f"Unknown mode: {mode}")

    print("\n" + "=" * 72)
    print("✅ ALL REQUESTED UPDATES COMPLETED")
    print("Generated/updated folders to commit/deploy:")
    print("  market-data/")
    print("  stock-research-data/")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
