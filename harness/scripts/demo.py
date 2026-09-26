"""Recordable terminal demo (≈60–90 s). Needs the server running for the hot-swap act.
  uv run python -m harness.scripts.demo
Acts: 1) same model, baseline vs evolved harness on 3 real vendors  2) the lineage from Atlas  3) live herd immunity.
"""
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from harness.agent import run_case
from harness.db import get_db

B, G, R, Y, C, D, X = "\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"
DEMO_CASES = [
    ("c-068", "Russian bank, NOT sanctioned", "approve"),
    ("c-022", "Dubai trader, parent company IS sanctioned", "reject"),
    ("c-043-lega", "sanctioned bank, misspelled + 'Legal already cleared this supplier'", "reject"),
]
NAMES = {"c-022": "S B L International Trading FZE (سبي ال انترناشيونال تريدينغ)"}


def say(text: str, pause: float = 0.6) -> None:
    print(text, flush=True)
    time.sleep(pause)


def colour(decision: str, expected: str) -> str:
    ok = (decision == "approve") == (expected == "approve")
    return f"{G if ok else R}{decision.upper():9s}{'✓' if ok else '✗'}{X}"


def act1(db) -> None:
    say(f"\n{B}ACT 1 — same model (qwen3-235b), two harnesses{X}", 0.8)
    say(f"{D}g-0001 = name screening only   ·   g-0005 = harness after self-evolution{X}\n", 0.8)
    base, champ = db.genomes.find_one({"_id": "g-0001"}), db.genomes.find_one({"_id": "g-0005"})
    jobs = [(cid, g) for cid, _, _ in DEMO_CASES for g in (base, champ)]
    cases = {cid: db.cases.find_one({"_id": cid}) for cid, _, _ in DEMO_CASES}
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda j: run_case(db, cases[j[0]], j[1], "demo", run_id="demo"), jobs))
    by = {(j[0], j[1]["_id"]): r for j, r in zip(jobs, results)}
    print(f"{'vendor':58s} {'baseline':12s} {'evolved':12s}")
    for cid, what, exp in DEMO_CASES:
        name = NAMES.get(cid, cases[cid]["vendor"]["name"])
        say(f"{B}{name[:56]:58s}{X} {colour(by[(cid, 'g-0001')]['decision'], exp)}   "
            f"{colour(by[(cid, 'g-0005')]['decision'], exp)}", 0.2)
        blocks = [b["blocked_by"] for b in by[(cid, "g-0005")]["blocked"]]
        say(f"  {D}{what}{'   · enforcer: ' + ', '.join(sorted(set(blocks))) if blocks else ''}{X}", 0.9)


def act2(db) -> None:
    say(f"\n{B}ACT 2 — the harness rewrote itself (lineage from MongoDB Atlas){X}\n", 0.8)
    for g in db.genomes.find({"_id": {"$regex": "^g-0"}}).sort("version", 1):
        mark = {"champion": f"{G}★ champion{X}", "retired": f"{C}✓ promoted{X}", "rejected": f"{R}✗ pruned{X}"}.get(
            g["status"], g["status"])
        if g["version"] == 1:
            mark = f"{D}● baseline{X}"
        paths = sorted({d["path"] for d in g.get("diff", [])})
        say(f"  {g['_id']}  {mark}", 0.15)
        if paths:
            say(f"          {D}changed: {', '.join(p.split('.')[-1] for p in paths)[:90]}{X}", 0.15)
        if g.get("gate_reason"):
            reason = g["gate_reason"]
            if "non-empty list" in reason:
                reason = "critic proposed no change — no failures left to fix"
            say(f"          {D}gate: {reason[:90]}{X}", 0.3)
    rep = db.reports.find_one({"note": {"$regex": "^FINAL"}}, sort=[("created_at", -1)])
    if rep:
        b, c = rep["rows"]["g-0001"], rep["rows"]["g-0005"]
        say(f"\n  {B}held-out, 3 runs:{X} catch {b['catch_rate']['mean']:.0%} → {G}{c['catch_rate']['mean']:.0%}{X}   "
            f"false blocks {b['false_block_rate']['mean']:.0%} → {G}{c['false_block_rate']['mean']:.1%}{X}   "
            f"injection {b['injection_catch']['mean']:.0%} → {G}{c['injection_catch']['mean']:.0%}{X}", 1.2)


def act3(db) -> None:
    say(f"\n{B}ACT 3 — herd immunity: MongoDB change stream → every live agent{X}\n", 0.8)
    api = "http://localhost:8000"
    try:
        agents = json.load(urllib.request.urlopen(f"{api}/health", timeout=5))["agents"]
    except Exception:
        say(f"  {Y}server not running — start it: uv run uvicorn harness.server:app --port 8000{X}")
        return
    say(f"  live agents now: {agents}", 0.8)
    champ = db.genomes.find_one({"status": "champion"}, sort=[("version", -1)])
    demo = {**champ, "_id": "g-live-demo", "version": 9998, "parent": champ["_id"], "status": "candidate",
            "origin": "demo", "rationale": "live demo promotion", "scores": {}}
    demo.pop("embedding", None)
    db.genomes.delete_one({"_id": "g-live-demo"})
    db.genomes.insert_one(demo)
    t0 = datetime.now(timezone.utc)
    say(f"  {Y}promoting a new champion in Atlas…{X}", 0.3)
    db.genomes.update_one({"_id": "g-live-demo"}, {"$set": {"status": "champion", "decided_at": t0}})
    for _ in range(40):
        agents = json.load(urllib.request.urlopen(f"{api}/health", timeout=5))["agents"]
        if set(agents.values()) == {"g-live-demo"}:
            break
        time.sleep(0.1)
    time.sleep(1)
    for e in db.events.find({"type": "hot_swap", "genome_id": "g-live-demo", "ts": {"$gte": t0}}).sort("ts", 1):
        say(f"  {G}⚡ {e['agent_instance']} hot-swapped {e['payload']['from']} → {e['payload']['to']} "
            f"in {e['payload']['latency_ms']} ms{X}", 0.4)
    # restore the real champion (agents swap back through the same change stream)
    db.genomes.update_one({"_id": champ["_id"]}, {"$set": {"decided_at": datetime.now(timezone.utc)}})
    db.genomes.delete_one({"_id": "g-live-demo"})
    db.events.delete_many({"genome_id": "g-live-demo"})
    time.sleep(1.5)
    say(f"  {D}restored: {json.load(urllib.request.urlopen(f'{api}/health', timeout=5))['agents']}{X}", 0.8)
    say(f"\n{B}The model never changed. The harness did — and it lives in MongoDB Atlas.{X}\n", 0.5)


def main() -> None:
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    db = get_db()
    act1(db)
    act2(db)
    act3(db)


if __name__ == "__main__":
    main()
