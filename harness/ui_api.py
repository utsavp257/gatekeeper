"""Read-only JSON for the built-in dashboard (harness/ui/index.html) + a token-protected live hot-swap demo.
Never exposes case_labels, embeddings or raw critic output."""
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

UI_FILE = Path(__file__).parent / "ui" / "index.html"
HIDDEN_GENOMES = {"ref-all-tools", "g-sanity", "g-live-demo"}


def _iso(v):
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def genome_summary(g: dict) -> dict:
    held = (g.get("scores") or {}).get("heldout") or {}
    p = g.get("policy") or {}
    return {"id": g["_id"], "version": g.get("version"), "parent": g.get("parent"), "status": g.get("status"),
            "origin": g.get("origin"), "rationale": g.get("rationale", ""), "gate_reason": g.get("gate_reason"),
            "diff": g.get("diff") or [], "created_at": _iso(g.get("created_at")), "decided_at": _iso(g.get("decided_at")),
            "heldout": {k: held.get(k) for k in ("catch_rate", "false_block_rate", "injection_block_rate")} if held else None,
            "tools": (p.get("tools") or {}).get("allow"), "antibodies": len(p.get("antibodies") or [])}


def event_summary(e: dict) -> dict:
    payload = {k: v for k, v in (e.get("payload") or {}).items() if k not in ("embedding", "chunk")}
    for k, v in list(payload.items()):
        if isinstance(v, str) and len(v) > 240:
            payload[k] = v[:240] + "…"
    return {"id": str(e["_id"]), "ts": _iso(e.get("ts")), "type": e.get("type"), "agent": e.get("agent_instance"),
            "genome": e.get("genome_id"), "payload": payload}


def build_router(db, agents: dict) -> APIRouter:
    r = APIRouter()

    @r.get("/", include_in_schema=False)
    @r.get("/ui", include_in_schema=False)
    def ui():
        return FileResponse(UI_FILE)

    @r.get("/api/overview")
    def overview() -> dict:
        genomes = [genome_summary(g) for g in db.genomes.find({"_id": {"$nin": list(HIDDEN_GENOMES)}},
                                                                {"embedding": 0, "critic_raw": 0}).sort("version", 1)]
        rep = db.reports.find_one({"note": {"$regex": "^FINAL"}}, sort=[("created_at", -1)])
        report = None
        if rep:
            report = {gid: {k: (row.get(k) or {}).get("mean") for k in ("catch_rate", "false_block_rate",
                                                                          "injection_catch", "cost_per_case_usd")}
                      | {"runs": row.get("runs"), "n": row.get("n")} for gid, row in rep["rows"].items()}
        now = datetime.now(timezone.utc)
        live = []
        for a in db.agents.find().sort("_id", 1):
            hb = a.get("last_heartbeat")
            hb = hb.replace(tzinfo=timezone.utc) if hb and not hb.tzinfo else hb
            live.append({"id": a["_id"], "genome": a.get("genome_id"), "heartbeat_age_s":
                         round((now - hb).total_seconds(), 1) if hb else None})
        champ = next((g["id"] for g in reversed(genomes) if g["status"] == "champion"), None)
        return {"genomes": genomes, "report": report, "agents": live, "champion": champ,
                "counts": {"screening_list": db.screening_list.estimated_document_count(),
                           "ownership_edges": db.ownership_edges.estimated_document_count(),
                           "cases": db.cases.count_documents({})}}

    @r.get("/api/events")
    def events(after: str | None = None, limit: int = 60) -> dict:
        q = {"genome_id": {"$nin": ["g-sanity"]}}
        if after:
            q["ts"] = {"$gt": datetime.fromisoformat(after)}
        docs = list(db.events.find(q).sort("ts", -1).limit(min(limit, 200)))
        return {"events": [event_summary(e) for e in reversed(docs)]}

    @r.get("/api/traces/{trace_id}")
    def trace(trace_id: str) -> dict:
        t = db.traces.find_one({"_id": trace_id}, {"usage": 0})
        if not t:
            raise HTTPException(404, "unknown trace")
        return {"id": t["_id"], "decision": t.get("decision"), "memo": t.get("memo"), "genome": t.get("genome_id"),
                "cost_usd": t.get("cost_usd"), "duration_s": t.get("duration_s"),
                "steps": [{"tool": s["tool"], "blocked_by": s.get("blocked_by"), "result": s.get("result_summary", "")[:200]}
                          for s in t.get("steps", [])]}

    @r.get("/api/presets")
    def presets() -> dict:
        picks = [("c-068", "Clean Russian bank"), ("c-022", "Dubai trader with a sanctioned parent"),
                 ("c-043-lega", "Misspelled sanctioned bank + fake legal clearance")]
        out = []
        for cid, label in picks:
            c = db.cases.find_one({"_id": cid}, {"vendor": 1, "request": 1})
            if c:
                out.append({"label": label, "vendor": c["vendor"], "request": c["request"]})
        return {"presets": out}

    def demo_hotswap() -> dict:
        """Promote a throwaway copy of the champion so both live agents hot-swap, then restore. Nothing is lost."""
        champ = db.genomes.find_one({"status": "champion"}, sort=[("version", -1)])
        demo = {**champ, "_id": "g-live-demo", "version": 9998, "parent": champ["_id"], "status": "candidate",
                "origin": "demo", "rationale": "live demo promotion", "scores": {}}
        demo.pop("embedding", None)
        db.genomes.delete_one({"_id": "g-live-demo"})
        db.genomes.insert_one(demo)
        t0 = datetime.now(timezone.utc)
        db.genomes.update_one({"_id": "g-live-demo"}, {"$set": {"status": "champion", "decided_at": t0}})
        for _ in range(40):
            if all(a.current()["_id"] == "g-live-demo" for a in agents.values()):
                break
            time.sleep(0.1)
        time.sleep(0.8)
        swaps = [{"agent": e["agent_instance"], "latency_ms": e["payload"]["latency_ms"]}
                 for e in db.events.find({"type": "hot_swap", "genome_id": "g-live-demo", "ts": {"$gte": t0}})]
        db.genomes.update_one({"_id": champ["_id"]}, {"$set": {"decided_at": datetime.now(timezone.utc)}})
        db.genomes.delete_one({"_id": "g-live-demo"})
        return {"swaps": swaps, "restored_to": champ["_id"]}

    r.demo_hotswap = demo_hotswap  # registered with auth in server.py
    return r
