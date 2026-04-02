"""
Table output and report generation for Danish tax calculations.

Produces formatted console tables and CSV exports.
"""

from .calculator import TaxResult, SkatBoxes, TaxEstimate
from .config import (
    TAX_YEAR, AKTIEINDKOMST_LOW_RATE, AKTIEINDKOMST_HIGH_RATE,
    PROGRESSIONSGRAENSE,
)


def _fmt(val: float, decimals: int = 2) -> str:
    """Format a number as Danish-style with thousand separators."""
    formatted = f"{val:,.{decimals}f}"
    return formatted


def _dkk(val: float) -> str:
    return f"{_fmt(val)} DKK"


def _sep(char: str = "=", width: int = 80) -> str:
    return char * width


def _header(title: str, width: int = 80) -> str:
    lines = [
        "",
        _sep("=", width),
        f"  {title}",
        _sep("=", width),
    ]
    return "\n".join(lines)


def print_full_report(result: TaxResult) -> str:
    """Generate and return the complete tax report as a string."""
    lines: list[str] = []

    lines.append(_sep("*"))
    lines.append("  TAXING212-DK — Danish Tax Report for Trading212")
    lines.append(f"  Tax Year: {result.tax_year} (01/01/{result.tax_year} - 31/12/{result.tax_year})")
    lines.append(_sep("*"))

    # --- Errors & Warnings ---
    if result.errors:
        lines.append(_header("ERRORS"))
        for i, err in enumerate(result.errors, 1):
            lines.append(f"  [{i}] {err}")

    if result.warnings:
        lines.append(_header("WARNINGS"))
        for i, w in enumerate(result.warnings, 1):
            lines.append(f"  [{i}] {w}")

    # --- Disposals (Round Trips) ---
    lines.append(_header(f"DISPOSALS (SALES) IN {result.tax_year}"))
    if result.disposals:
        lines.append("")
        lines.append(
            f"  {'Date':<12} {'Ticker':<8} {'Name':<25} {'Shares':>10} "
            f"{'Proceeds DKK':>14} {'Cost DKK':>14} {'Gain/Loss DKK':>14}"
        )
        lines.append(f"  {'-'*10:<12} {'-'*6:<8} {'-'*23:<25} {'-'*10:>10} "
                      f"{'-'*12:>14} {'-'*12:>14} {'-'*13:>14}")

        for d in sorted(result.disposals, key=lambda x: x.timestamp):
            gl_prefix = "+" if d.gain_loss_dkk >= 0 else ""
            name_short = d.name[:23] if len(d.name) > 23 else d.name
            lines.append(
                f"  {d.date_str:<12} {d.ticker:<8} {name_short:<25} "
                f"{d.shares:>10.4f} {d.proceeds_dkk:>14,.2f} "
                f"{d.cost_basis_dkk:>14,.2f} {gl_prefix}{d.gain_loss_dkk:>13,.2f}"
            )

        lines.append(f"  {'-'*97}")
        lines.append(
            f"  {'TOTAL':<47} {'':<10} "
            f"{result.total_proceeds_dkk:>14,.2f} "
            f"{result.total_cost_basis_dkk:>14,.2f} "
            f"{'+'if result.net_gain_loss_dkk>=0 else ''}{result.net_gain_loss_dkk:>13,.2f}"
        )
    else:
        lines.append("  No disposals in this tax year.")

    # --- Disposals Summary ---
    lines.append(_header(f"CAPITAL GAINS SUMMARY — {result.tax_year}"))
    lines.append(f"  Number of disposals:      {result.total_disposals}")
    lines.append(f"  Total proceeds:           {_dkk(result.total_proceeds_dkk)}")
    lines.append(f"  Total acquisition cost:   {_dkk(result.total_cost_basis_dkk)}")
    lines.append(f"  Total realised gains:     {_dkk(result.total_gain_dkk)}")
    lines.append(f"  Total realised losses:    {_dkk(result.total_loss_dkk)}")
    lines.append(f"  Net gain/loss:            {_dkk(result.net_gain_loss_dkk)}")

    # --- Dividends ---
    lines.append(_header(f"DIVIDENDS IN {result.tax_year}"))
    if result.dividends_summary:
        # Danish dividends
        dk_divs = [d for d in result.dividends_summary if d.is_danish]
        foreign_divs = [d for d in result.dividends_summary if not d.is_danish]

        if dk_divs:
            lines.append("")
            lines.append("  DANISH DIVIDENDS (Rubrik 66)")
            lines.append(
                f"  {'Date':<12} {'Ticker':<8} {'Name':<25} "
                f"{'Gross DKK':>12} {'WHT DKK':>10} {'Net DKK':>12}"
            )
            lines.append(f"  {'-'*10:<12} {'-'*6:<8} {'-'*23:<25} "
                          f"{'-'*10:>12} {'-'*8:>10} {'-'*10:>12}")
            for d in dk_divs:
                name_short = d.name[:23] if len(d.name) > 23 else d.name
                lines.append(
                    f"  {d.date_str:<12} {d.ticker:<8} {name_short:<25} "
                    f"{d.gross_amount_dkk:>12,.2f} {d.withholding_tax_dkk:>10,.2f} "
                    f"{d.net_amount_dkk:>12,.2f}"
                )
            dk_total = sum(d.gross_amount_dkk for d in dk_divs)
            lines.append(f"  {'':>45} TOTAL: {dk_total:>12,.2f} DKK")

        if foreign_divs:
            lines.append("")
            lines.append("  FOREIGN DIVIDENDS (Rubrik 67)")
            lines.append(
                f"  {'Date':<12} {'Ticker':<8} {'Name':<25} "
                f"{'Gross DKK':>12} {'WHT DKK':>10} {'Net DKK':>12} "
                f"{'Orig Amt':>10} {'Cur':>4}"
            )
            lines.append(f"  {'-'*10:<12} {'-'*6:<8} {'-'*23:<25} "
                          f"{'-'*10:>12} {'-'*8:>10} {'-'*10:>12} "
                          f"{'-'*8:>10} {'-'*3:>4}")
            for d in foreign_divs:
                name_short = d.name[:23] if len(d.name) > 23 else d.name
                lines.append(
                    f"  {d.date_str:<12} {d.ticker:<8} {name_short:<25} "
                    f"{d.gross_amount_dkk:>12,.2f} {d.withholding_tax_dkk:>10,.2f} "
                    f"{d.net_amount_dkk:>12,.2f} "
                    f"{d.original_amount:>10,.2f} {d.original_currency:>4}"
                )
            foreign_total = sum(d.gross_amount_dkk for d in foreign_divs)
            wht_total = sum(d.withholding_tax_dkk for d in foreign_divs)
            lines.append(f"  {'':>45} TOTAL: {foreign_total:>12,.2f} DKK  (WHT: {wht_total:>10,.2f} DKK)")
    else:
        lines.append("  No dividends in this tax year.")

    # --- Interest ---
    if result.interest_summary:
        lines.append(_header(f"INTEREST INCOME IN {result.tax_year}"))
        lines.append(
            f"  {'Date':<12} {'Amount DKK':>14} {'Orig Amt':>12} {'Cur':>4}"
        )
        lines.append(f"  {'-'*10:<12} {'-'*12:>14} {'-'*10:>12} {'-'*3:>4}")
        for i in result.interest_summary:
            lines.append(
                f"  {i.date_str:<12} {i.amount_dkk:>14,.2f} "
                f"{i.original_amount:>12,.2f} {i.original_currency:>4}"
            )
        total_interest = sum(i.amount_dkk for i in result.interest_summary)
        lines.append(f"  {'':>12} TOTAL: {total_interest:>12,.2f} DKK")
        lines.append("")
        lines.append("  NOTE: Interest from Trading212 is kapitalindkomst (capital income),")
        lines.append("        NOT aktieindkomst. Report separately on your tax return.")

    # --- Holdings ---
    lines.append(_header("CURRENT HOLDINGS (Open Positions)"))
    open_holdings = {
        k: v for k, v in result.holdings.items() if v.current_shares > 0.0001
    }
    if open_holdings:
        lines.append(
            f"  {'Ticker':<8} {'Name':<25} {'Shares':>10} "
            f"{'Avg Cost DKK':>14} {'Total Cost DKK':>15}"
        )
        lines.append(f"  {'-'*6:<8} {'-'*23:<25} {'-'*10:>10} "
                      f"{'-'*12:>14} {'-'*13:>15}")
        for t, h in sorted(open_holdings.items()):
            name_short = h.name[:23] if len(h.name) > 23 else h.name
            lines.append(
                f"  {h.ticker:<8} {name_short:<25} {h.current_shares:>10.4f} "
                f"{h.average_cost_dkk:>14,.2f} {h.total_cost_dkk:>15,.2f}"
            )
    else:
        lines.append("  No open positions.")

    # --- SKAT.DK BOX MAPPING ---
    lines.append(_header("SKAT.DK — RUBRIK MAPPING (Where to enter numbers)"))
    lines.append(_print_skat_boxes(result.skat_boxes))

    # --- TAX ESTIMATE ---
    lines.append(_header("TAX ESTIMATE (Aktieindkomst)"))
    lines.append(_print_tax_estimate(result.tax_estimate, result.skat_boxes))

    # --- DETAILED SKAT GUIDE ---
    lines.append(_header("SKAT.DK FILING GUIDE"))
    lines.append(_print_skat_guide(result.skat_boxes))

    lines.append("")
    lines.append(_sep("*"))
    lines.append("  DISCLAIMER: This is an estimate only. Verify all numbers")
    lines.append("  with your tax advisor before filing your selvangivelse.")
    lines.append("  This tool does NOT handle: ETFs with lagerbeskatning,")
    lines.append("  pension accounts (ASK/ratepension), or crypto assets.")
    lines.append(_sep("*"))
    lines.append("")

    report = "\n".join(lines)
    return report


def _print_skat_boxes(skat: SkatBoxes) -> str:
    lines = []
    lines.append("")
    lines.append(f"  ┌─────────────────────────────────────────────────────────────────┐")
    lines.append(f"  │  Rubrik 66 — Udbytte af danske aktier mv.                      │")
    lines.append(f"  │  (Dividends from Danish shares)                                 │")
    lines.append(f"  │  Enter: {_dkk(skat.rubrik_66_dk_dividends):>52} │")
    lines.append(f"  ├─────────────────────────────────────────────────────────────────┤")
    lines.append(f"  │  Rubrik 67 — Udbytte af udenlandske aktier mv.                 │")
    lines.append(f"  │  (Dividends from foreign shares)                                │")
    lines.append(f"  │  Enter: {_dkk(skat.rubrik_67_foreign_dividends):>52} │")
    lines.append(f"  ├─────────────────────────────────────────────────────────────────┤")
    lines.append(f"  │  Rubrik 68 — Gevinst/tab ved salg af aktier                    │")
    lines.append(f"  │  (Net gain/loss from sale of shares)                            │")
    lines.append(f"  │  Enter: {_dkk(skat.rubrik_68_gains_losses):>52} │")
    lines.append(f"  ├─────────────────────────────────────────────────────────────────┤")
    lines.append(f"  │  Foreign withholding tax paid (for lempelse/credit claim):      │")
    lines.append(f"  │  {_dkk(skat.foreign_tax_paid_dkk):>62} │")
    lines.append(f"  └─────────────────────────────────────────────────────────────────┘")

    if skat.interest_income_dkk > 0:
        lines.append("")
        lines.append(f"  Interest income (kapitalindkomst, NOT aktieindkomst):")
        lines.append(f"  {_dkk(skat.interest_income_dkk)}")
        lines.append(f"  → Report in Rubrik 30 (Renteindtægter af indestående i bank mv.)")

    lines.append("")
    lines.append(f"  Total aktieindkomst: {_dkk(skat.total_aktieindkomst)}")
    return "\n".join(lines)


def _print_tax_estimate(est: TaxEstimate, skat: SkatBoxes) -> str:
    lines = []
    lines.append("")
    lines.append(f"  Total aktieindkomst:              {_dkk(est.total_aktieindkomst)}")
    lines.append(f"  Progressionsgrænse ({TAX_YEAR}):     {_dkk(est.progressionsgraense)}")
    lines.append("")

    if est.total_aktieindkomst <= 0:
        lines.append(f"  Net aktieindkomst is zero or negative.")
        if est.total_aktieindkomst < 0:
            lines.append(f"  Loss of {_dkk(abs(est.total_aktieindkomst))} carries forward")
            lines.append(f"  to offset future aktieindkomst.")
        lines.append(f"  No aktieindkomst tax due.")
    else:
        lines.append(f"  Tax at {AKTIEINDKOMST_LOW_RATE*100:.0f}% (first {_dkk(est.progressionsgraense)}):")
        lines.append(f"    {_dkk(est.tax_at_low_rate)}")
        lines.append(f"  Tax at {AKTIEINDKOMST_HIGH_RATE*100:.0f}% (above {_dkk(est.progressionsgraense)}):")
        lines.append(f"    {_dkk(est.tax_at_high_rate)}")
        lines.append(f"  Gross tax:                        {_dkk(est.total_tax)}")
        if est.foreign_tax_credit > 0:
            lines.append(f"  Foreign tax credit (lempelse):    -{_dkk(est.foreign_tax_credit)}")
        lines.append(f"  Estimated net tax:                {_dkk(est.net_tax)}")

    return "\n".join(lines)


def _print_skat_guide(skat: SkatBoxes) -> str:
    lines = []
    lines.append("")
    lines.append("  HOW TO FILE ON SKAT.DK:")
    lines.append("  " + "-" * 60)
    lines.append("")
    lines.append("  1. Log in to skat.dk with MitID")
    lines.append("  2. Go to 'Ret årsopgørelsen' (Edit tax return)")
    lines.append("  3. Find section: 'Aktieindkomst'")
    lines.append("")
    lines.append("  RUBRIK 66 — Udbytte af danske aktier:")
    lines.append(f"    → Enter: {_dkk(skat.rubrik_66_dk_dividends)}")
    lines.append("    This is the GROSS dividend amount before any tax.")
    lines.append("    Danish companies auto-report, so check pre-filled.")
    lines.append("")
    lines.append("  RUBRIK 67 — Udbytte af udenlandske aktier:")
    lines.append(f"    → Enter: {_dkk(skat.rubrik_67_foreign_dividends)}")
    lines.append("    This is the GROSS dividend in DKK (before WHT).")
    lines.append("    Convert each dividend to DKK at the exchange rate")
    lines.append("    on the payment date (Nationalbanken rate).")
    lines.append("")
    lines.append("  RUBRIK 68 — Gevinst/tab ved salg af aktier:")
    lines.append(f"    → Enter: {_dkk(skat.rubrik_68_gains_losses)}")
    lines.append("    This is the NET gain or loss from all share sales.")
    lines.append("    Use gennemsnitsmetoden (average cost) for cost basis.")
    if skat.rubrik_68_gains_losses < 0:
        lines.append("    NOTE: This is a LOSS. Enter as negative.")
        lines.append("    Losses on listed shares offset gains on listed shares.")
        lines.append("    Unused losses carry forward automatically.")
    lines.append("")
    if skat.foreign_tax_paid_dkk > 0:
        lines.append("  FOREIGN TAX CREDIT (Lempelse):")
        lines.append(f"    Total foreign WHT paid: {_dkk(skat.foreign_tax_paid_dkk)}")
        lines.append("    → On skat.dk, look for 'Lempelse for dobbeltbeskatning'")
        lines.append("      or 'Nedslag for udenlandsk skat' under aktieindkomst.")
        lines.append("    → The credit is limited to the Danish tax on the")
        lines.append("      foreign income (per country, per treaty).")
        lines.append("    → For US dividends with W-8BEN: 15% WHT is generally")
        lines.append("      creditable against Danish tax.")
        lines.append("")
    if skat.interest_income_dkk > 0:
        lines.append("  INTEREST (Separate from aktieindkomst!):")
        lines.append(f"    Trading212 interest earned: {_dkk(skat.interest_income_dkk)}")
        lines.append("    → This is KAPITALINDKOMST, not aktieindkomst.")
        lines.append("    → Enter in Rubrik 30 (Renteindtægter) or similar.")
        lines.append("")

    return "\n".join(lines)


def generate_disposals_csv(result: TaxResult, filepath: str) -> None:
    """Export disposals to CSV."""
    import csv
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Date", "Ticker", "Name", "ISIN", "Shares",
            "Proceeds (DKK)", "Cost Basis (DKK)", "Gain/Loss (DKK)",
            "Danish/Foreign"
        ])
        for d in sorted(result.disposals, key=lambda x: x.timestamp):
            writer.writerow([
                d.date_str, d.ticker, d.name, d.isin,
                f"{d.shares:.4f}",
                f"{d.proceeds_dkk:.2f}",
                f"{d.cost_basis_dkk:.2f}",
                f"{d.gain_loss_dkk:.2f}",
                "Danish" if d.is_danish else "Foreign",
            ])


def generate_dividends_csv(result: TaxResult, filepath: str) -> None:
    """Export dividends to CSV."""
    import csv
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Date", "Ticker", "Name", "ISIN",
            "Gross Amount (DKK)", "Withholding Tax (DKK)", "Net Amount (DKK)",
            "Original Amount", "Original Currency",
            "Danish/Foreign", "Skat Rubrik"
        ])
        for d in sorted(result.dividends_summary, key=lambda x: x.timestamp):
            writer.writerow([
                d.date_str, d.ticker, d.name, d.isin,
                f"{d.gross_amount_dkk:.2f}",
                f"{d.withholding_tax_dkk:.2f}",
                f"{d.net_amount_dkk:.2f}",
                f"{d.original_amount:.2f}",
                d.original_currency,
                "Danish" if d.is_danish else "Foreign",
                "66" if d.is_danish else "67",
            ])


def generate_summary_csv(result: TaxResult, filepath: str) -> None:
    """Export skat.dk summary to CSV."""
    import csv
    skat = result.skat_boxes
    est = result.tax_estimate
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Rubrik", "Amount (DKK)"])
        writer.writerow(["Udbytte af danske aktier", "66", f"{skat.rubrik_66_dk_dividends:.2f}"])
        writer.writerow(["Udbytte af udenlandske aktier", "67", f"{skat.rubrik_67_foreign_dividends:.2f}"])
        writer.writerow(["Gevinst/tab ved salg af aktier", "68", f"{skat.rubrik_68_gains_losses:.2f}"])
        writer.writerow(["Foreign WHT paid (lempelse)", "-", f"{skat.foreign_tax_paid_dkk:.2f}"])
        writer.writerow(["Interest (kapitalindkomst)", "30", f"{skat.interest_income_dkk:.2f}"])
        writer.writerow(["", "", ""])
        writer.writerow(["Total aktieindkomst", "-", f"{est.total_aktieindkomst:.2f}"])
        writer.writerow(["Estimated tax (gross)", "-", f"{est.total_tax:.2f}"])
        writer.writerow(["Foreign tax credit", "-", f"{est.foreign_tax_credit:.2f}"])
        writer.writerow(["Estimated net tax", "-", f"{est.net_tax:.2f}"])
