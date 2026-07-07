"""
Danish tax calculator for Trading212 transactions.

Implements Danish tax rules for aktieindkomst:
- Gennemsnitsmetoden (average cost method) for cost basis
- Realisationsbeskatning (realization-based taxation) for listed shares
- Calendar year tax period (Jan 1 - Dec 31)
- Aktieindkomst rates: 27% / 42% with progressionsgrænse

Key differences from UK (the original tool):
- No "same day" matching rule (Danish law uses simple average cost pool)
- No "bed and breakfast" 30-day rule
- Tax year = calendar year, not April-April
- All amounts must be in DKK
- Dividends + capital gains are combined as aktieindkomst
"""

from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from . import config
from .config import (
    TAX_YEAR, TAX_YEAR_START, TAX_YEAR_END,
    AKTIEINDKOMST_LOW_RATE, AKTIEINDKOMST_HIGH_RATE,
    PROGRESSIONSGRAENSE, TREATY_WHT_CREDIT_CAP,
    DANISH_ISIN_PREFIX,
)
from .parser import Trade, Dividend, Interest, ParsedData
from .fx_rates import FXRateStore


@dataclass
class CostPool:
    """Average cost pool for a single security (gennemsnitsmetoden).

    Danish tax law requires using the average acquisition cost of all
    shares of the same type when calculating gains on disposal.
    """
    ticker: str
    name: str
    isin: str
    total_shares: float = 0.0
    total_cost_dkk: float = 0.0   # Total acquisition cost in DKK

    @property
    def average_cost_per_share_dkk(self) -> float:
        if self.total_shares <= 0.0001:
            return 0.0
        return self.total_cost_dkk / self.total_shares

    def buy(self, shares: float, cost_dkk: float) -> None:
        """Add shares to the pool."""
        self.total_shares += shares
        self.total_cost_dkk += cost_dkk

    def sell(self, shares: float) -> float:
        """Remove shares from the pool. Returns the cost basis in DKK."""
        if shares > self.total_shares + 0.001:  # small tolerance for fractional
            raise ValueError(
                f"Selling {shares:.4f} shares of {self.ticker} but pool only has "
                f"{self.total_shares:.4f}. Check for missing trade history."
            )
        avg_cost = self.average_cost_per_share_dkk
        cost_basis = shares * avg_cost
        self.total_shares -= shares
        self.total_cost_dkk -= cost_basis
        # Clean up floating point dust
        if abs(self.total_shares) < 0.0001:
            self.total_shares = 0.0
            self.total_cost_dkk = 0.0
        return cost_basis


@dataclass
class Disposal:
    """A single disposal (sale) and its tax computation."""
    timestamp: datetime
    ticker: str
    name: str
    isin: str
    shares: float
    proceeds_dkk: float
    cost_basis_dkk: float
    gain_loss_dkk: float
    is_danish: bool

    @property
    def date_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")


@dataclass
class DividendSummary:
    """Summary of a dividend payment for tax reporting."""
    timestamp: datetime
    ticker: str
    name: str
    isin: str
    gross_amount_dkk: float
    withholding_tax_dkk: float
    net_amount_dkk: float
    is_danish: bool
    original_amount: float
    original_currency: str

    @property
    def date_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")


@dataclass
class InterestSummary:
    timestamp: datetime
    amount_dkk: float
    original_amount: float
    original_currency: str

    @property
    def date_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")


@dataclass
class HoldingSummary:
    """Summary for a single holding across all time."""
    ticker: str
    name: str
    isin: str
    current_shares: float
    average_cost_dkk: float
    total_cost_dkk: float
    total_trades: int
    # Tax year specific
    ty_disposals: int = 0
    ty_realised_gain: float = 0.0
    ty_realised_loss: float = 0.0
    ty_proceeds: float = 0.0
    ty_cost_basis: float = 0.0
    # All-time
    all_realised_gain: float = 0.0
    all_realised_loss: float = 0.0


@dataclass
class SkatBoxes:
    """Amounts to enter in skat.dk rubrikker.

    Correct boxes for a Danish resident using a foreign broker (T212):
      - Rubrik 61:  dividends from DANISH listed shares (dansk udbytteskat withheld)
      - Rubrik 66:  net gain/loss on ALL listed shares (Danish + foreign)
      - Rubrik 414: foreign dividends, listed shares in foreign depot
                    (in the "Udenlandsk indkomst" section of TastSelv)
      - Rubrik 496: foreign withholding tax paid — creditable portion is
                    capped at the treaty rate (15% for US) of the gross dividend
    """
    rubrik_61_dk_dividends: float = 0.0         # Udbytte af danske aktier
    rubrik_66_gains_losses: float = 0.0         # Gevinst/tab, noterede aktier
    rubrik_414_foreign_dividends: float = 0.0   # Udbytte, udenlandske aktier
    foreign_wht_paid_dkk: float = 0.0           # Actually withheld abroad
    foreign_wht_creditable_dkk: float = 0.0     # Capped at treaty rate (rubrik 496)
    interest_income_dkk: float = 0.0            # Interest on cash (kapitalindkomst)

    @property
    def total_aktieindkomst(self) -> float:
        return (
            self.rubrik_61_dk_dividends
            + self.rubrik_414_foreign_dividends
            + self.rubrik_66_gains_losses
        )


@dataclass
class TaxEstimate:
    """Estimated tax liability on aktieindkomst."""
    total_aktieindkomst: float
    progressionsgraense: float
    tax_at_low_rate: float
    tax_at_high_rate: float
    total_tax: float
    foreign_tax_credit: float
    net_tax: float


@dataclass
class TaxResult:
    """Complete tax calculation result."""
    tax_year: int
    disposals: list[Disposal]
    dividends_summary: list[DividendSummary]
    interest_summary: list[InterestSummary]
    holdings: dict[str, HoldingSummary]
    skat_boxes: SkatBoxes
    tax_estimate: TaxEstimate
    errors: list[str]
    warnings: list[str]
    # Aggregate stats
    total_disposals: int = 0
    total_proceeds_dkk: float = 0.0
    total_cost_basis_dkk: float = 0.0
    total_gain_dkk: float = 0.0
    total_loss_dkk: float = 0.0
    net_gain_loss_dkk: float = 0.0


def calculate(parsed: ParsedData, fx: FXRateStore) -> TaxResult:
    """Run the full Danish tax calculation.

    Steps:
    1. Convert all amounts to DKK using Nationalbanken rates
    2. Build average cost pools (gennemsnitsmetoden) chronologically
    3. Calculate gains/losses on disposals in the tax year
    4. Summarise dividends (Danish vs foreign)
    5. Map totals to skat.dk rubrikker
    6. Estimate tax liability
    """
    errors: list[str] = list(parsed.errors)
    warnings: list[str] = []

    tax_start = datetime.strptime(TAX_YEAR_START, "%Y-%m-%d")
    tax_end = datetime.strptime(TAX_YEAR_END, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )

    # --- Step 1: Convert trades to DKK ---
    account_cur = parsed.account_currency or "GBP"
    _convert_trades_to_dkk(parsed.trades, fx, account_cur, errors)

    # --- Step 2 & 3: Build cost pools and calculate disposals ---
    pools: dict[str, CostPool] = {}
    disposals: list[Disposal] = []
    holding_summaries: dict[str, HoldingSummary] = {}

    for trade in parsed.trades:
        ticker = trade.ticker
        if ticker not in pools:
            pools[ticker] = CostPool(
                ticker=ticker, name=trade.name, isin=trade.isin
            )
        if ticker not in holding_summaries:
            holding_summaries[ticker] = HoldingSummary(
                ticker=ticker, name=trade.name, isin=trade.isin,
                current_shares=0, average_cost_dkk=0, total_cost_dkk=0,
                total_trades=0,
            )

        pool = pools[ticker]
        hs = holding_summaries[ticker]
        hs.total_trades += 1

        if trade.action == "Buy":
            cost_dkk = trade.total_dkk
            if cost_dkk <= 0:
                # Fallback: use shares * price_dkk
                cost_dkk = trade.shares * trade.price_dkk
            pool.buy(trade.shares, cost_dkk)

        elif trade.action == "Sell":
            try:
                cost_basis = pool.sell(trade.shares)
            except ValueError as e:
                errors.append(str(e))
                # Skip this disposal entirely — we can't compute gain/loss
                # without a valid cost basis. Don't create a phantom gain.
                continue

            proceeds = trade.total_dkk
            if proceeds <= 0:
                proceeds = trade.shares * trade.price_dkk

            gain_loss = proceeds - cost_basis
            is_danish = trade.isin.startswith(DANISH_ISIN_PREFIX)

            disposal = Disposal(
                timestamp=trade.timestamp,
                ticker=ticker,
                name=trade.name,
                isin=trade.isin,
                shares=trade.shares,
                proceeds_dkk=proceeds,
                cost_basis_dkk=cost_basis,
                gain_loss_dkk=gain_loss,
                is_danish=is_danish,
            )

            # All-time stats
            if gain_loss > 0:
                hs.all_realised_gain += gain_loss
            else:
                hs.all_realised_loss += abs(gain_loss)

            # Tax year stats
            in_tax_year = tax_start <= trade.timestamp <= tax_end
            if in_tax_year:
                disposals.append(disposal)
                hs.ty_disposals += 1
                hs.ty_proceeds += proceeds
                hs.ty_cost_basis += cost_basis
                if gain_loss > 0:
                    hs.ty_realised_gain += gain_loss
                else:
                    hs.ty_realised_loss += abs(gain_loss)

    # Update holding summaries with final pool state
    for ticker, pool in pools.items():
        if ticker in holding_summaries:
            hs = holding_summaries[ticker]
            hs.current_shares = pool.total_shares
            hs.average_cost_dkk = pool.average_cost_per_share_dkk
            hs.total_cost_dkk = pool.total_cost_dkk

    # --- Step 4: Process dividends ---
    dividends_summary: list[DividendSummary] = []
    for div in parsed.dividends:
        in_tax_year = tax_start <= div.timestamp <= tax_end
        if not in_tax_year:
            continue

        # Convert to DKK
        try:
            if div.amount_currency and div.amount_currency != "DKK":
                div.amount_dkk = fx.convert_to_dkk(
                    div.amount, div.amount_currency, div.timestamp.date()
                )
            else:
                div.amount_dkk = div.amount
        except ValueError as e:
            errors.append(
                f"CRITICAL FX error for dividend {div.ticker} on {div.timestamp.date()}: {e} "
                f"— Dividend of {div.amount} {div.amount_currency} NOT converted. "
                f"Load rate data covering this date."
            )
            div.amount_dkk = 0.0

        # Convert withholding tax to DKK
        try:
            if div.wht_currency and div.wht_currency != "DKK" and div.withholding_tax > 0:
                div.withholding_tax_dkk = fx.convert_to_dkk(
                    div.withholding_tax, div.wht_currency, div.timestamp.date()
                )
            else:
                div.withholding_tax_dkk = div.withholding_tax
        except ValueError as e:
            errors.append(f"WHT FX error for {div.ticker}: {e}")
            div.withholding_tax_dkk = 0.0

        dividends_summary.append(DividendSummary(
            timestamp=div.timestamp,
            ticker=div.ticker,
            name=div.name,
            isin=div.isin,
            gross_amount_dkk=div.amount_dkk,
            withholding_tax_dkk=div.withholding_tax_dkk,
            net_amount_dkk=div.amount_dkk - div.withholding_tax_dkk,
            is_danish=div.is_danish,
            original_amount=div.amount,
            original_currency=div.amount_currency,
        ))

    # --- Step 4b: Process interest ---
    interest_summary: list[InterestSummary] = []
    for intr in parsed.interest:
        in_tax_year = tax_start <= intr.timestamp <= tax_end
        if not in_tax_year:
            continue
        try:
            if intr.currency and intr.currency != "DKK":
                intr.amount_dkk = fx.convert_to_dkk(
                    intr.amount, intr.currency, intr.timestamp.date()
                )
            else:
                intr.amount_dkk = intr.amount
        except ValueError as e:
            errors.append(f"Interest FX error: {e}")
            intr.amount_dkk = 0.0

        interest_summary.append(InterestSummary(
            timestamp=intr.timestamp,
            amount_dkk=intr.amount_dkk,
            original_amount=intr.amount,
            original_currency=intr.currency,
        ))

    # --- Step 5: Skat.dk box mapping ---
    skat = SkatBoxes()

    for ds in dividends_summary:
        if ds.is_danish:
            skat.rubrik_61_dk_dividends += ds.gross_amount_dkk
        else:
            skat.rubrik_414_foreign_dividends += ds.gross_amount_dkk
            skat.foreign_wht_paid_dkk += ds.withholding_tax_dkk
            # Credit (lempelse) is capped at the treaty rate per dividend
            cap = ds.gross_amount_dkk * TREATY_WHT_CREDIT_CAP
            skat.foreign_wht_creditable_dkk += min(ds.withholding_tax_dkk, cap)
            if ds.withholding_tax_dkk > cap * 1.01:
                warnings.append(
                    f"{ds.ticker} dividend on {ds.date_str}: foreign tax withheld "
                    f"({ds.withholding_tax_dkk:.2f} DKK) exceeds the 15% treaty cap "
                    f"({cap:.2f} DKK). Only the capped amount is creditable in "
                    f"Denmark; reclaim the excess from the foreign tax authority "
                    f"(and check your W-8BEN status with Trading212)."
                )

    total_gain = sum(d.gain_loss_dkk for d in disposals if d.gain_loss_dkk > 0)
    total_loss = sum(abs(d.gain_loss_dkk) for d in disposals if d.gain_loss_dkk < 0)
    net_gain_loss = total_gain - total_loss

    skat.rubrik_66_gains_losses = net_gain_loss
    skat.interest_income_dkk = sum(i.amount_dkk for i in interest_summary)

    # --- Validation warnings ---
    critical_errors = [e for e in errors if "CRITICAL" in e]
    if critical_errors:
        warnings.append(
            f"WARNING: {len(critical_errors)} critical FX conversion error(s) found. "
            f"Tax numbers are UNRELIABLE until you provide rate data covering all "
            f"trade dates. See ERRORS section above."
        )

    # Check for zero-cost buys (indicates FX failure)
    for ticker, pool in pools.items():
        if pool.total_shares > 0.0001 and pool.total_cost_dkk <= 0:
            warnings.append(
                f"WARNING: {ticker} has {pool.total_shares:.4f} shares but 0 DKK "
                f"cost basis — likely missing FX rates for purchase dates."
            )

    # --- Step 6: Tax estimate ---
    tax_estimate = _estimate_tax(skat)

    # --- Build result ---
    result = TaxResult(
        tax_year=TAX_YEAR,
        disposals=disposals,
        dividends_summary=dividends_summary,
        interest_summary=interest_summary,
        holdings=holding_summaries,
        skat_boxes=skat,
        tax_estimate=tax_estimate,
        errors=errors,
        warnings=warnings,
        total_disposals=len(disposals),
        total_proceeds_dkk=sum(d.proceeds_dkk for d in disposals),
        total_cost_basis_dkk=sum(d.cost_basis_dkk for d in disposals),
        total_gain_dkk=total_gain,
        total_loss_dkk=total_loss,
        net_gain_loss_dkk=net_gain_loss,
    )

    return result


def _convert_trades_to_dkk(
    trades: list[Trade], fx: FXRateStore, account_cur: str, errors: list[str]
) -> None:
    """Convert all trade amounts to DKK."""
    for trade in trades:
        trade_date = trade.timestamp.date()

        # Convert total (proceeds/cost) to DKK
        try:
            total_cur = trade.total_currency or account_cur
            if total_cur == "DKK":
                trade.total_dkk = trade.total
            else:
                trade.total_dkk = fx.convert_to_dkk(trade.total, total_cur, trade_date)
        except ValueError as e:
            errors.append(
                f"CRITICAL FX error for {trade.ticker} on {trade_date}: {e} "
                f"— Total of {trade.total} {total_cur} could NOT be converted to DKK. "
                f"Cost basis will be WRONG. Load rate data covering this date."
            )
            trade.total_dkk = 0.0  # Zero, not the foreign amount — forces error visibility

        # Convert price per share to DKK
        try:
            price_cur = trade.currency_price or account_cur
            if price_cur == "DKK":
                trade.price_dkk = trade.price_per_share
            else:
                trade.price_dkk = fx.convert_to_dkk(
                    trade.price_per_share, price_cur, trade_date
                )
        except ValueError as e:
            errors.append(f"FX error for {trade.ticker} price on {trade_date}: {e}")
            trade.price_dkk = 0.0


def _estimate_tax(skat: SkatBoxes) -> TaxEstimate:
    """Estimate aktieindkomst tax.

    Aktieindkomst = dividends (rubrik 66 + 67) + capital gains (rubrik 68).
    Tax rates:
      - 27% on the first PROGRESSIONSGRAENSE DKK
      - 42% on everything above

    Losses reduce aktieindkomst. If net aktieindkomst is negative,
    the loss carries forward to offset future aktieindkomst (cannot
    be used in the current year against other income types).
    """
    total = skat.total_aktieindkomst
    threshold = PROGRESSIONSGRAENSE
    if config.MARRIED_DOUBLE_THRESHOLD:
        threshold *= 2

    if total <= 0:
        return TaxEstimate(
            total_aktieindkomst=total,
            progressionsgraense=threshold,
            tax_at_low_rate=0.0,
            tax_at_high_rate=0.0,
            total_tax=0.0,
            foreign_tax_credit=0.0,
            net_tax=0.0,
        )

    taxable_low = min(total, threshold)
    taxable_high = max(0, total - threshold)

    tax_low = taxable_low * AKTIEINDKOMST_LOW_RATE
    tax_high = taxable_high * AKTIEINDKOMST_HIGH_RATE
    gross_tax = tax_low + tax_high

    # Foreign tax credit (lempelse): capped per dividend at the treaty rate
    # (done above), and can never exceed the Danish tax on the income.
    credit = min(skat.foreign_wht_creditable_dkk, gross_tax)

    return TaxEstimate(
        total_aktieindkomst=total,
        progressionsgraense=threshold,
        tax_at_low_rate=tax_low,
        tax_at_high_rate=tax_high,
        total_tax=gross_tax,
        foreign_tax_credit=credit,
        net_tax=gross_tax - credit,
    )
