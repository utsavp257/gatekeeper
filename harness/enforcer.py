"""The enforcer: deterministic policy applied BEFORE tool execution. The model cannot override it."""
import time
from dataclasses import dataclass, field

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider

from harness.policy import required_checks_for, tool_allowed

DECISION_TOOLS = {"approve_vendor": "approve", "reject_vendor": "reject", "escalate": "escalate"}
MAX_TOOL_CALLS = 20  # backstop: after this many calls only decisions are allowed


@dataclass
class CaseState:
    case: dict
    genome_id: str
    policy: dict
    agent_instance: str
    checks_done: set = field(default_factory=set)
    best_screen: float = 0.0
    best_screen_hit: dict | None = None
    listed_ancestor_depth: int | None = None
    listed_ancestor: dict | None = None
    steps: list = field(default_factory=list)
    decision: str | None = None
    decision_reason: str | None = None
    web_calls: int = 0
    blocked: list = field(default_factory=list)
    injection_hits: list = field(default_factory=list)
    tool_calls: int = 0


def decide(state: CaseState, tool_name: str, args: dict) -> tuple[str, str] | None:
    if tool_name in DECISION_TOOLS and state.decision:
        return f"A decision ({state.decision}) is already recorded for this case.", "harness.single_decision"
    p = state.policy
    if tool_name not in DECISION_TOOLS and state.tool_calls >= MAX_TOOL_CALLS:
        return "Tool-call budget exhausted. Record your decision now (escalate if unsure).", "harness.max_tool_calls"
    if not tool_allowed(p, tool_name):
        return f"Tool {tool_name} is not granted by the current harness policy.", "policy.tools.allow"
    if tool_name == "web_research" and state.web_calls >= p.get("tools", {}).get("max_web_calls", 99):
        return "Web research budget for this case is exhausted.", "policy.tools.max_web_calls"
    if tool_name in ("reject_vendor", "escalate"):
        d = p.get("decisions") or {}
        flag = "reject_requires_evidence" if tool_name == "reject_vendor" else "escalate_requires_evidence"
        has_evidence = (state.best_screen >= d.get("min_evidence_score", 0.9) or state.listed_ancestor_depth is not None
                        or bool(state.injection_hits))
        # never deadlock: if approval is hard-blocked, a human must be reachable (escalate always allowed then)
        if tool_name == "escalate" and not has_evidence and (_approval_hard_blocked(state)
                                                             or state.tool_calls >= MAX_TOOL_CALLS):
            return None
        if d.get(flag) and not has_evidence:
            return (f"No sanctions evidence: best screening similarity {state.best_screen:.2f} < "
                    f"{d.get('min_evidence_score', 0.9)} and no listed parent found. A {tool_name} decision must rest on "
                    "evidence, not nationality or name resemblance — run the remaining checks or approve.",
                    f"policy.decisions.{flag}")
        return None
    if tool_name != "approve_vendor":
        return None
    if state.injection_hits:
        h = state.injection_hits[0]
        return (f"Antibody {h['antibody_id']} matched suspected instruction injection in untrusted text "
                f"(similarity {h['score']:.2f}): \"{h['chunk'][:120]}\". Approval not permitted; escalate for human review.",
                f"policy.antibodies.{h['antibody_id']}")
    missing = [c for c in required_checks_for(p, "approve_vendor", state.case) if c not in state.checks_done]
    if missing:
        return f"Policy requires {', '.join(missing)} before approve_vendor. Run it on the vendor, then decide.", \
               "policy.required_checks"
    if state.best_screen_hit and state.best_screen >= p["screening"]["min_score"]:
        h = state.best_screen_hit
        return (f"Screening hit {h['_id']} ({h['name']}, similarity {state.best_screen:.2f} ≥ "
                f"{p['screening']['min_score']}). Approval not permitted.", "policy.screening.min_score")
    limit = p["ownership"]["block_if_listed_ancestor_within"]
    if state.listed_ancestor_depth is not None and state.listed_ancestor_depth <= limit:
        a = state.listed_ancestor
        return (f"Listed ancestor {a['_id']} ({a['name']}) at depth {state.listed_ancestor_depth} ≤ {limit}. "
                "Approval not permitted.", "policy.ownership.block_if_listed_ancestor_within")
    return None


def _approval_hard_blocked(state: CaseState) -> bool:
    p = state.policy
    screen_block = bool(state.best_screen_hit) and state.best_screen >= p["screening"]["min_score"]
    anc_block = (state.listed_ancestor_depth is not None
                 and state.listed_ancestor_depth <= p["ownership"]["block_if_listed_ancestor_within"])
    return screen_block or anc_block or bool(state.injection_hits)


class GatekeeperHooks(HookProvider):
    def __init__(self, state: CaseState):
        self.state = state

    def register_hooks(self, registry, **kwargs):
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event: BeforeToolCallEvent):
        name, args = event.tool_use["name"], event.tool_use.get("input") or {}
        verdict = decide(self.state, name, args)
        self.state.tool_calls += 1
        if verdict:
            reason, path = verdict
            event.cancel_tool = f"BLOCKED by {path}: {reason}"
            self.state.blocked.append({"tool": name, "blocked_by": path, "reason": reason})

    def after(self, event: AfterToolCallEvent):
        content = event.result.get("content") or [{}]
        text = " ".join(str(c.get("text", "")) for c in content)
        self.state.steps.append({"t": time.time(), "tool": event.tool_use["name"],
                                 "args": event.tool_use.get("input") or {}, "result_summary": text[:400],
                                 "blocked_by": event.cancel_message and event.cancel_message.split(":")[0][11:]})
