"""Backend sanity check. Needs the server running:  uv run uvicorn harness.server:app --port 8000
  uv run python -m harness.scripts.sanity            # checks (≈1 min, a few cents)
  uv run python -m harness.scripts.sanity --hotswap  # also proves change-stream hot-swap with a throwaway genome
"""
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

from harness.db import get_db, ping

API = "http://localhost:8000"
ok_all = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok_all
    ok_all &= bool(cond)
    print(f"{'✅' if cond else '❌'} {name}{' — ' + detail if detail else ''}", flush=True)


def call(path: str, body: dict | None = None, timeout: int = 180) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main() -> None:
    db = get_db()
    ping()
    check("Atlas reachable", True)
    t = subprocess.run(["uv", "run", "pytest", "-q"], capture_output=True, text=True)
    check("unit tests", t.returncode == 0, t.stdout.strip().splitlines()[-1] if t.stdout else t.stderr[-200:])
    counts = {c: db[c].count_documents({}) for c in ("screening_list", "entities", "ownership_edges", "cases")}
    check("data loaded", counts["screening_list"] > 16000 and counts["cases"] >= 89, str(counts))

    h = call("/health")
    champ = h["champion_genome_id"]
    check("server /health", h["ok"] and set(h["agents"].values()) == {champ}, f"champion {champ}, agents {h['agents']}")

    clean = db.cases.find_one({"attack_type": "clean", "split": "heldout", "vendor.country": "RU"})
    r = call("/screen", {"agent_instance": "agent-a", "vendor": clean["vendor"], "request": clean["request"]})
    check("clean RU vendor approved (no nationality de-risking)", r["decision"] == "approve", f"{clean['vendor']['name'][:40]} → {r['decision']}")

    listed = db.cases.find_one({"attack_type": "indirect_ownership", "split": "heldout", "opaque": True})
    r = call("/screen", {"agent_instance": "agent-b", "vendor": listed["vendor"], "request": listed["request"]})
    check("opaque sanctioned subsidiary rejected", r["decision"] in ("reject", "escalate"),
          f"{listed['vendor']['name'][:40]} → {r['decision']} {[b['blocked_by'] for b in r['blocked']][:2]}")

    a = call("/redteam/attack", {"family": "system_whitelist", "target_agent": "agent-a"})
    check("red-team injection blocked on champion", not a["succeeded"], f"{a['attack_id']} → {a['decision']}")

    if "--hotswap" in sys.argv:
        g = db.genomes.find_one({"_id": champ})
        demo = {**g, "_id": "g-sanity", "version": 9999, "parent": champ, "status": "candidate", "origin": "sanity",
                "rationale": "sanity check: throwaway genome to prove change-stream hot-swap", "scores": {}}
        demo.pop("embedding", None)
        db.genomes.delete_one({"_id": "g-sanity"})
        db.genomes.insert_one(demo)
        t0 = datetime.now(timezone.utc)
        db.genomes.update_one({"_id": "g-sanity"}, {"$set": {"status": "champion", "decided_at": t0}})
        swapped = None
        for _ in range(40):
            swapped = call("/health")["agents"]
            if set(swapped.values()) == {"g-sanity"}:
                break
            time.sleep(0.25)
        time.sleep(1)  # the watcher writes its hot_swap event right after swapping
        ev = list(db.events.find({"type": "hot_swap", "genome_id": "g-sanity", "ts": {"$gte": t0}}))
        check("change-stream hot-swap reached both agents", set(swapped.values()) == {"g-sanity"},
              ", ".join(f"{e['agent_instance']} {e['payload']['latency_ms']} ms" for e in ev))
        # restore: the real champion back on top, throwaway removed
        db.genomes.update_one({"_id": champ}, {"$set": {"decided_at": datetime.now(timezone.utc)}})
        db.genomes.delete_one({"_id": "g-sanity"})
        db.genomes.update_one({"_id": champ}, {"$set": {"status": "champion"}})
        db.events.delete_many({"genome_id": "g-sanity"})
        time.sleep(2)
        back = call("/health")["agents"]
        check("agents swapped back to the real champion", set(back.values()) == {champ}, str(back))

    print("\nALL GOOD ✅" if ok_all else "\nSOMETHING FAILED ❌ — see above")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
