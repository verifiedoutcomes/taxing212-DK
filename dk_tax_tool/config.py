"""
Danish tax configuration for tax year 2025.

Aktieindkomst (share income) rates and thresholds per Danish tax law.
Sources: skat.dk, skatteministeriet.dk
"""

TAX_YEAR = 2025
TAX_YEAR_START = f"{TAX_YEAR}-01-01"
TAX_YEAR_END = f"{TAX_YEAR}-12-31"

# Aktieindkomst tax rates (2025)
# Below progressionsgrænsen: 27%
# Above progressionsgrænsen: 42%
AKTIEINDKOMST_LOW_RATE = 0.27
AKTIEINDKOMST_HIGH_RATE = 0.42

# Progressionsgrænsen for 2025 (per person)
# 2023: 58,900 / 2024: 61,000 / 2025: 63,300 DKK (personskattelovens § 20 regulering)
PROGRESSIONSGRAENSE = 63_300

# Max creditable foreign dividend withholding tax under most Danish tax
# treaties (e.g. US-DK DBO art. 10): 15% of the gross dividend.
# Anything withheld above this must be reclaimed from the foreign tax
# authority, not credited in Denmark.
TREATY_WHT_CREDIT_CAP = 0.15

# For married couples filing jointly, the threshold doubles if one spouse
# doesn't use their full allowance. Set to True if applicable.
MARRIED_DOUBLE_THRESHOLD = False

# Trading212 CSV column indices (old format)
# These map to the positional columns in Trading212's CSV export.
# The tool also supports header-based parsing for the new format.
T212_COLUMNS_OLD = {
    "action": 0,
    "time": 1,
    "isin": 2,
    "ticker": 3,
    "name": 4,
    "shares": 5,
    "price_per_share": 6,
    "currency_price": 7,
    "exchange_rate": 8,
    "result_gbp": 9,      # Result in account currency (GBP)
    "total_gbp": 10,      # Total in account currency (GBP)
    "withholding_tax": 11,
    "wht_currency": 12,
    "charge_amount": 13,
    "stamp_duty": 14,
    "transaction_fee": 15,
    "finra_fee": 16,
    "notes": 17,
    "id": 18,
    "french_tax": 19,
}

# New T212 CSV column headers (2024+ format)
T212_COLUMNS_NEW = {
    "Action": "action",
    "Time": "time",
    "ISIN": "isin",
    "Ticker": "ticker",
    "Name": "name",
    "No. of shares": "shares",
    "Price / share": "price_per_share",
    "Currency (Price / share)": "currency_price",
    "Exchange rate": "exchange_rate",
    "Result": "result",
    "Result Currency": "result_currency",      # New in 2024+ format
    "Total": "total",
    "Total Currency": "total_currency",        # New in 2024+ format
    "Withholding tax": "withholding_tax",
    "Currency (Withholding tax)": "wht_currency",
    "Charge amount": "charge_amount",
    "Charge amount Currency": "charge_currency",
    "Stamp duty": "stamp_duty",
    "Transaction fee": "transaction_fee",
    "Finra fee": "finra_fee",
    "Notes": "notes",
    "ID": "id",
    "French transaction tax": "french_tax",
    "Currency conversion fee": "conversion_fee",
}

# Account base currency (Trading212 accounts for non-UK may be EUR or GBP)
# This is detected automatically from the CSV but can be overridden.
ACCOUNT_CURRENCY = None  # Auto-detect

# Skat.dk rubrik mapping (oplysningsskema / årsopgørelse)
# NOTE: For a Danish resident holding shares via a FOREIGN broker
# (Trading212), foreign dividends and foreign tax go in the
# "Udenlandsk indkomst" section of TastSelv, not the main dividend boxes.
SKAT_RUBRIKKER = {
    61: "Udbytte af danske aktier, optaget til handel på reguleret marked, "
        "hvor der er indeholdt dansk udbytteskat",
    66: "Gevinst/tab på aktier, optaget til handel på reguleret marked "
        "(net gain/loss on all listed shares, Danish and foreign)",
    414: "Udenlandsk indkomst: Udbytte af udenlandske aktier optaget til "
         "handel på reguleret marked, i udenlandsk depot",
    496: "Udenlandsk indkomst: Betalt udenlandsk udbytteskat "
         "(creditable, max treaty rate — 15% for US)",
}

# ISIN country prefixes for identifying Danish vs foreign securities
DANISH_ISIN_PREFIX = "DK"
