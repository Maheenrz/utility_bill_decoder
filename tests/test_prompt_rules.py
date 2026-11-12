
from billdecoder.extract import PROMPT, PROMPT_VERSION


def test_multiple_meter_register_rule_is_present_in_prompt():
    assert PROMPT_VERSION == "v10"
    assert "multiple separate meter-register rows" in PROMPT
    assert "A row's units value is NOT automatically the property's units_consumed." in PROMPT
    assert "NEVER copy the first register's units into units_consumed." in PROMPT
    assert "previous_reading = null" in PROMPT
    assert "current_reading = null" in PROMPT
    assert "units_consumed = null" in PROMPT
    assert "Do not add individual register units together" in PROMPT
