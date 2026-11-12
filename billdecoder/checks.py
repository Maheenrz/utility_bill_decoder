"""Plain-Python verification of an extraction. No LLM involved.

Two things live here:
  normalize(): deterministic fixes for rules the task states explicitly.
  check():     reconciliation tests. They FLAG problems; they never silently change
               printed values (the task says: extract as printed, do not correct).
"""
import re
from datetime import date

from .schema import Extraction

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TOL = 1.5     # rupee tolerance for printed-rounding differences


def normalize(ext: Extraction) -> Extraction:
    ext = ext.model_copy(deep=True)

    # Rule: lines printed as 0 are skipped (the model sometimes copies a blank/zero row).
    ext.charges = [c for c in ext.charges if c.amount != 0]
    ext.taxes = [t for t in ext.taxes if t.amount != 0]

    # Rule: subsidies / credits are recorded as negative amounts.
    for c in ext.charges:
        if c.type == "subsidy" and c.amount > 0:
            c.amount = -c.amount

    # Rule: if only ONE combined tax figure is printed, taxes = [] and the amount goes in total_taxes.
    # (This is the 'Taxes 16.23 %  1314' line on the IESCO/LESCO layout.)
    if ext.provider in ("IESCO", "LESCO") and len(ext.taxes) == 1 and ext.taxes[0].type == "other_tax":
        if ext.total_taxes is None:
            ext.total_taxes = ext.taxes[0].amount
        ext.taxes = []

    for c in ext.charges:
        c.amount = round(c.amount, 2)
    for t in ext.taxes:
        t.amount = round(t.amount, 2)
    return ext


def _valid_date(s: str) -> bool:
    try:
        return date.fromisoformat(s).isoformat() == s
    except ValueError:
        return False


def check(ext: Extraction) -> list[str]:
    w: list[str] = []

    if ext.bill_month and not _MONTH.match(ext.bill_month):
        w.append(f"bill_month '{ext.bill_month}' is not YYYY-MM")
    for f in ("reading_date", "issue_date", "due_date"):
        v = getattr(ext, f)
        if v and not _valid_date(v):
            w.append(f"{f} '{v}' is not a valid YYYY-MM-DD date")
    if ext.issue_date and ext.due_date and _valid_date(ext.issue_date) and _valid_date(ext.due_date):
        if ext.due_date < ext.issue_date:
            w.append("due_date is before issue_date")

    if None not in (ext.previous_reading, ext.current_reading, ext.units_consumed):
        diff = ext.current_reading - ext.previous_reading
        if abs(diff - ext.units_consumed) > TOL:
            w.append(f"readings difference {diff:.2f} does not match units_consumed {ext.units_consumed}")

    if ext.charges and ext.total_charges is not None:
        s = sum(c.amount for c in ext.charges)
        s_no_fpa = s - sum(c.amount for c in ext.charges if c.type == "fpa")
        # IESCO/LESCO new layout prints Total FPA outside the 'Net Electricity Charges' subtotal
        if min(abs(s - ext.total_charges), abs(s_no_fpa - ext.total_charges)) > TOL:
            w.append(f"charges add up to {s:.2f} but printed total_charges is {ext.total_charges}")

    if ext.taxes and ext.total_taxes is not None:
        s = sum(t.amount for t in ext.taxes)
        if abs(s - ext.total_taxes) > TOL:
            w.append(f"taxes add up to {s:.2f} but printed total_taxes is {ext.total_taxes}")

    if None not in (ext.total_charges, ext.total_taxes, ext.current_bill):
        subsidy = sum(c.amount for c in ext.charges if c.type == "subsidy")
        pay = ext.payable_within_due_date
        ok = (abs(ext.total_charges + ext.total_taxes - ext.current_bill) <= TOL
              or abs(ext.total_charges + subsidy + ext.total_taxes - ext.current_bill) <= TOL
              # old LESCO layout: printed Current Bill can differ while charges + taxes = amount payable
              or (pay is not None and abs(ext.total_charges + ext.total_taxes + (ext.arrears or 0) - pay) <= TOL))
        if not ok:
            w.append(f"total_charges {ext.total_charges} + total_taxes {ext.total_taxes} "
                     f"does not equal current_bill {ext.current_bill}")

    if None not in (ext.payable_within_due_date, ext.payable_after_due_date):
        if ext.payable_after_due_date < ext.payable_within_due_date:
            w.append("payable_after_due_date is lower than payable_within_due_date")

    seen = set()
    for r in ext.history:
        if not _MONTH.match(r.month):
            w.append(f"history month '{r.month}' is not YYYY-MM")
        if r.month in seen:
            w.append(f"history month {r.month} appears twice")
        seen.add(r.month)
    return w
