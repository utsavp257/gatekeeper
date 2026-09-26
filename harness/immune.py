"""Immune step: turn injection attacks that got through on TRAIN into antibodies, then gate like any genome.
Held-out attacks (different families and wording) decide promotion, so antibodies must generalize."""
import json
from datetime import datetime, timezone

from harness.antibodies import chunks, cosine, embed_cached
from harness.eval import evaluate
from harness.eval import matching_runs
from harness.evolve import _finish, _heldout_mean, comparable_scores, gate
from harness.genomes import champion as get_champion


def centroid(vecs: list[list[float]]) -> list[float]:
    return [sum(col) / len(vecs) for col in zip(*vecs)]


def select_signature(parts: list[str], vecs: list[list[float]], benign_centroid: list[float]):
    """The attack sentence is the chunk least like ordinary request text."""
    i = min(range(len(parts)), key=lambda j: cosine(vecs[j], benign_centroid))
    return parts[i], vecs[i]


def calibrate_threshold(sig: list[float], benign_vecs: list[list[float]], margin: float = 0.05, floor: float = 0.7) -> float:
    worst = max((cosine(sig, b) for b in benign_vecs), default=0.0)
    return round(max(floor, worst + margin), 3)


def mint(db) -> dict:
    champ = get_champion(db)
    champ_scores = comparable_scores(db, champ["_id"])  # re-evaluates if the case set changed (e.g. injections added)
    run = sorted(matching_runs(db, champ["_id"], "train"), key=lambda r: r["finished_at"])[-1]
    got_through = [c for c in run["per_case"] if c["attack_type"] == "injection" and c["decision"] == "approve"]
    if not got_through:
        return {"minted": 0, "reason": "no train injection got through"}

    benign_texts = [p for c in db.cases.find({"split": "train", "attack_type": {"$ne": "injection"}})
                    for p in chunks(c["request"]["justification"])]
    # untrusted web text is scanned too, so calibrate against real (benign) web snippets as well (audit M4)
    for w in db.web_cache.find({"_id": {"$not": {"$regex": "^extract:"}}}).limit(60):
        for r in (w.get("response") or {}).get("results", [])[:2]:
            benign_texts += chunks(r.get("content", ""))[:3]
    benign_vecs = embed_cached(db, sorted(set(t for t in benign_texts if t)))
    benign_c = centroid(benign_vecs)

    existing = champ["policy"].get("antibodies") or []
    new = []
    for c in got_through:
        case = db.cases.find_one({"_id": c["case_id"]})
        parts = chunks(case["request"]["justification"])
        sig_text, sig_vec = select_signature(parts, embed_cached(db, parts), benign_c)
        if any(cosine(sig_vec, ab["embedding"]) > 0.9 for ab in existing + new):
            continue  # same attack family already covered
        n = len(existing) + len(new) + 1
        new.append({"id": f"ab-{n:03d}", "kind": "injection", "signature_text": sig_text, "embedding": sig_vec,
                    "similarity_threshold": calibrate_threshold(sig_vec, benign_vecs), "action": "escalate",
                    "source_case": c["case_id"], "created_at": datetime.now(timezone.utc), "stats": {"hits": 0}})
    if not new:
        return {"minted": 0, "reason": "all successful attacks already covered"}

    version = (db.genomes.find_one(sort=[("version", -1)]) or {"version": 0})["version"] + 1
    cid = f"g-{version:04d}"
    policy = {**champ["policy"], "antibodies": existing + new}
    doc = {"_id": cid, "version": version, "parent": champ["_id"], "status": "candidate",
           "created_at": datetime.now(timezone.utc), "origin": "immune",
           "rationale": f"Immune response: {len(new)} antibod{'y' if len(new) == 1 else 'ies'} minted from injection attacks "
                        f"that got an approval on train ({', '.join(a['source_case'] for a in new)})",
           "diff": [{"op": "append", "path": "antibodies",
                     "value": [{k: a[k] for k in ("id", "signature_text", "similarity_threshold", "action")} for a in new]}],
           "policy": policy, "scores": {}}
    db.genomes.insert_one(doc)
    for a in new:
        db.events.insert_one({"ts": datetime.now(timezone.utc), "type": "antibody", "agent_instance": None,
                              "genome_id": cid, "payload": {k: a[k] for k in ("id", "signature_text", "similarity_threshold",
                                                                              "source_case")}})
    cand_train = evaluate(db, cid, "train")["metrics"]
    ok, reason = gate(champ_scores, cand_train, None)
    if ok:
        ok, reason = gate(champ_scores, cand_train, _heldout_mean(db, cid))
    result = _finish(db, doc, ok, reason)
    if ok:
        db.genomes.update_one({"_id": champ["_id"]}, {"$set": {"status": "retired"}})
    result["minted"] = len(new)
    result["antibodies"] = [(a["id"], a["signature_text"][:80], a["similarity_threshold"]) for a in new]
    return result


def main() -> None:
    from harness.db import get_db
    print(json.dumps(mint(get_db()), default=str, indent=1))


if __name__ == "__main__":
    main()
