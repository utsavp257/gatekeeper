from datetime import datetime, timezone

from harness.policy import BASELINE_POLICY


def ensure_baseline(db) -> dict:
    g = db.genomes.find_one({"_id": "g-0001"})
    if g:
        return g
    g = {"_id": "g-0001", "version": 1, "parent": None, "status": "champion",
         "created_at": datetime.now(timezone.utc), "rationale": "Baseline harness: name screening only, exact match",
         "diff": [], "policy": BASELINE_POLICY, "scores": {}}
    db.genomes.insert_one(g)
    return g


def get_genome(db, gid: str) -> dict:
    g = db.genomes.find_one({"_id": gid})
    if not g:
        raise SystemExit(f"genome {gid} not found")
    return g


def champion(db) -> dict:
    g = db.genomes.find_one({"status": "champion"}, sort=[("version", -1)])
    if g:
        return g
    if db.genomes.count_documents({"_id": {"$regex": "^g-"}}):
        raise RuntimeError("no champion genome — refusing to silently fall back to the baseline")
    return ensure_baseline(db)
