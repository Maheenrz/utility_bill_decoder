"""All Level 2 arithmetic lives here, in plain Python.

The LLM never adds, averages or compares numbers. It receives the dict returned by
build_facts() and only turns it into English. Every definition (what counts as 'the
last 12 months', 'summer', 'last month') is fixed here, so answers are consistent
across bills and the wording of the answer can state the interpretation used.
"""
from statistics import mean
from typing import Optional

from .schema import Extraction, HistoryRow

SUMMER = {6, 7, 8}
WINTER = {12, 1, 2}


def _ym(month: str) -> tuple[int, int]:
    y, m = month.split("-")
    return int(y), int(m)


def add_months(month: str, n: int) -> str:
    y, m = _ym(month)
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None else round(x, nd)


def _clean_history(rows: list[HistoryRow]) -> list[HistoryRow]:
    by_month: dict[str, HistoryRow] = {}
    for r in rows:
        try:
            _ym(r.month)
        except ValueError:
            continue
        old = by_month.get(r.month)
        if old is None:
            by_month[r.month] = r
        else:   # merge: the chart gives units, the billing table gives amount/payment
            by_month[r.month] = HistoryRow(
                month=r.month,
                units=r.units if r.units is not None else old.units,
                bill_amount=r.bill_amount if r.bill_amount is not None else old.bill_amount,
                payment=r.payment if r.payment is not None else old.payment,
            )
    return [by_month[k] for k in sorted(by_month)]


def build_facts(b: Extraction) -> dict:
    cur = b.bill_month
    cur_units = b.units_consumed
    hist_all = _clean_history(b.history)
    # 'history' = previous months only. Some layouts (KE) draw the current month as the last bar.
    hist = [r for r in hist_all if r.month != cur][-12:]
    with_units = [r for r in hist if r.units is not None]

    f: dict = {
        "bill_month": cur,
        "current_month_units": cur_units,
        "history_months_with_units": len(with_units),
        "history_note": "history = up to 12 months BEFORE the current bill month; the current month is excluded",
        "units_by_month": {r.month: r.units for r in with_units},
    }

    # --- Q: peak month
    if with_units:
        peak = max(with_units, key=lambda r: r.units)
        f["peak_month"] = peak.month
        f["peak_units"] = peak.units
        f["current_exceeds_peak"] = bool(cur_units is not None and cur_units > peak.units)

    # --- Q: average and comparison
    if with_units:
        avg = mean(r.units for r in with_units)
        f["avg_monthly_units"] = _r(avg)
        if cur_units is not None:
            f["current_vs_avg_diff"] = _r(cur_units - avg)
            f["current_vs_avg_pct"] = _r((cur_units - avg) / avg * 100, 1) if avg else None

    # --- Q: same month last year
    if cur:
        prev_year = add_months(cur, -12)
        row = next((r for r in hist_all if r.month == prev_year and r.units is not None), None)
        f["same_month_last_year"] = prev_year
        f["same_month_last_year_units"] = row.units if row else None
        if row and cur_units is not None:
            f["vs_same_month_last_year_diff"] = _r(cur_units - row.units)

    # --- Q: summer vs winter
    s = [r for r in with_units if int(r.month[5:7]) in SUMMER]
    w = [r for r in with_units if int(r.month[5:7]) in WINTER]
    f["summer_months_found"] = [r.month for r in s]
    f["winter_months_found"] = [r.month for r in w]
    if s and w:
        f["summer_total_units"] = _r(sum(r.units for r in s))
        f["winter_total_units"] = _r(sum(r.units for r in w))
        f["summer_avg_units"] = _r(mean(r.units for r in s))
        f["winter_avg_units"] = _r(mean(r.units for r in w))
        f["summer_minus_winter_total"] = _r(sum(r.units for r in s) - sum(r.units for r in w))
        f["summer_minus_winter_per_month"] = _r(mean(r.units for r in s) - mean(r.units for r in w))

    # --- Q: last 3 months trend
    last3 = with_units[-3:]
    if len(last3) >= 2:
        seq = [(r.month, r.units) for r in last3]
        steps = [("up" if b2[1] > a[1] else "down" if b2[1] < a[1] else "flat")
                 for a, b2 in zip(seq, seq[1:])]
        f["last3_units"] = seq
        f["last3_steps"] = steps
        f["last3_overall"] = ("up" if last3[-1].units > last3[0].units
                              else "down" if last3[-1].units < last3[0].units else "flat")
        if cur_units is not None:
            f["last3_then_current_note"] = (f"current month {cur} is {cur_units} units, "
                                           f"{'above' if cur_units > last3[-1].units else 'below' if cur_units < last3[-1].units else 'equal to'} "
                                           f"the latest history month {last3[-1].month} ({last3[-1].units})")

    # --- Q: payments
    paid, partial, unpaid, unknown = [], [], [], []
    for r in hist:
        if r.payment is None:
            unknown.append(r.month)
        elif r.payment == 0:
            unpaid.append(r.month)
        elif r.bill_amount is not None and r.payment < r.bill_amount - 1:
            partial.append(r.month)
        else:
            paid.append(r.month)
    f["payments"] = {"paid_in_full_or_more": paid, "paid_less_than_billed": partial,
                     "shown_as_zero": unpaid, "payment_not_shown": unknown}
    f["payment_note"] = ("a payment can be slightly above the bill amount (late surcharge); "
                         "0 means no payment is recorded for that month")

    # --- Q: even monthly set-aside
    bills = [r.bill_amount for r in hist if r.bill_amount is not None]
    f["billed_months_available"] = len(bills)
    if bills:
        f["billed_total"] = _r(sum(bills))
        f["avg_monthly_bill"] = _r(mean(bills))
        f["set_aside_per_month"] = _r(mean(bills))
        f["set_aside_is_full_year"] = len(bills) >= 12

    # --- Q: next month units estimate
    if cur and with_units:
        refs: dict[str, float] = {"12_month_avg": mean(r.units for r in with_units)}
        l3 = [r.units for r in with_units[-3:]]
        refs["last_3_month_avg"] = mean(l3)
        nxt = add_months(cur, 1)
        ly = next((r for r in hist_all if r.month == add_months(nxt, -12) and r.units is not None), None)
        if ly:
            refs[f"same_month_last_year ({ly.month})"] = ly.units
        f["next_month"] = nxt
        f["next_month_reference_values"] = {k: _r(v) for k, v in refs.items()}
        f["next_month_estimate_units"] = _r(mean(refs.values()), 0)
        f["next_month_method"] = "average of the reference values listed"

    # --- Q: bill if same units as last month
    if cur and b.current_bill is not None and cur_units:
        last_month = add_months(cur, -1)
        lm = next((r for r in hist if r.month == last_month and r.units is not None), None)
        if lm:
            fixed = sum(c.amount for c in b.charges if c.type in ("fixed", "meter_rent"))
            var_rate = (b.current_bill - fixed) / cur_units
            f["last_month"] = last_month
            f["last_month_units"] = lm.units
            f["current_bill_total"] = b.current_bill
            f["fixed_charges_in_current_bill"] = _r(fixed)
            f["bill_estimate_fixed_adjusted"] = _r(fixed + var_rate * lm.units, 0)
            f["bill_estimate_simple_avg_rate"] = _r(b.current_bill / cur_units * lm.units, 0)
            f["bill_estimate_note"] = ("rough: assumes the same average cost per unit as the current bill; "
                                       "real tariffs use slabs so cost per unit changes with usage")

    # --- plain facts straight from the bill
    f["tax_share_pct"] = (_r(b.total_taxes / b.current_bill * 100, 1)
                          if b.total_taxes is not None and b.current_bill else None)
    f["fpa_charges"] = [c.amount for c in b.charges if c.type == "fpa"]
    f["fpa_note"] = b.fpa_note
    f["net_metering_evidence"] = b.net_metering_evidence
    f["late_payment"] = [lp.model_dump() for lp in b.late_payment]
    f["payable_within_due_date"] = b.payable_within_due_date
    f["payable_after_due_date"] = b.payable_after_due_date
    f["due_date"] = b.due_date
    return f
