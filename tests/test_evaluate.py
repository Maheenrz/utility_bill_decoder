from billdecoder.evaluate import score_bill


def test_perfect_match_scores_one():
    gold = {"provider": "KE", "units_consumed": 151, "charges": [{"type": "fixed", "amount": 900}]}
    s, _ = score_bill(dict(gold), gold)
    assert s == 1.0


def test_numbers_within_one_rupee_ok_text_must_match():
    gold = {"tariff": "A1-R", "current_bill": 3430.24}
    s, per = score_bill({"tariff": "A1-r", "current_bill": 3430.9}, gold)
    assert per == {"tariff": 0.0, "current_bill": 1.0}


def test_extra_charge_is_penalised():
    gold = {"charges": [{"type": "energy", "amount": 100}]}
    pred = {"charges": [{"type": "energy", "amount": 100}, {"type": "fpa", "amount": 5}]}
    assert score_bill(pred, gold)[1]["charges"] == 0.5


def test_correct_null_counts():
    s, per = score_bill({"arrears": None}, {"arrears": None})
    assert per["arrears"] == 1.0
