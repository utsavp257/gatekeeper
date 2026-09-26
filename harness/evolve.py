"""Evolution loop: critic proposes structured policy diffs; gate decides promotion. Diffs are data, never prompt text."""
import json
import os
import re
import time
from datetime import datetime, timezone

import voyageai
from openai import OpenAI

from harness.config import load_settings
from harness.data.search_indexes import GENOME_VECTOR_INDEX, ensure_search_index
from harness.eval import evaluate
from harness.genomes import champion as get_champion
from harness.policy import set_path

CHECKS = {"screen_name", "check_ownership", "web_research"}
SANITIZERS = {"drop_hidden_text", "strip_imperatives", "strip_urls_in_instructions"}
COST_FLOOR_USD = 0.02


def _int_in(lo, hi):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _rule_ok(r) -> bool:
    if not isinstance(r, dict) or r.get("before_tool") != "approve_vendor":
        return False
    req = r.get("require")
    if not isinstance(req, list) or not req or not set(req) <= CHECKS:
        return False
    when = r.get("when")
    if when is None:
        return True
    if not isinstance(when, dict) or not set(when) <= {"amount_gt", "country_in"}:
        return False
    if "amount_gt" in when and not _int_in(0, 10_000_000)(when["amount_gt"]):
        return False
    if "country_in" in when and not (isinstance(when["country_in"], list)
                                     and all(isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in when["country_in"])):
        return False
    return True


RULES = {
    "screening.fuzzy_max_edits": _int_in(0, 2),
    "screening.min_score": lambda v: isinstance(v, (int, float)) and 0.5 <= v <= 1.0,
    "ownership.default_depth": _int_in(1, 3),
    "ownership.block_if_listed_ancestor_within": _int_in(1, 3),
    "required_checks": lambda v: isinstance(v, list) and len(v) <= 6 and all(_rule_ok(r) for r in v),
    "tools.allow": lambda v: isinstance(v, list) and v and set(v) <= CHECKS and "screen_name" in v,
    "tools.max_web_calls": _int_in(0, 4),
    "web.sanitize": lambda v: isinstance(v, list) and set(v) <= SANITIZERS,
    "web.treat_as_untrusted": lambda v: isinstance(v, bool),
    "decisions.reject_requires_evidence": lambda v: isinstance(v, bool),
    "decisions.escalate_requires_evidence": lambda v: isinstance(v, bool),
    "decisions.min_evidence_score": lambda v: isinstance(v, (int, float)) and 0.5 <= v <= 1.0,
}
COUNTRY_DEPTH = re.compile(r"ownership\.depth_by_country\.([A-Z]{2})")


def validate_diff(diff) -> list[str]:
    if not isinstance(diff, list) or not diff:
        return ["diff must be a non-empty list of operations"]
    errors = []
    for op in diff:
        if not isinstance(op, dict) or op.get("op") != "set" or not isinstance(op.get("path"), str):
            errors.append(f"bad op {op!r}: expected {{op: 'set', path, value}}")
            continue
        path, value = op["path"].removeprefix("policy."), op.get("value")
        check = RULES.get(path) or (_int_in(1, 3) if COUNTRY_DEPTH.fullmatch(path) else None)
        if check is None:
            errors.append(f"path {path!r} is not editable")
        elif not check(value):
            errors.append(f"invalid value for {path!r}: {value!r}")
    return errors


def apply_diff(policy: dict, diff: list[dict]) -> dict:
    for op in diff:
        policy = set_path(policy, op["path"].removeprefix("policy."), op["value"])
    return policy


_FENCE = "`" * 3


def extract_json(text: str) -> dict | None:
    fenced = re.search(_FENCE + r"(?:json)?\s*(\{.*?\})\s*" + _FENCE, text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    if start != -1:
        candidates.append(text[start:text.rfind("}") + 1])
    for c in candidates:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None


def _score(m: dict) -> float:
    return (m["catch_rate"] or 0) - (m["false_block_rate"] or 0)


def gate(champ: dict, cand_train: dict, cand_heldout: dict | None) -> tuple[bool, str]:
    cap = max(1.5 * champ["train"]["cost_per_case_usd"], COST_FLOOR_USD)
    if cand_train["cost_per_case_usd"] > cap:
        return False, f"cost ${cand_train['cost_per_case_usd']:.4f}/case exceeds cap ${cap:.4f}"
    if _score(cand_train) <= _score(champ["train"]):
        return False, f"train catch−false_block {_score(cand_train):.3f} ≤ champion {_score(champ['train']):.3f}"
    if cand_heldout is None:
        return True, "train improved"
    h, c = cand_heldout, champ["heldout"]
    if (h["catch_rate"] or 0) < (c["catch_rate"] or 0):
        return False, f"held-out catch fell {c['catch_rate']} → {h['catch_rate']}"
    if (h["false_block_rate"] or 0) > (c["false_block_rate"] or 0):
        return False, f"held-out false_block rose {c['false_block_rate']} → {h['false_block_rate']}"
    better = ((h["catch_rate"] or 0) > (c["catch_rate"] or 0) or (h["false_block_rate"] or 0) < (c["false_block_rate"] or 0)
              or h["cost_per_case_usd"] < c["cost_per_case_usd"])
    if not better:
        return False, "held-out not strictly better on any metric"
    return True, (f"held-out catch {c['catch_rate']} → {h['catch_rate']}, "
                  f"false_block {c['false_block_rate']} → {h['false_block_rate']}")




CRITIC_SYSTEM = """You are the critic in a self-improving compliance-agent harness. The agent model is FIXED; you improve
the HARNESS POLICY that a deterministic enforcer applies around it. You see the current policy, the agent's failures on the
training cases (with ground truth), and similar earlier attempts with their outcomes. Propose ONE coherent, targeted policy change (a small bundle of related ops is fine)
that fixes a cluster of failures without blocking legitimate vendors or blowing up cost.

Editable paths (JSON ops of the form {"op": "set", "path": <path>, "value": <value>}):
- tools.allow: subset of ["screen_name","check_ownership","web_research"] (must include screen_name) — which tools the agent is granted
- tools.max_web_calls: int 0-4
- screening.fuzzy_max_edits: int 0-2 (Atlas Search fuzzy matching on sanctions names)
- screening.min_score: float 0.5-1.0 (name similarity at/above which approval is hard-blocked)
- ownership.default_depth: int 1-3 (how many parent levels check_ownership walks)
- ownership.depth_by_country.<ISO2>: int 1-3
- ownership.block_if_listed_ancestor_within: int 1-3 (hard-block approval if a listed parent is within N levels)
- required_checks: list of {"before_tool":"approve_vendor","require":[checks...],"when":{"amount_gt":int,"country_in":[ISO2...]}}
  (checks: screen_name, check_ownership, web_research; "when" optional) — approval is blocked until these ran on the vendor
- decisions.reject_requires_evidence / decisions.escalate_requires_evidence: bool — when true the enforcer BLOCKS
  reject_vendor / escalate unless there is evidence: a screening similarity >= decisions.min_evidence_score (float 0.5-1.0)
  or a listed parent found by check_ownership. Use this to stop rejections based on nationality or vague name resemblance.
- web.sanitize: subset of ["drop_hidden_text","strip_imperatives","strip_urls_in_instructions"]; web.treat_as_untrusted: bool
Note: granting a tool does not force its use — required_checks does. Hard blocks (min_score, block_if_listed_ancestor_within) apply
only to evidence the enforcer has actually seen.

Reply with ONLY a JSON object: {"rationale": "<one sentence: which failures, why this fixes them>", "diff": [ops...]}"""


def _embed(texts: list[str]) -> list[list[float]]:
    client = voyageai.Client(api_key=load_settings().voyage_api_key)
    return client.embed(texts, model="voyage-3.5-lite", input_type="document").embeddings


def failure_digest(db, run: dict) -> list[dict]:
    out = []
    labels = {l["case_id"]: l for l in db.case_labels.find({"case_id": {"$in": [c["case_id"] for c in run["per_case"]]}})}
    for c in run["per_case"]:
        if c["correct"]:
            continue
        case = db.cases.find_one({"_id": c["case_id"]})
        tr = db.traces.find_one({"_id": c["trace_id"]}) or {}
        out.append({"case_id": c["case_id"], "vendor": case["vendor"], "attack_type": c["attack_type"],
                    "expected": c["expected"], "decision": c["decision"], "evidence": labels[c["case_id"]]["evidence"],
                    "tool_calls": [s["tool"] for s in tr.get("steps", [])], "blocked": [b["blocked_by"] for b in c["blocked"]],
                    "memo": (tr.get("memo") or "")[:300]})
    return out


def similar_attempts(db, text: str, k: int = 4) -> list[dict]:
    if not db.genomes.count_documents({"embedding": {"$exists": True}}):
        return []
    hits = db.genomes.aggregate([
        {"$vectorSearch": {"index": "genome_vectors", "path": "embedding", "queryVector": _embed([text])[0],
                           "numCandidates": 50, "limit": k}},
        {"$project": {"_id": 1, "status": 1, "rationale": 1, "diff": 1, "gate_reason": 1,
                      "score": {"$meta": "vectorSearchScore"}}}])
    return list(hits)


def propose(db, champion: dict, run: dict) -> tuple[dict | None, str]:
    failures = failure_digest(db, run)
    summary = "; ".join(f"{f['attack_type']}:{f['decision']}" for f in failures)
    prior = similar_attempts(db, f"failures {summary}")
    user = json.dumps({"current_policy": champion["policy"], "train_metrics": run["metrics"],
                       "train_failures": failures,
                       "similar_prior_attempts": [{k: p.get(k) for k in ("_id", "status", "rationale", "diff", "gate_reason")}
                                                  for p in prior]}, default=str)
    s = load_settings()
    client = OpenAI(api_key=s.openrouter_api_key, base_url="https://openrouter.ai/api/v1", timeout=120, max_retries=2)
    resp = client.chat.completions.create(model=s.critic_model or "anthropic/claude-sonnet-5", temperature=0.2,
                                          max_tokens=4000, extra_body={"reasoning": {"effort": "low"}},
                                          messages=[{"role": "system", "content": CRITIC_SYSTEM},
                                                    {"role": "user", "content": user}])
    text = resp.choices[0].message.content or f"<empty reply, finish_reason={resp.choices[0].finish_reason}>"
    return extract_json(text), text


def _latest_run(db, genome_id: str, split: str) -> dict | None:
    return db.eval_runs.find_one({"genome_id": genome_id, "split": split}, sort=[("finished_at", -1)])


def _event(db, kind: str, genome_id: str, payload: dict) -> None:
    db.events.insert_one({"ts": datetime.now(timezone.utc), "type": kind, "agent_instance": None,
                          "genome_id": genome_id, "payload": payload})


def step(db) -> dict:
    champ = get_champion(db)
    run = _latest_run(db, champ["_id"], "train") or evaluate(db, champ["_id"], "train")
    if not _latest_run(db, champ["_id"], "heldout"):
        evaluate(db, champ["_id"], "heldout")
    champ = db.genomes.find_one({"_id": champ["_id"]})
    proposal, raw = propose(db, champ, run)
    version = (db.genomes.find_one(sort=[("version", -1)]) or {"version": 0})["version"] + 1
    cid = f"g-{version:04d}"
    doc = {"_id": cid, "version": version, "parent": champ["_id"], "status": "candidate",
           "created_at": datetime.now(timezone.utc), "rationale": (proposal or {}).get("rationale", "unparseable critic reply"),
           "diff": (proposal or {}).get("diff", []), "policy": champ["policy"], "scores": {}, "critic_raw": raw[:4000]}
    errors = ["unparseable"] if proposal is None else validate_diff(proposal.get("diff"))
    if not errors:
        doc["policy"] = apply_diff(champ["policy"], proposal["diff"])
        if doc["policy"] == champ["policy"]:
            errors = ["no-op diff"]
    db.genomes.insert_one(doc)
    if errors:
        return _finish(db, doc, False, "invalid diff: " + "; ".join(errors))
    cand_train = evaluate(db, cid, "train")["metrics"]
    ok, reason = gate(champ["scores"], cand_train, None)
    if ok:
        cand_held = evaluate(db, cid, "heldout")["metrics"]
        ok, reason = gate(champ["scores"], cand_train, cand_held)
    if ok:
        db.genomes.update_one({"_id": champ["_id"]}, {"$set": {"status": "retired"}})
        for a in ("agent-a", "agent-b"):
            db.agents.update_one({"_id": a}, {"$set": {"genome_id": cid}}, upsert=True)
    return _finish(db, doc, ok, reason)


def _finish(db, doc: dict, promoted: bool, reason: str) -> dict:
    status = "champion" if promoted else "rejected"
    emb = _embed([f"{doc['rationale']} | diff {json.dumps(doc['diff'])} | outcome {status}: {reason}"])[0]
    db.genomes.update_one({"_id": doc["_id"]}, {"$set": {"status": status, "gate_reason": reason, "embedding": emb}})
    _event(db, "promotion" if promoted else "rejection", doc["_id"],
           {"candidate": doc["_id"], "parent": doc["parent"], "reason": reason, "rationale": doc["rationale"]})
    g = db.genomes.find_one({"_id": doc["_id"]}, {"scores": 1})
    return {"candidate_id": doc["_id"], "promoted": promoted, "reason": reason, "scores": g.get("scores")}


def _openrouter_usage() -> float:
    import urllib.request
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": f"Bearer {load_settings().openrouter_api_key}"})
    return json.load(urllib.request.urlopen(req, timeout=20))["data"]["usage"]


def main() -> None:
    import argparse
    from harness.db import get_db
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--budget-usd", type=float, default=5.0)
    args = ap.parse_args()
    db = get_db()
    ensure_search_index(db.genomes, GENOME_VECTOR_INDEX)
    start = _openrouter_usage()
    for i in range(args.generations):
        t = time.time()
        r = step(db)
        spent = _openrouter_usage() - start
        print(f"gen {i + 1}: {r['candidate_id']} {'PROMOTED' if r['promoted'] else 'rejected'} — {r['reason']} "
              f"({time.time() - t:.0f}s, spent ${spent:.2f})", flush=True)
        if spent > args.budget_usd:
            print(f"budget ${args.budget_usd} reached — stopping")
            break


if __name__ == "__main__":
    main()
