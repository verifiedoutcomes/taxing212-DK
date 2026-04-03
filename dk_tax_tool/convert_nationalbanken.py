#!/usr/bin/env python3
"""
Convert Nationalbanken transposed TSV data into per-currency CSV files.

Input format (from https://nationalbanken.statistikbank.dk/909):
  - Tab-separated
  - Row 1: header with dates as 2025M01D02
  - Subsequent rows: currency name followed by rates (per 100 units)

Output: One CSV per currency in the output directory, e.g. GBP.csv, USD.csv, EUR.csv
"""

import csv
import re
import sys
from pathlib import Path


# Map Nationalbanken currency names to ISO codes
CURRENCY_MAP = {
    "euro": "EUR",
    "us dollars": "USD",
    "us dollar": "USD",
    "gbp": "GBP",
    "pound sterling": "GBP",
    "british pounds": "GBP",
    "swiss francs": "CHF",
    "swiss franc": "CHF",
    "canadian dollars": "CAD",
    "canadian dollar": "CAD",
    "swedish kronor": "SEK",
    "swedish krona": "SEK",
    "norwegian kroner": "NOK",
    "norwegian krone": "NOK",
    "japanese yen": "JPY",
    "australian dollars": "AUD",
}


def parse_nationalbanken_date(date_str: str) -> str:
    """Parse '2025M01D02' into '2025-01-02'."""
    m = re.match(r"(\d{4})M(\d{2})D(\d{2})", date_str.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def detect_currency(name: str) -> str:
    """Map a Nationalbanken currency name to ISO code."""
    lower = name.strip().lower()
    # Direct match
    for key, code in CURRENCY_MAP.items():
        if key in lower:
            return code
    # Try the name itself as a code (e.g. "GBP")
    upper = name.strip().upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return upper[:3]  # fallback


def convert(input_path: str, output_dir: str) -> list[str]:
    """Convert Nationalbanken TSV to per-currency CSVs.

    Returns list of created file paths.
    """
    inpath = Path(input_path)
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    with open(inpath, newline="", encoding="utf-8-sig") as f:
        lines = f.read().strip().split("\n")

    if len(lines) < 2:
        raise ValueError("Input file has fewer than 2 lines")

    # Parse header row for dates
    header_parts = lines[0].split("\t")
    dates = []
    for part in header_parts[1:]:  # skip the label column
        d = parse_nationalbanken_date(part.strip())
        dates.append(d)

    created_files = []

    # Parse each currency row
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        currency_name = parts[0].strip()
        currency_code = detect_currency(currency_name)

        rates = parts[1:]

        outfile = outdir / f"{currency_code}.csv"
        with open(outfile, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Rate"])

            for i, rate_str in enumerate(rates):
                if i >= len(dates) or not dates[i]:
                    continue
                rate_str = rate_str.strip().replace(",", ".")
                if not rate_str:
                    continue
                try:
                    # Rates are per 100 units — convert to per 1 unit
                    rate = float(rate_str) / 100
                    writer.writerow([dates[i], f"{rate:.6f}"])
                except ValueError:
                    continue

        created_files.append(str(outfile))
        print(f"  Created {outfile} ({currency_code}, {len(rates)} rates)")

    return created_files


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m dk_tax_tool.convert_nationalbanken <input.tsv> [output_dir]")
        print()
        print("Converts Nationalbanken transposed TSV to per-currency CSV files.")
        print("Default output directory: fx_data/")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "fx_data"

    print(f"Converting {input_path} → {output_dir}/")
    files = convert(input_path, output_dir)
    print(f"\nDone. Created {len(files)} rate files.")


if __name__ == "__main__":
    main()
