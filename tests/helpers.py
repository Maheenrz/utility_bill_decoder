from billdecoder.schema import Extraction

# IESCO_0003 (Sep 26) history, read from the bill image: (month, units, bill, payment)
IESCO_0003_HISTORY = [
    ("2025-09", 75, 816, 850), ("2025-10", 46, 506, 548), ("2025-11", 30, 385, 385),
    ("2025-12", 40, 539, 539), ("2026-01", 50, 676, 732), ("2026-02", 27, 744, 775),
    ("2026-03", 8, 914, 914), ("2026-04", 23, 1066, 1066), ("2026-05", 24, 1034, 1034),
    ("2026-06", 48, 1271, 1271), ("2026-07", 70, 1470, 1470), ("2026-08", 49, 1277, 1277),
]


def make_extraction(**over) -> Extraction:
    base = dict(
        provider="IESCO", tariff="A-1A(01)", sanctioned_load_kw=3, bill_month="2026-09",
        reading_date="2026-09-27", issue_date="2026-09-28", due_date="2026-10-12",
        previous_reading=1156.14, current_reading=1213.9, units_consumed=58,
        charges=[{"type": "energy", "amount": 2636}, {"type": "subsidy", "amount": -1393}],
        total_charges=1243, taxes=[], total_taxes=234, current_bill=1477, arrears=0,
        payable_within_due_date=1649, payable_after_due_date=1773,
        history=[{"month": m, "units": u, "bill_amount": b, "payment": p} for m, u, b, p in IESCO_0003_HISTORY],
        net_metering_evidence=None, fpa_note="FPA for July 26 included", late_payment=[],
    )
    base.update(over)
    return Extraction.model_validate(base)
