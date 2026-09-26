from harness.evolve import apply_diff, extract_json, gate, validate_diff
from harness.policy import BASELINE_POLICY


def test_valid_diff_passes_and_applies():
    diff = [{"op": "set", "path": "tools.allow", "value": ["screen_name", "check_ownership"]},
            {"op": "set", "path": "ownership.depth_by_country.CY", "value": 2},
            {"op": "set", "path": "required_checks", "value": [
                {"before_tool": "approve_vendor", "require": ["screen_name", "check_ownership"]}]}]
    assert validate_diff(diff) == []
    p = apply_diff(BASELINE_POLICY, diff)
    assert p["tools"]["allow"] == ["screen_name", "check_ownership"] and p["ownership"]["depth_by_country"]["CY"] == 2


def test_rejects_unknown_path_and_bad_values():
    assert validate_diff([{"op": "set", "path": "antibodies", "value": []}])
    assert validate_diff([{"op": "set", "path": "screening.fuzzy_max_edits", "value": 5}])
    assert validate_diff([{"op": "set", "path": "tools.allow", "value": ["rm_rf"]}])
    assert validate_diff([{"op": "set", "path": "ownership.depth_by_country.cyprus", "value": 2}])
    assert validate_diff([{"op": "set", "path": "required_checks", "value": [{"before_tool": "x", "require": []}]}])
    assert validate_diff([])


def test_extract_json_from_fenced_or_prose():
    fence = "`" * 3
    assert extract_json(f"Here you go:\n{fence}json\n{{\"a\": 1}}\n{fence}") == {"a": 1}
    assert extract_json('prefix {"a": {"b": 2}} suffix') == {"a": {"b": 2}}
    assert extract_json("no json here") is None


M = lambda c, fb, cost=0.001: {"catch_rate": c, "false_block_rate": fb, "cost_per_case_usd": cost}  # noqa: E731
CHAMP = {"train": M(0.6, 0.1), "heldout": M(0.5, 0.1)}


def test_gate_train_stage():
    assert gate(CHAMP, M(0.7, 0.1), None)[0]
    ok, why = gate(CHAMP, M(0.6, 0.1), None)
    assert not ok and "train" in why


def test_gate_heldout_stage():
    assert gate(CHAMP, M(0.7, 0.1), M(0.6, 0.1))[0]
    ok, why = gate(CHAMP, M(0.7, 0.1), M(0.45, 0.1))
    assert not ok and "catch" in why
    ok, why = gate(CHAMP, M(0.7, 0.1), M(0.6, 0.2))
    assert not ok and "false_block" in why
    ok, why = gate(CHAMP, M(0.7, 0.1), M(0.5, 0.1))
    assert not ok and "strictly" in why


def test_gate_cost_cap():
    ok, why = gate(CHAMP, M(0.9, 0.0, 0.05), None)
    assert not ok and "cost" in why
    assert gate(CHAMP, M(0.9, 0.0, 0.015), None)[0]  # under the $0.02 absolute floor


def test_decisions_paths_editable():
    assert validate_diff([{"op": "set", "path": "decisions.reject_requires_evidence", "value": True}]) == []
    assert validate_diff([{"op": "set", "path": "decisions.min_evidence_score", "value": 0.85}]) == []
    assert validate_diff([{"op": "set", "path": "decisions.min_evidence_score", "value": 2}])
