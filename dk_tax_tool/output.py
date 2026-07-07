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
            lines.append("  DANISH DIVIDENDS (Rubrik 61)")
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
            lines.append("  FOREIGN DIVIDENDS (Udenlandsk indkomst — Rubrik 414)")
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
    w = 66
    def box_line(text: str) -> str:
        return f"  │ {text:<{w-4}} │"

    lines = []
    lines.append("")
    lines.append("  ┌" + "─" * (w - 2) + "┐")
    lines.append(box_line("RUBRIK 66 — Gevinst/tab på aktier, optaget til handel"))
    lines.append(box_line("på reguleret marked (net gain/loss, ALL listed shares)"))
    lines.append(box_line(f"Enter: {_dkk(skat.rubrik_66_gains_losses)}"))
    lines.append("  ├" + "─" * (w - 2) + "┤")
    lines.append(box_line("UDENLANDSK INDKOMST section (foreign broker/depot):"))
    lines.append(box_line("Rubrik 414 — Udbytte af udenlandske aktier,"))
    lines.append(box_line("optaget til handel, i udenlandsk depot (GROSS)"))
    lines.append(box_line(f"Enter: {_dkk(skat.rubrik_414_foreign_dividends)}"))
    lines.append("  ├" + "─" * (w - 2) + "┤")
    lines.append(box_line("Rubrik 496 — Udenlandsk udbytteskat (creditable,"))
    lines.append(box_line("capped at 15% treaty rate for US shares)"))
    lines.append(box_line(f"Enter: {_dkk(skat.foreign_wht_creditable_dkk)}"))
    if skat.foreign_wht_paid_dkk > skat.foreign_wht_creditable_dkk + 0.005:
        lines.append(box_line(f"(Actually withheld: {_dkk(skat.foreign_wht_paid_dkk)} —"))
        lines.append(box_line("excess above 15% is NOT creditable in DK)"))
    if skat.rubrik_61_dk_dividends > 0:
        lines.append("  ├" + "─" * (w - 2) + "┤")
        lines.append(box_line("RUBRIK 61 — Udbytte af danske aktier (listed,"))
        lines.append(box_line("dansk udbytteskat withheld)"))
        lines.append(box_line(f"Enter: {_dkk(skat.rubrik_61_dk_dividends)}"))
    lines.append("  └" + "─" * (w - 2) + "┘")

    if skat.interest_income_dkk > 0:
        lines.append("")
        lines.append(f"  Interest income (kapitalindkomst, NOT aktieindkomst):")
        lines.append(f"  {_dkk(skat.interest_income_dkk)}")
        lines.append(f"  → Foreign interest: report under 'Udenlandsk indkomst' →")
        lines.append(f"    renteindtægter fra udlandet (kapitalindkomst).")

    lines.append("")
    lines.append(f"  Total aktieindkomst: {_dkk(skat.total_aktieindkomst)}")
    lines.append("")
    lines.append("  NOTE: Rubrik numbers follow the 2024/2025 oplysningsskema layout.")
    lines.append("  Field numbering in TastSelv can change — match on the Danish")
    lines.append("  field NAMES above when you file.")
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
    lines.append("  2. Go to 'Ret årsopgørelsen / oplysningsskemaet' (Edit tax return)")
    lines.append("  3. You need BOTH the 'Aktier' section and the")
    lines.append("     'Udenlandsk indkomst' section (Trading212 = foreign depot).")
    lines.append("")
    lines.append("  RUBRIK 66 — Gevinst/tab på aktier optaget til handel på")
    lines.append("  reguleret marked:")
    lines.append(f"    → Enter: {_dkk(skat.rubrik_66_gains_losses)}")
    lines.append("    Net gain/loss from ALL your listed share sales (US, EU, UK...),")
    lines.append("    computed with gennemsnitsmetoden (average cost) in DKK.")
    if skat.rubrik_66_gains_losses < 0:
        lines.append("    NOTE: This is a LOSS — enter it as a negative amount.")
        lines.append("    Losses on listed shares are KILDEARTSBEGRÆNSEDE: they only")
        lines.append("    offset dividends/gains from other LISTED shares, and unused")
        lines.append("    losses carry forward automatically.")
    lines.append("")
    lines.append("  UDENLANDSK INDKOMST → 'Udbytte af udenlandske aktier' (Rubrik 414):")
    lines.append(f"    → Enter: {_dkk(skat.rubrik_414_foreign_dividends)}")
    lines.append("    GROSS foreign dividends in DKK (before withholding tax),")
    lines.append("    converted at the Nationalbanken rate on each payment date.")
    lines.append("")
    if skat.foreign_wht_paid_dkk > 0:
        lines.append("  UDENLANDSK INDKOMST → 'Betalt udbytteskat i udlandet' (Rubrik 496):")
        lines.append(f"    → Enter: {_dkk(skat.foreign_wht_creditable_dkk)}")
        if skat.foreign_wht_paid_dkk > skat.foreign_wht_creditable_dkk + 0.005:
            lines.append(f"    (Trading212 actually withheld {_dkk(skat.foreign_wht_paid_dkk)};")
            lines.append("    Denmark only credits up to the treaty rate — 15% for US.")
            lines.append("    The excess must be reclaimed from the foreign tax authority.)")
        lines.append("    Skat gives credit (lempelse) for this against Danish tax")
        lines.append("    on the same dividends.")
        lines.append("")
    if skat.rubrik_61_dk_dividends > 0:
        lines.append("  RUBRIK 61 — Udbytte af danske aktier:")
        lines.append(f"    → Enter: {_dkk(skat.rubrik_61_dk_dividends)}")
        lines.append("    Usually pre-filled for Danish shares — verify the number.")
        lines.append("")
    if skat.interest_income_dkk > 0:
        lines.append("  INTEREST (separate from aktieindkomst!):")
        lines.append(f"    Trading212 interest earned: {_dkk(skat.interest_income_dkk)}")
        lines.append("    → This is KAPITALINDKOMST. Foreign interest goes under")
        lines.append("      'Udenlandsk indkomst' → renteindtægter fra udlandet.")
        lines.append("")
    lines.append("  IMPORTANT — FOREIGN BROKER OBLIGATIONS:")
    lines.append("    Trading212 does not auto-report to Skattestyrelsen. You must")
    lines.append("    declare the account yourself, and loss deduction on listed")
    lines.append("    shares requires that Skat is informed of the share purchases")
    lines.append("    (aktieavancebeskatningslovens § 14) — file the trade details")
    lines.append("    with your return (use the exported CSVs from this tool).")
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
                "61" if d.is_danish else "414",
            ])


def generate_summary_csv(result: TaxResult, filepath: str) -> None:
    """Export skat.dk summary to CSV."""
    import csv
    skat = result.skat_boxes
    est = result.tax_estimate
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Rubrik", "Amount (DKK)"])
        writer.writerow(["Gevinst/tab paa aktier, optaget til handel paa reguleret marked", "66", f"{skat.rubrik_66_gains_losses:.2f}"])
        writer.writerow(["Udbytte af udenlandske aktier, udenlandsk depot (GROSS)", "414", f"{skat.rubrik_414_foreign_dividends:.2f}"])
        writer.writerow(["Udenlandsk udbytteskat, creditable (max 15% treaty)", "496", f"{skat.foreign_wht_creditable_dkk:.2f}"])
        writer.writerow(["Udenlandsk udbytteskat, actually withheld", "-", f"{skat.foreign_wht_paid_dkk:.2f}"])
        writer.writerow(["Udbytte af danske aktier", "61", f"{skat.rubrik_61_dk_dividends:.2f}"])
        writer.writerow(["Interest, foreign (kapitalindkomst)", "-", f"{skat.interest_income_dkk:.2f}"])
        writer.writerow(["", "", ""])
        writer.writerow(["Total aktieindkomst", "-", f"{est.total_aktieindkomst:.2f}"])
        writer.writerow(["Estimated tax (gross)", "-", f"{est.total_tax:.2f}"])
        writer.writerow(["Foreign tax credit", "-", f"{est.foreign_tax_credit:.2f}"])
        writer.writerow(["Estimated net tax", "-", f"{est.net_tax:.2f}"])
