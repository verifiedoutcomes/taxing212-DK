"""
Trading212 CSV parser.

Parses Trading212 account history CSV exports into structured transaction
records. Supports both the old (positional) and new (header-based, 2024+)
CSV formats.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import T212_COLUMNS_NEW


@dataclass
class Trade:
    """A single buy or sell trade."""
    uid: int
    timestamp: datetime
    action: str           # "Buy" or "Sell"
    order_type: str       # Original action string (e.g. "Market buy")
    ticker: str
    name: str
    isin: str
    shares: float
    price_per_share: float
    currency_price: str   # Currency of price_per_share
    exchange_rate: float   # T212's FX rate (to account currency)
    total: float           # Total in account currency
    total_currency: str    # Account currency (GBP, EUR, etc.)
    withholding_tax: float
    wht_currency: str
    stamp_duty: float
    transaction_fee: float
    notes: str
    t212_id: str

    # Computed fields
    total_dkk: float = 0.0
    price_dkk: float = 0.0  # price per share in DKK


@dataclass
class Dividend:
    """A dividend payment."""
    uid: int
    timestamp: datetime
    ticker: str
    name: str
    isin: str
    amount: float           # In account currency
    amount_currency: str
    amount_dkk: float
    withholding_tax: float
    wht_currency: str
    withholding_tax_dkk: float
    is_danish: bool          # True if ISIN starts with DK


@dataclass
class Deposit:
    uid: int
    timestamp: datetime
    amount: float
    currency: str


@dataclass
class Withdrawal:
    uid: int
    timestamp: datetime
    amount: float
    currency: str


@dataclass
class Interest:
    """Interest payment (Trading212 pays interest on cash)."""
    uid: int
    timestamp: datetime
    amount: float
    currency: str
    amount_dkk: float


@dataclass
class ParsedData:
    """Container for all parsed data from CSV files."""
    trades: list[Trade] = field(default_factory=list)
    dividends: list[Dividend] = field(default_factory=list)
    deposits: list[Deposit] = field(default_factory=list)
    withdrawals: list[Withdrawal] = field(default_factory=list)
    interest: list[Interest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    account_currency: str = ""


_uid_counter = 0


def _next_uid() -> int:
    global _uid_counter
    _uid_counter += 1
    return _uid_counter


def _safe_float(val: str | None) -> float:
    """Parse a string to float, handling commas and empty values."""
    if val is None or val.strip() == "":
        return 0.0
    cleaned = val.strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_timestamp(date_str: str) -> datetime:
    """Parse T212 date formats."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def _detect_format(headers: list[str]) -> str:
    """Detect whether this is old (positional) or new (header) format."""
    # New format has specific named headers
    header_set = set(h.strip() for h in headers)
    if "Action" in header_set or "Time" in header_set:
        return "new"
    return "old"


def _parse_row_new(row: dict[str, str]) -> dict:
    """Parse a row from the new (header-based) CSV format."""
    result = {}
    for csv_header, internal_name in T212_COLUMNS_NEW.items():
        result[internal_name] = row.get(csv_header, "")
    return result


def parse_csv(filepath: str) -> ParsedData:
    """Parse a Trading212 CSV export file.

    Returns ParsedData containing all transactions.
    """
    path = Path(filepath)
    data = ParsedData()

    with open(path, newline="", encoding="utf-8-sig") as f:
        # First, try to read as a standard CSV
        reader = csv.reader(f)
        headers = next(reader)

        fmt = _detect_format(headers)

        if fmt == "new":
            # Re-read as DictReader
            f.seek(0)
            dict_reader = csv.DictReader(f)

            for row in dict_reader:
                _process_row_new(row, data)
        else:
            # Old positional format
            for row in reader:
                if not row or not row[0].strip():
                    continue
                _process_row_old(row, data)

    # Sort trades by timestamp
    data.trades.sort(key=lambda t: t.timestamp)
    data.dividends.sort(key=lambda d: d.timestamp)

    return data


def _process_row_new(row: dict[str, str], data: ParsedData) -> None:
    """Process a single row from the new-format CSV."""
    action = row.get("Action", "").strip()
    if not action:
        return

    first_word = action.split()[0].lower() if action else ""

    try:
        if action == "Deposit":
            data.deposits.append(Deposit(
                uid=_next_uid(),
                timestamp=_parse_timestamp(row.get("Time", "")),
                amount=_safe_float(row.get("Total", "")),
                currency=row.get("Total Currency", row.get("Currency (Total)", "")).strip(),
            ))
        elif action == "Withdrawal":
            data.withdrawals.append(Withdrawal(
                uid=_next_uid(),
                timestamp=_parse_timestamp(row.get("Time", "")),
                amount=_safe_float(row.get("Total", "")),
                currency=row.get("Total Currency", row.get("Currency (Total)", "")).strip(),
            ))
        elif first_word == "dividend":
            isin = row.get("ISIN", "").strip()
            total_currency = row.get("Total Currency", row.get("Currency (Total)", "")).strip()
            data.dividends.append(Dividend(
                uid=_next_uid(),
                timestamp=_parse_timestamp(row.get("Time", "")),
                ticker=row.get("Ticker", "").strip(),
                name=row.get("Name", "").strip(),
                isin=isin,
                amount=_safe_float(row.get("Total", "")),
                amount_currency=total_currency,
                amount_dkk=0.0,  # Calculated later
                withholding_tax=_safe_float(row.get("Withholding tax", "")),
                wht_currency=row.get("Currency (Withholding tax)", "").strip(),
                withholding_tax_dkk=0.0,  # Calculated later
                is_danish=isin.startswith("DK"),
            ))
            if not data.account_currency and total_currency:
                data.account_currency = total_currency
        elif "interest" in action.lower():
            total_currency = row.get("Total Currency", row.get("Currency (Total)", "")).strip()
            data.interest.append(Interest(
                uid=_next_uid(),
                timestamp=_parse_timestamp(row.get("Time", "")),
                amount=_safe_float(row.get("Total", "")),
                currency=total_currency,
                amount_dkk=0.0,
            ))
        elif first_word in ("buy", "sell") or "buy" in action.lower() or "sell" in action.lower():
            raw_type = "Buy" if "buy" in action.lower() else "Sell"
            price_currency = row.get("Currency (Price / share)", "").strip()
            total_currency = row.get("Total Currency", row.get("Currency (Total)", "")).strip()

            if not data.account_currency and total_currency:
                data.account_currency = total_currency

            data.trades.append(Trade(
                uid=_next_uid(),
                timestamp=_parse_timestamp(row.get("Time", "")),
                action=raw_type,
                order_type=action,
                ticker=row.get("Ticker", "").strip(),
                name=row.get("Name", "").strip(),
                isin=row.get("ISIN", "").strip(),
                shares=_safe_float(row.get("No. of shares", "")),
                price_per_share=_safe_float(row.get("Price / share", "")),
                currency_price=price_currency,
                exchange_rate=_safe_float(row.get("Exchange rate", "")),
                total=abs(_safe_float(row.get("Total", ""))),
                total_currency=total_currency,
                withholding_tax=_safe_float(row.get("Withholding tax", "")),
                wht_currency=row.get("Currency (Withholding tax)", "").strip(),
                stamp_duty=_safe_float(
                    row.get("Stamp duty", "") or row.get("Stamp duty reserve tax", "")
                ),
                transaction_fee=_safe_float(
                    row.get("Transaction fee", "")
                    or row.get("Currency conversion fee", "")
                ),
                notes=row.get("Notes", "").strip(),
                t212_id=row.get("ID", "").strip(),
            ))
        else:
            # Unknown action type - log it
            data.errors.append(f"Unknown action type: '{action}' at {row.get('Time', '?')}")

    except (ValueError, KeyError) as e:
        data.errors.append(f"Error parsing row: {e} — row: {row.get('Action', '?')} at {row.get('Time', '?')}")


def _process_row_old(row: list[str], data: ParsedData) -> None:
    """Process a single row from the old positional CSV format."""
    if len(row) < 11:
        return

    action = row[0].strip()
    first_word = action.split()[0].lower() if action else ""

    def col(i: int) -> str:
        return row[i].strip() if i < len(row) else ""

    try:
        if action == "Deposit":
            data.deposits.append(Deposit(
                uid=_next_uid(),
                timestamp=_parse_timestamp(col(1)),
                amount=_safe_float(col(10)),
                currency="GBP",  # Old format was always GBP
            ))
        elif action == "Withdrawal":
            data.withdrawals.append(Withdrawal(
                uid=_next_uid(),
                timestamp=_parse_timestamp(col(1)),
                amount=_safe_float(col(10)),
                currency="GBP",
            ))
        elif first_word == "dividend":
            isin = col(2)
            data.dividends.append(Dividend(
                uid=_next_uid(),
                timestamp=_parse_timestamp(col(1)),
                ticker=col(3),
                name=col(4),
                isin=isin,
                amount=_safe_float(col(10)),
                amount_currency="GBP",
                amount_dkk=0.0,
                withholding_tax=_safe_float(col(11)),
                wht_currency=col(12) if len(row) > 12 else "",
                withholding_tax_dkk=0.0,
                is_danish=isin.startswith("DK"),
            ))
            if not data.account_currency:
                data.account_currency = "GBP"
        elif first_word in ("buy", "sell") or "buy" in action.lower() or "sell" in action.lower():
            raw_type = "Buy" if "buy" in action.lower() else "Sell"
            data.trades.append(Trade(
                uid=_next_uid(),
                timestamp=_parse_timestamp(col(1)),
                action=raw_type,
                order_type=action,
                ticker=col(3),
                name=col(4),
                isin=col(2),
                shares=_safe_float(col(5)),
                price_per_share=_safe_float(col(6)),
                currency_price=col(7),
                exchange_rate=_safe_float(col(8)),
                total=abs(_safe_float(col(10))),
                total_currency="GBP",
                withholding_tax=_safe_float(col(11)) if len(row) > 11 else 0.0,
                wht_currency=col(12) if len(row) > 12 else "",
                stamp_duty=_safe_float(col(14)) if len(row) > 14 else 0.0,
                transaction_fee=_safe_float(col(15)) if len(row) > 15 else 0.0,
                notes=col(17) if len(row) > 17 else "",
                t212_id=col(18) if len(row) > 18 else "",
            ))
            if not data.account_currency:
                data.account_currency = "GBP"

    except (ValueError, IndexError) as e:
        data.errors.append(f"Error parsing row: {e} — action: {action}")
