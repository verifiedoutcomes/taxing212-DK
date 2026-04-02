#!/usr/bin/env python3
"""
Taxing212-DK: Danish tax calculator for Trading212 accounts.

Usage:
    python -m dk_tax_tool.main --trades trades.csv --rates GBP.csv USD.csv EUR.csv
    python -m dk_tax_tool.main --trades trades.csv --rates rates.csv --export-csv

For help:
    python -m dk_tax_tool.main --help
"""

import argparse
import sys
from pathlib import Path

from .parser import parse_csv
from .fx_rates import FXRateStore
from .calculator import calculate
from .output import (
    print_full_report,
    generate_disposals_csv,
    generate_dividends_csv,
    generate_summary_csv,
)


def main():
    parser = argparse.ArgumentParser(
        description="Taxing212-DK: Danish tax calculator for Trading212 CSV exports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with separate FX rate files:
  python -m dk_tax_tool.main --trades my_trades.csv --rates GBP.csv USD.csv EUR.csv

  # With a single multi-currency rate file:
  python -m dk_tax_tool.main --trades my_trades.csv --rates nationalbanken_rates.csv

  # Export CSV reports alongside the console output:
  python -m dk_tax_tool.main --trades my_trades.csv --rates rates.csv --export-csv

  # Multiple trade files (if history is split):
  python -m dk_tax_tool.main --trades trades_2024.csv trades_2025.csv --rates rates.csv

Exchange Rate Files:
  Download from https://nationalbanken.statistikbank.dk/909
  Supports formats:
    - Multi-currency CSV: Date,Currency,Rate (DKK per 1 unit)
    - Single-currency CSV: Date,Rate (name file like GBP.csv)
    - Nationalbanken semicolon-delimited format
        """,
    )

    parser.add_argument(
        "--trades", "-t",
        nargs="+",
        required=True,
        help="Trading212 CSV export file(s). Full history recommended.",
    )
    parser.add_argument(
        "--rates", "-r",
        nargs="+",
        required=True,
        help="Nationalbanken exchange rate CSV file(s). "
             "One multi-currency file, or separate per-currency files.",
    )
    parser.add_argument(
        "--export-csv", "-e",
        action="store_true",
        default=False,
        help="Also export detailed CSV reports (disposals, dividends, summary).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Directory for exported CSV files (default: current directory).",
    )
    parser.add_argument(
        "--married",
        action="store_true",
        default=False,
        help="Double the progressionsgrænse (married couple, unused spouse allowance).",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress console output (only write CSV files if --export-csv is set).",
    )

    args = parser.parse_args()

    # Handle married flag
    if args.married:
        from . import config
        config.MARRIED_DOUBLE_THRESHOLD = True

    # --- Load exchange rates ---
    fx = FXRateStore()
    for rate_file in args.rates:
        path = Path(rate_file)
        if not path.exists():
            print(f"ERROR: Rate file not found: {rate_file}", file=sys.stderr)
            sys.exit(1)
        try:
            fx.load_csv(str(path))
            print(f"  Loaded FX rates from: {path.name}")
        except Exception as e:
            print(f"ERROR loading rate file {rate_file}: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"  Currencies available: {', '.join(fx.loaded_currencies)}")
    print()

    # --- Parse trade files ---
    from .parser import ParsedData
    combined = ParsedData()

    for trade_file in args.trades:
        path = Path(trade_file)
        if not path.exists():
            print(f"ERROR: Trade file not found: {trade_file}", file=sys.stderr)
            sys.exit(1)
        try:
            parsed = parse_csv(str(path))
            combined.trades.extend(parsed.trades)
            combined.dividends.extend(parsed.dividends)
            combined.deposits.extend(parsed.deposits)
            combined.withdrawals.extend(parsed.withdrawals)
            combined.interest.extend(parsed.interest)
            combined.errors.extend(parsed.errors)
            if not combined.account_currency and parsed.account_currency:
                combined.account_currency = parsed.account_currency
            print(f"  Loaded trades from: {path.name}")
            print(f"    → {len(parsed.trades)} trades, {len(parsed.dividends)} dividends, "
                  f"{len(parsed.interest)} interest payments")
        except Exception as e:
            print(f"ERROR loading trade file {trade_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Sort combined data
    combined.trades.sort(key=lambda t: t.timestamp)
    combined.dividends.sort(key=lambda d: d.timestamp)
    combined.interest.sort(key=lambda i: i.timestamp)

    print(f"\n  Account currency detected: {combined.account_currency}")
    print(f"  Total: {len(combined.trades)} trades, {len(combined.dividends)} dividends")
    print()

    # --- Calculate ---
    try:
        result = calculate(combined, fx)
    except Exception as e:
        print(f"ERROR during calculation: {e}", file=sys.stderr)
        raise

    # --- Output ---
    if not args.quiet:
        report = print_full_report(result)
        print(report)

    # --- Export CSV ---
    if args.export_csv:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        year = result.tax_year
        disposals_path = out_dir / f"taxing212_dk_disposals_{year}.csv"
        dividends_path = out_dir / f"taxing212_dk_dividends_{year}.csv"
        summary_path = out_dir / f"taxing212_dk_summary_{year}.csv"

        generate_disposals_csv(result, str(disposals_path))
        generate_dividends_csv(result, str(dividends_path))
        generate_summary_csv(result, str(summary_path))

        print(f"\n  CSV files exported to: {out_dir.absolute()}")
        print(f"    → {disposals_path.name}")
        print(f"    → {dividends_path.name}")
        print(f"    → {summary_path.name}")


if __name__ == "__main__":
    main()
