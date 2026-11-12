from billdecoder.checks import check, normalize
from tests.helpers import make_extraction


def test_clean_bill_has_no_warnings():
    assert check(make_extraction()) == []


def test_positive_subsidy_is_made_negative():
    e = normalize(make_extraction(charges=[{"type": "subsidy", "amount": 1393}]))
    assert e.charges[0].amount == -1393


def test_single_combined_tax_moves_to_total_taxes():
    e = normalize(make_extraction(taxes=[{"type": "other_tax", "amount": 234}], total_taxes=None))
    assert e.taxes == [] and e.total_taxes == 234


def test_charges_not_matching_total_is_flagged():
    w = check(make_extraction(total_charges=2636))
    assert any("charges add up" in x for x in w)


def test_readings_mismatch_flagged():
    w = check(make_extraction(units_consumed=99))
    assert any("readings difference" in x for x in w)


def test_bad_date_flagged():
    w = check(make_extraction(due_date="2026-13-40"))
    assert any("due_date" in x for x in w)


def test_after_due_lower_than_within_flagged():
    w = check(make_extraction(payable_after_due_date=100))
    assert any("payable_after_due_date" in x for x in w)
