"""Generalization test on an attack surface the evolution never trained on (web-page injections on the vendor sites).
Runs a subset of cases for given genomes and stores the result in `reports` — it does not touch genome scores."""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from harness.agent import run_case
from harness.db import get_db
from harness.eval import compute_metrics
from harness.genomes import get_genome


def main() -> None:
    db = get_db()
    cases = list(db.cases.find({"attack_family": {"$regex": "^web_"}}).sort("_id", 1))
    labels = {l["case_id"]: l for l in db.case_labels.find({"case_id": {"$in": [c["_id"] for c in cases]}})}
    rows = {}
    for gid in sys.argv[1:] or ["g-0001"]:
        g = get_genome(db, gid)
        with ThreadPoolExecutor(6) as pool:
            rs = list(pool.map(lambda c: run_case(db, c, g, "agent-a", run_id=f"generalize-{gid}"), cases))
        per = [{"case_id": c["_id"], "attack_type": c["attack_type"], "family": c["attack_family"], "split": c["split"],
                "vendor": c["vendor"]["name"], "decision": r["decision"], "expected": labels[c["_id"]]["expected"],
                "forced": r["forced"], "cost_usd": r["cost_usd"], "blocked": [b["blocked_by"] for b in r["blocked"]]}
               for c, r in zip(cases, rs)]
        rows[gid] = {"metrics": compute_metrics(per), "per_case": per}
        m = rows[gid]["metrics"]
        print(f"{gid}: catch={m['catch_rate']} false_block={m['false_block_rate']} cost=${m['cost_per_case_usd']} n={m['n']}")
        for p in per:
            ok = (p["decision"] == "approve") == (p["expected"] == "approve")
            print(f"   {'✓' if ok else '✗'} {p['family']:18s} {p['split']:7s} {p['decision']:8s} (exp {p['expected']}) {p['blocked'][:2]}")
    db.reports.insert_one({"created_at": datetime.now(timezone.utc), "kind": "generalization_web_injection", "rows": rows})


if __name__ == "__main__":
    main()
