"""Live agent instances. Each watches `genomes` with a MongoDB change stream and hot-swaps to a newly promoted
champion within seconds ("herd immunity"), logging a hot_swap event with the measured latency."""
import threading
from datetime import datetime, timezone

from harness.genomes import champion


def champion_from_change(event: dict, current_id: str | None) -> dict | None:
    doc = event.get("fullDocument") or {}
    if event.get("operationType") not in ("insert", "update", "replace"):
        return None
    if doc.get("status") != "champion" or doc.get("_id") == current_id:
        return None
    return doc


class AgentInstance:
    def __init__(self, db, name: str):
        self.db, self.name = db, name
        self.genome = champion(db)
        self._lock = threading.Lock()
        db.agents.update_one({"_id": name}, {"$set": {"genome_id": self.genome["_id"],
                                                      "last_heartbeat": datetime.now(timezone.utc)}}, upsert=True)

    def current(self) -> dict:
        with self._lock:
            return self.genome

    def watch(self) -> None:
        """Resumes from the last token after network blips instead of dying silently (audit M5)."""
        import time as _time
        while True:
            try:
                self._watch_once()
            except Exception as e:  # noqa: BLE001 — keep the immune link alive
                print(f"[{self.name}] change stream error, resuming: {type(e).__name__}: {e}", flush=True)
                _time.sleep(2)

    _token = None

    def _watch_once(self) -> None:
        pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}]
        with self.db.genomes.watch(pipeline, full_document="updateLookup", resume_after=self._token) as stream:
            for event in stream:
                self._token = event["_id"]
                new = champion_from_change(event, self.genome["_id"])
                if not new:
                    continue
                old = self.genome["_id"]
                with self._lock:
                    self.genome = new
                now = datetime.now(timezone.utc)
                decided = new.get("decided_at")
                latency_ms = int((now - decided.replace(tzinfo=timezone.utc)).total_seconds() * 1000) if decided else None
                self.db.agents.update_one({"_id": self.name}, {"$set": {"genome_id": new["_id"], "last_heartbeat": now}})
                self.db.events.insert_one({"ts": now, "type": "hot_swap", "agent_instance": self.name,
                                           "genome_id": new["_id"],
                                           "payload": {"from": old, "to": new["_id"], "latency_ms": latency_ms,
                                                       "antibodies": len(new["policy"].get("antibodies") or [])}})
                print(f"[{self.name}] hot-swapped {old} → {new['_id']} ({latency_ms} ms)", flush=True)

    def heartbeat(self, every_s: float = 10.0) -> None:
        """Keeps agents.last_heartbeat fresh so the dashboard can show liveness (not just the last swap)."""
        import time as _time
        while True:
            try:
                self.db.agents.update_one({"_id": self.name}, {"$set": {"genome_id": self.current()["_id"],
                                                                       "last_heartbeat": datetime.now(timezone.utc)}})
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] heartbeat error: {e}", flush=True)
            _time.sleep(every_s)

    def start(self) -> "AgentInstance":
        threading.Thread(target=self.watch, daemon=True, name=f"watch-{self.name}").start()
        threading.Thread(target=self.heartbeat, daemon=True, name=f"heartbeat-{self.name}").start()
        return self
