from billdecoder.checks import check
from tests.helpers import make_extraction


def test_old_lesco_layout_printed_current_bill_is_not_flagged():
    e = make_extraction(
        provider="LESCO", previous_reading=6529, current_reading=6618, units_consumed=89,
        charges=[{"type": "energy", "amount": 938.5}, {"type": "fpa", "amount": 193.6},
                 {"type": "surcharge", "amount": 38.27}, {"type": "quarterly_adjustment", "amount": 31.19},
                 {"type": "fixed", "amount": 400}],
        total_charges=1601.56,
        taxes=[{"type": "electricity_duty", "amount": 14.54}, {"type": "gst", "amount": 256},
               {"type": "gst", "amount": 35}, {"type": "electricity_duty", "amount": 2.9}],
        total_taxes=308.44, current_bill=1678.5, arrears=None,
        payable_within_due_date=1910, payable_after_due_date=2051)
    assert check(e) == []


def test_new_layout_fpa_outside_net_subtotal_is_not_flagged():
    e = make_extraction(
        charges=[{"type": "energy", "amount": 2636}, {"type": "subsidy", "amount": -1393},
                 {"type": "fpa", "amount": 172}],
        total_charges=1243, total_taxes=234, current_bill=1477)
    assert check(e) == []


def test_real_mismatch_still_flagged():
    e = make_extraction(total_charges=999)
    assert check(e) != []
