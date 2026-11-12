"""Regression tests built from the mistakes the first version made on IESCO_0003."""
from billdecoder.analytics import add_months, build_facts
from tests.helpers import make_extraction


def test_add_months_wraps_year():
    assert add_months("2026-12", 1) == "2027-01"
    assert add_months("2026-01", -1) == "2025-12"
    assert add_months("2026-09", -12) == "2025-09"


def test_peak_is_by_units_not_by_bill_amount():
    f = build_facts(make_extraction())
    assert f["peak_month"] == "2025-09" and f["peak_units"] == 75      # v1 said 'March, 914 units'


def test_average_uses_units_column():
    f = build_facts(make_extraction())
    assert f["history_months_with_units"] == 12
    assert f["avg_monthly_units"] == 40.83                              # v1 said 53.67 (sum 644)
    assert f["current_vs_avg_diff"] == 17.17


def test_even_monthly_budget_from_real_sum():
    f = build_facts(make_extraction())
    assert f["billed_total"] == 10698                                   # v1 said 9625
    assert f["set_aside_per_month"] == 891.5 and f["set_aside_is_full_year"] is True


def test_same_month_last_year_found():
    f = build_facts(make_extraction())
    assert f["same_month_last_year_units"] == 75                        # v1 said 'not shown'
    assert f["vs_same_month_last_year_diff"] == -17


def test_summer_winter():
    f = build_facts(make_extraction())
    assert f["summer_total_units"] == 167 and f["winter_total_units"] == 117
    assert f["summer_minus_winter_total"] == 50
    assert f["summer_minus_winter_per_month"] == 16.67


def test_last3_trend_is_mixed():
    f = build_facts(make_extraction())
    assert f["last3_steps"] == ["up", "down"] and f["last3_overall"] == "up"


def test_all_bills_paid_here():
    f = build_facts(make_extraction())
    assert f["payments"]["shown_as_zero"] == [] and f["payments"]["paid_less_than_billed"] == []


def test_unpaid_and_missing_payments_detected():
    hist = [{"month": "2026-07", "units": 10, "bill_amount": 100, "payment": 0},
            {"month": "2026-08", "units": 12, "bill_amount": 120, "payment": None},
            {"month": "2026-06", "units": 9, "bill_amount": 90, "payment": 50}]
    f = build_facts(make_extraction(history=hist))
    assert f["payments"]["shown_as_zero"] == ["2026-07"]
    assert f["payments"]["payment_not_shown"] == ["2026-08"]
    assert f["payments"]["paid_less_than_billed"] == ["2026-06"]


def test_next_month_estimate_is_average_of_references():
    f = build_facts(make_extraction())
    assert f["next_month"] == "2026-10"
    assert f["next_month_estimate_units"] == 48                         # mean(40.83, 55.67, 46) = 47.5 -> 48 (rounded)


def test_current_month_row_in_history_is_excluded():
    hist = [{"month": "2026-08", "units": 100, "bill_amount": None, "payment": None},
            {"month": "2026-09", "units": 58, "bill_amount": None, "payment": None}]   # KE chart style
    f = build_facts(make_extraction(history=hist))
    assert f["history_months_with_units"] == 1 and f["avg_monthly_units"] == 100


def test_missing_data_does_not_crash():
    f = build_facts(make_extraction(history=[], units_consumed=None, current_bill=None, bill_month=None))
    assert "avg_monthly_units" not in f and f["net_metering_evidence"] is None


def test_bill_estimate_uses_last_month_units():
    f = build_facts(make_extraction())
    assert f["last_month"] == "2026-08" and f["last_month_units"] == 49
    assert f["bill_estimate_simple_avg_rate"] == round(1477 / 58 * 49)
