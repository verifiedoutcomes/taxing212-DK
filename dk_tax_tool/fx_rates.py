"""
Currency conversion using Nationalbanken exchange rates.

Supports loading rates from CSV files downloaded from:
https://nationalbanken.statistikbank.dk/909

Expected CSV format (flexible - auto-detected):
  Date,Currency,Rate
  2025-01-02,GBP,8.8234
  2025-01-02,USD,7.0512

Or per-currency files with columns: Date, Rate

Rates are expressed as DKK per 1 unit of foreign currency (or per 100 units
for some Nationalbanken exports).
"""

import csv
from datetime import date, timedelta, datetime
from pathlib import Path


class FXRateStore:
    """Stores and looks up daily exchange rates for converting to DKK."""

    def __init__(self):
        # {currency: {date_str: rate_as_dkk_per_1_unit}}
        self._rates: dict[str, dict[str, float]] = {}

    def load_csv(self, filepath: str, currency: str | None = None) -> None:
        """Load exchange rates from a CSV file.

        Auto-detects format:
        - Multi-currency: columns Date, Currency, Rate
        - Single-currency: columns Date, Rate (currency must be specified or
          inferred from filename like 'GBP.csv')
        - Nationalbanken format: may have rates per 100 units
        """
        path = Path(filepath)

        with open(path, newline="", encoding="utf-8-sig") as f:
            # Sniff delimiter
            sample = f.read(2048)
            f.seek(0)

            delimiter = ";"  # Nationalbanken often uses semicolons
            if sample.count(",") > sample.count(";"):
                delimiter = ","

            reader = csv.reader(f, delimiter=delimiter)
            headers = [h.strip().lower() for h in next(reader)]

            # Detect format
            has_currency_col = "currency" in headers or "valuta" in headers
            date_col = self._find_col(headers, ["date", "dato", "observation"])
            rate_col = self._find_col(headers, ["rate", "kurs", "value", "closing"])
            currency_col = self._find_col(headers, ["currency", "valuta"]) if has_currency_col else None

            # If single-currency file, determine currency
            file_currency = currency
            if not has_currency_col and not file_currency:
                # Try to infer from filename (e.g., "GBP.csv", "usd_rates.csv")
                stem = path.stem.upper()
                for c in ["GBP", "USD", "EUR", "SEK", "NOK", "CHF", "JPY", "CAD", "AUD"]:
                    if c in stem:
                        file_currency = c
                        break
                if not file_currency:
                    raise ValueError(
                        f"Cannot determine currency for {filepath}. "
                        f"Pass currency= or name file like 'GBP.csv'."
                    )

            for row in reader:
                if len(row) <= max(date_col, rate_col):
                    continue

                date_str = row[date_col].strip()
                rate_str = row[rate_col].strip().replace(",", ".")

                if not rate_str or not date_str:
                    continue

                try:
                    rate = float(rate_str)
                except ValueError:
                    continue

                # Normalise date to YYYY-MM-DD
                parsed_date = self._parse_date(date_str)
                if parsed_date is None:
                    continue

                cur = row[currency_col].strip().upper() if currency_col is not None else file_currency

                # Nationalbanken sometimes reports per 100 units
                # Heuristic: if rate > 100 for GBP/USD/EUR, it's per 100
                if rate > 50 and cur in ("GBP", "USD", "EUR", "CHF", "CAD", "AUD"):
                    rate = rate / 100

                if cur not in self._rates:
                    self._rates[cur] = {}
                self._rates[cur][parsed_date] = rate

    def _find_col(self, headers: list[str], candidates: list[str]) -> int:
        for i, h in enumerate(headers):
            for c in candidates:
                if c in h:
                    return i
        return 0  # fallback to first column

    def _parse_date(self, date_str: str) -> str | None:
        """Parse various date formats to YYYY-MM-DD."""
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y%m%d"):
            try:
                d = datetime.strptime(date_str, fmt)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def get_rate(self, currency: str, transaction_date: str | date) -> float:
        """Get the DKK exchange rate for a given currency and date.

        If the exact date is not available (weekend/holiday), uses the most
        recent preceding business day rate, per Danish tax practice.

        Returns DKK per 1 unit of foreign currency.
        """
        if currency == "DKK":
            return 1.0

        cur = currency.upper()

        # Handle GBX (pence) -> GBP
        if cur == "GBX":
            return self.get_rate("GBP", transaction_date) / 100

        if cur not in self._rates:
            raise ValueError(
                f"No exchange rates loaded for {cur}. "
                f"Load a rate file with load_csv()."
            )

        if isinstance(transaction_date, date):
            date_str = transaction_date.strftime("%Y-%m-%d")
        else:
            date_str = self._parse_date(transaction_date) or transaction_date

        # Look back up to 7 days for the nearest business day
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        for _ in range(8):
            key = d.strftime("%Y-%m-%d")
            if key in self._rates[cur]:
                return self._rates[cur][key]
            d -= timedelta(days=1)

        raise ValueError(
            f"No exchange rate found for {cur} on or near {date_str}. "
            f"Ensure rate data covers this date range."
        )

    def convert_to_dkk(self, amount: float, currency: str, transaction_date: str | date) -> float:
        """Convert an amount in foreign currency to DKK."""
        rate = self.get_rate(currency, transaction_date)
        return amount * rate

    @property
    def loaded_currencies(self) -> list[str]:
        return list(self._rates.keys())

    def has_currency(self, currency: str) -> bool:
        cur = currency.upper()
        if cur == "DKK":
            return True
        if cur == "GBX":
            cur = "GBP"
        return cur in self._rates
