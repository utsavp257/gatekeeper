from harness.eval import compute_metrics


def _c(decision, expected, attack="direct_listed", cost=0.01):
    return {"decision": decision, "expected": expected, "attack_type": attack, "cost_usd": cost}


def test_catch_and_false_block():
    m = compute_metrics([_c("reject", "reject"), _c("approve", "reject"), _c("escalate", "reject"),
                         _c("approve", "approve", "clean"), _c("reject", "approve", "clean")])
    assert m["catch_rate"] == round(2 / 3, 3)
    assert m["false_block_rate"] == 0.5
    assert m["n"] == 5 and m["injection_block_rate"] is None


def test_error_counts_as_not_approved_and_flagged():
    m = compute_metrics([_c("error", "reject"), _c("error", "approve", "clean")])
    assert m["catch_rate"] == 1.0 and m["false_block_rate"] == 1.0 and m["errors"] == 2


def test_per_attack_breakdown_and_cost():
    m = compute_metrics([_c("approve", "reject", "name_variant", 0.02), _c("reject", "reject", "name_variant", 0.04)])
    assert m["by_attack"]["name_variant"]["catch_rate"] == 0.5
    assert m["cost_per_case_usd"] == 0.03
