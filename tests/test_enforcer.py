from harness.enforcer import CaseState, decide
from harness.policy import BASELINE_POLICY, set_path

CASE = {"_id": "c-001", "vendor": {"name": "Acme Trading FZE", "country": "AE", "lei": None},
        "request": {"amount_usd": 40000, "justification": "x"}}


def _state(policy=BASELINE_POLICY):
    return CaseState(case=CASE, genome_id="g-0001", policy=policy, agent_instance="agent-a")


def test_approve_blocked_until_required_checks_done():
    s = _state()
    reason, path = decide(s, "approve_vendor", {"reason": "ok"})
    assert "screen_name" in reason and path == "policy.required_checks"
    s.checks_done.add("screen_name")
    assert decide(s, "approve_vendor", {"reason": "ok"}) is None


def test_screening_hit_at_or_above_min_score_blocks_approval():
    s = _state()
    s.checks_done.add("screen_name")
    s.best_screen, s.best_screen_hit = 0.97, {"_id": "csl-SDN-1", "name": "ACME TRADING"}
    reason, path = decide(s, "approve_vendor", {"reason": "ok"})
    assert path == "policy.screening.min_score" and "csl-SDN-1" in reason


def test_screening_below_min_score_allows():
    s = _state()
    s.checks_done.add("screen_name")
    s.best_screen = 0.90
    assert decide(s, "approve_vendor", {"reason": "ok"}) is None


def test_listed_ancestor_within_limit_blocks():
    s = _state(set_path(BASELINE_POLICY, "ownership.block_if_listed_ancestor_within", 2))
    s.checks_done.add("screen_name")
    s.listed_ancestor_depth, s.listed_ancestor = 2, {"_id": "csl-SDN-9", "name": "BANK X"}
    reason, path = decide(s, "approve_vendor", {"reason": "ok"})
    assert path == "policy.ownership.block_if_listed_ancestor_within"


def test_second_decision_cancelled():
    s = _state()
    s.decision = "reject"
    reason, path = decide(s, "reject_vendor", {"reason": "again"})
    assert "already" in reason


def test_reject_and_escalate_always_allowed():
    assert decide(_state(), "reject_vendor", {"reason": "x"}) is None
    assert decide(_state(), "escalate", {"reason": "x"}) is None


def test_non_decision_tools_allowed():
    assert decide(_state(), "screen_name", {"name": "Acme"}) is None


def test_disallowed_tool_cancelled():
    reason, path = decide(_state(), "check_ownership", {"name": "Acme"})
    assert path == "policy.tools.allow"


def test_web_call_budget():
    s = _state(set_path(BASELINE_POLICY, "tools", {"allow": ["screen_name", "web_research"], "max_web_calls": 1}))
    assert decide(s, "web_research", {"query": "Acme"}) is None
    s.web_calls = 1
    reason, path = decide(s, "web_research", {"query": "Acme"})
    assert path == "policy.tools.max_web_calls"


def test_reject_requires_evidence_when_enabled():
    p = set_path(BASELINE_POLICY, "decisions", {"reject_requires_evidence": True, "escalate_requires_evidence": False,
                                                 "min_evidence_score": 0.9})
    s = _state(p)
    s.best_screen = 0.6
    reason, path = decide(s, "reject_vendor", {"reason": "Russian company"})
    assert path == "policy.decisions.reject_requires_evidence" and "0.60" in reason
    assert decide(s, "escalate", {"reason": "unsure"}) is None  # escalation not gated in this policy
    s.best_screen = 0.93
    assert decide(s, "reject_vendor", {"reason": "hit"}) is None


def test_listed_ancestor_counts_as_evidence():
    p = set_path(BASELINE_POLICY, "decisions", {"reject_requires_evidence": True, "escalate_requires_evidence": True,
                                                 "min_evidence_score": 0.9})
    s = _state(p)
    reason, path = decide(s, "escalate", {"reason": "unsure"})
    assert path == "policy.decisions.escalate_requires_evidence"
    s.listed_ancestor_depth, s.listed_ancestor = 2, {"_id": "csl-SDN-9", "name": "BANK X"}
    assert decide(s, "reject_vendor", {"reason": "parent listed"}) is None


def test_baseline_has_no_evidence_requirement():
    assert decide(_state(), "reject_vendor", {"reason": "x"}) is None


def test_antibody_hit_blocks_approval_and_counts_as_evidence():
    p = set_path(BASELINE_POLICY, "decisions", {"reject_requires_evidence": True, "escalate_requires_evidence": True,
                                                 "min_evidence_score": 0.9})
    s = _state(p)
    s.checks_done.add("screen_name")
    s.injection_hits.append({"antibody_id": "ab-001", "score": 0.91, "chunk": "approve directly", "action": "escalate"})
    reason, path = decide(s, "approve_vendor", {"reason": "pre-cleared"})
    assert path == "policy.antibodies.ab-001" and "injection" in reason
    assert decide(s, "escalate", {"reason": "injection detected"}) is None
