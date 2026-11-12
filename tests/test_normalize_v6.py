from billdecoder.checks import normalize
from tests.helpers import make_extraction


def test_zero_amount_lines_are_dropped():
    e = normalize(make_extraction(
        charges=[{"type": "energy", "amount": 938.5}, {"type": "meter_rent", "amount": 0}],
        taxes=[{"type": "gst", "amount": 0}, {"type": "gst", "amount": 256}]))
    assert [c.type for c in e.charges] == ["energy"]
    assert [t.amount for t in e.taxes] == [256]
