"""Contract-shaped mock documents (HANDOFF.md §5–§6) so the dashboard can be built before real data exists."""
import random
from datetime import datetime, timedelta, timezone

EVENT_KINDS = ("decision", "blocked", "promotion", "rejection", "antibody", "hot_swap")

_MUTATIONS = [
    ("policy.ownership.depth_by_country.AE", 1, 3, "3 held-out misses were subsidiaries of listed parents at depth 2 in AE"),
    ("policy.screening.fuzzy_max_edits", 0, 1, "Transliterated names (e.g. 'Rosneft' vs 'Rosnyeft') slipped past exact match"),
    ("policy.screening.min_score", 0.9, 0.8, "Near-miss matches scored 0.82-0.88 and were ignored"),
    ("policy.web.sanitize", [], ["strip_imperatives"], "Vendor page instructed the agent to call approve_vendor"),
    ("policy.ownership.block_if_listed_ancestor_within", 1, 2, "Grandparent was on the Entity List"),
    ("policy.required_checks", [], [{"before_tool": "approve_vendor", "require": ["web_research"], "when": {"amount_gt": 25000}}],
     "High-value approvals happened without any web research"),
]


def _base_policy() -> dict:
    return {
        "screening": {"fuzzy_max_edits": 0, "min_score": 0.9, "fields": ["name", "alt_names"], "lists": ["ALL"]},
        "ownership": {"default_depth": 1, "depth_by_country": {}, "block_if_listed_ancestor_within": 1},
        "required_checks": [{"before_tool": "approve_vendor", "require": ["screen_name"]}],
        "web": {"sanitize": [], "treat_as_untrusted": False},
        "antibodies": [],
    }


def _scores(catch: float, rng: random.Random) -> dict:
    def split(c: float) -> dict:
        return {
            "catch_rate": round(min(c, 0.97), 3),
            "false_block_rate": round(rng.uniform(0.03, 0.08), 3),
            "injection_block_rate": round(min(c + rng.uniform(-0.1, 0.1), 1.0), 3),
            "cost_per_case_usd": round(rng.uniform(0.003, 0.006), 4),
        }
    return {"train": split(catch + 0.03), "heldout": split(catch)}


def build_genomes(n: int = 6, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    start = datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc)
    genomes = [{
        "_id": "g-0001", "version": 1, "parent": None, "status": "retired", "created_at": start,
        "rationale": "Baseline harness", "diff": [], "policy": _base_policy(), "scores": _scores(0.5, rng),
    }]
    best, catch = genomes[0], 0.5
    for v in range(2, n + 1):
        path, before, after, why = _MUTATIONS[(v - 2) % len(_MUTATIONS)]
        rejected = v % 3 == 0
        cand_catch = catch - 0.04 if rejected else catch + rng.uniform(0.05, 0.1)
        genomes.append({
            "_id": f"g-{v:04d}", "version": v, "parent": best["_id"],
            "status": "rejected" if rejected else "retired",
            "created_at": start + timedelta(minutes=12 * v), "rationale": why,
            "diff": [{"op": "set", "path": path, "from": before, "to": after}],
            "policy": _base_policy(), "scores": _scores(cand_catch, rng),
        })
        if not rejected:
            best, catch = genomes[-1], cand_catch
    best["status"] = "champion"
    return genomes


def build_eval_runs(genomes: list[dict]) -> list[dict]:
    runs = []
    for g in genomes:
        if g["status"] == "rejected":
            continue
        metrics = dict(g["scores"]["heldout"], n=20)
        runs.append({
            "_id": f"run-{g['_id']}-heldout", "genome_id": g["_id"], "split": "heldout",
            "started_at": g["created_at"], "finished_at": g["created_at"] + timedelta(minutes=3),
            "metrics": metrics, "per_case": [],
        })
    return runs


def build_agents(champion_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [{"_id": a, "genome_id": champion_id, "last_heartbeat": now} for a in ("agent-a", "agent-b")]


def build_event(kind: str, agent_instance: str, genome_id: str, ts: datetime) -> dict:
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind {kind!r}; expected one of {EVENT_KINDS}")
    payloads = {
        "decision": {"vendor": "Acme Trading FZE", "decision": "reject", "case_id": "c-017"},
        "blocked": {"tool": "approve_vendor", "blocked_by": "policy.ownership.block_if_listed_ancestor_within",
                    "reason": "Listed ancestor within 2 hops"},
        "promotion": {"from": "g-0004", "to": genome_id, "heldout_catch_rate": 0.8},
        "rejection": {"candidate": genome_id, "reason": "false_block_rate rose 0.05 → 0.12"},
        "antibody": {"antibody_id": "ab-012", "kind": "injection", "source_attack": "atk-0044"},
        "hot_swap": {"from": "g-0004", "to": genome_id, "latency_ms": 1400},
    }
    return {"ts": ts, "type": kind, "agent_instance": agent_instance, "genome_id": genome_id, "payload": payloads[kind]}
