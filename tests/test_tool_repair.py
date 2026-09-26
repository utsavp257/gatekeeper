from harness.agent import parse_text_decision


def test_parses_text_form_decision_calls():
    assert parse_text_decision('reject_vendor(reason="Listed on SSI (csl-SSI-1)")') == ("reject_vendor", "Listed on SSI (csl-SSI-1)")
    assert parse_text_decision("I will now call escalate(reason='ambiguous match')") == ("escalate", "ambiguous match")
    assert parse_text_decision('approve_vendor(reason="clean")\nThanks') == ("approve_vendor", "clean")


def test_no_decision_text_returns_none():
    assert parse_text_decision("I have gathered the evidence.") is None
    assert parse_text_decision("") is None
