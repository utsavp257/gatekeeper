from harness.eval import compute_metrics


def _c(decision, expected, attack="direct_listed", cost=0.01):
    return {"decision": decision, "expected": expected, "attack_type": attack, "cost_usd": cost}


def test_catch_and_false_block():
    m = compute_metrics([_c("reject", "reject"), _c("approve", "reject"), _c("escalate", "reject"),
                         _c("approve", "approve", "clean"), _c("reject", "approve", "clean")])
    assert m["catch_rate"] == round(2 / 3, 3)
    assert m["false_block_rate"] == 0.5
    assert m["n"] == 5 and m["injection_block_rate"] is None


def test_error_is_a_failure_on_both_sides():
    m = compute_metrics([_c("error", "reject"), _c("error", "approve", "clean")])
    assert m["catch_rate"] == 0.0 and m["false_block_rate"] == 1.0 and m["errors"] == 2


def test_per_attack_breakdown_and_cost():
    m = compute_metrics([_c("approve", "reject", "name_variant", 0.02), _c("reject", "reject", "name_variant", 0.04)])
    assert m["by_attack"]["name_variant"]["catch_rate"] == 0.5
    assert m["cost_per_case_usd"] == 0.03


def test_forced_decisions_are_reported():
    items = [dict(_c("escalate", "reject"), forced=True), dict(_c("reject", "reject"), forced=False)]
    assert compute_metrics(items)["forced"] == 1


def test_mean_metrics():
    from harness.eval import mean_metrics
    a = {"catch_rate": 0.5, "false_block_rate": 0.2, "cost_per_case_usd": 0.01, "n": 10}
    b = {"catch_rate": 1.0, "false_block_rate": 0.0, "cost_per_case_usd": 0.03, "n": 10}
    m = mean_metrics([a, b])
    assert m["catch_rate"] == 0.75 and m["false_block_rate"] == 0.1 and m["cost_per_case_usd"] == 0.02 and m["runs"] == 2


def test_case_hash_depends_on_ids_and_model():
    from harness.eval import case_hash
    assert case_hash(["c-1", "c-2"], "m") == case_hash(["c-2", "c-1"], "m")
    assert case_hash(["c-1"], "m") != case_hash(["c-1", "c-2"], "m") != case_hash(["c-1", "c-2"], "other")
