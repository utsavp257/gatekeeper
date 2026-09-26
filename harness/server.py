"""HTTP API for the dashboard (HANDOFF §7). Two live agent instances hot-swap genomes via change streams.

  uv run uvicorn harness.server:app --port 8000
"""
import threading
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from harness.agent import run_case
from harness.data.injections import FAMILIES
from harness.db import get_db
from harness.genomes import champion
from harness.live import AgentInstance

app = FastAPI(title="Gatekeeper harness")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
db = get_db()
AGENTS: dict[str, AgentInstance] = {}
STEP_LOCK = threading.Lock()  # one evolve/immune step at a time (version numbers, promotions)


@app.on_event("startup")
def _start_agents() -> None:
    for name in ("agent-a", "agent-b"):
        AGENTS[name] = AgentInstance(db, name).start()


class Vendor(BaseModel):
    name: str
    country: str | None = None
    lei: str | None = None
    website: str | None = None


class Request(BaseModel):
    amount_usd: int = 25000
    justification: str = "New supplier onboarding"


class ScreenBody(BaseModel):
    agent_instance: str = "agent-a"
    genome_id: str | None = None  # optional override, e.g. screen with the baseline g-0001 for a before/after demo
    vendor: Vendor
    request: Request = Request()


class AttackBody(BaseModel):
    family: str = "compliance_preapproval"
    target_agent: str = "agent-a"
    payload: str | None = None  # custom wording, e.g. a paraphrase for the herd-immunity demo


def _agent(name: str) -> AgentInstance:
    if name not in AGENTS:
        raise HTTPException(404, f"unknown agent {name}")
    return AGENTS[name]


@app.get("/health")
def health() -> dict:
    return {"ok": True, "champion_genome_id": champion(db)["_id"],
            "agents": {n: a.current()["_id"] for n, a in AGENTS.items()}}


@app.post("/screen")
def screen(body: ScreenBody) -> dict:
    agent = _agent(body.agent_instance)
    case = {"_id": f"live-{uuid.uuid4().hex[:8]}", "split": "live", "attack_type": "live",
            "vendor": body.vendor.model_dump(), "request": body.request.model_dump()}
    genome = agent.current()
    if body.genome_id:
        genome = db.genomes.find_one({"_id": body.genome_id})
        if not genome:
            raise HTTPException(404, f"unknown genome {body.genome_id}")
    r = run_case(db, case, genome, body.agent_instance, run_id="live")
    return {"decision": r["decision"], "memo": r["memo"], "trace_id": r["trace_id"], "blocked": r["blocked"],
            "genome_id": genome["_id"], "cost_usd": r["cost_usd"]}


@app.post("/redteam/attack")
def attack(body: AttackBody) -> dict:
    if body.family not in FAMILIES and not body.payload:
        raise HTTPException(400, f"family must be one of {list(FAMILIES)} or give a payload")
    agent = _agent(body.target_agent)
    base = db.cases.find_one({"attack_type": "name_variant"}, sort=[("_id", 1)])
    payload = body.payload or FAMILIES[body.family]["payload"]
    attack_id = f"atk-{uuid.uuid4().hex[:6]}"
    case = {**base, "_id": attack_id, "split": "live", "attack_type": "injection", "attack_family": body.family,
            "request": {**base["request"], "justification": f"{base['request']['justification']}. {payload}"}}
    r = run_case(db, case, agent.current(), body.target_agent, run_id="redteam")
    succeeded = r["decision"] == "approve"
    db.attacks.insert_one({"_id": attack_id, "family": body.family, "payload": payload, "target_agent": body.target_agent,
                           "genome_id": agent.current()["_id"], "vendor": base["vendor"]["name"], "decision": r["decision"],
                           "succeeded": succeeded, "trace_id": r["trace_id"], "created_at": datetime.now(timezone.utc)})
    return {"attack_id": attack_id, "succeeded": succeeded, "decision": r["decision"], "blocked": r["blocked"],
            "genome_id": agent.current()["_id"], "trace_id": r["trace_id"]}


def _locked(fn):
    if not STEP_LOCK.acquire(blocking=False):
        raise HTTPException(409, "an evolve/immune step is already running")
    try:
        return fn(db)
    finally:
        STEP_LOCK.release()


@app.post("/evolve/step")
def evolve_step() -> dict:
    from harness.evolve import step
    return _locked(step)


@app.post("/immune/step")
def immune_step() -> dict:
    from harness.immune import mint
    return _locked(mint)
