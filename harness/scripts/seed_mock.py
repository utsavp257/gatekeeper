"""Seed contract-shaped mock data for the dashboard.

  MONGODB_DB=gatekeeper_mock uv run python -m harness.scripts.seed_mock           # reseed
  MONGODB_DB=gatekeeper_mock uv run python -m harness.scripts.seed_mock --stream  # reseed, then emit an event every 2s
"""
import argparse
import itertools
import random
import time
from datetime import datetime, timezone

from harness.config import load_settings
from harness.db import get_db
from harness.mock.builders import EVENT_KINDS, build_agents, build_eval_runs, build_event, build_genomes

REAL_DB = "gatekeeper"
SEEDED = ("genomes", "eval_runs", "agents", "events")


def check_target_db(db_name: str, force: bool) -> None:
    if db_name == REAL_DB and not force:
        raise SystemExit(f"Refusing to seed mock data into the real '{REAL_DB}' database. "
                         "Set MONGODB_DB=gatekeeper_mock, or pass --force if you really mean it.")


def seed(db) -> str:
    for name in SEEDED:
        db[name].drop()
    genomes = build_genomes(n=8)
    champion = next(g for g in genomes if g["status"] == "champion")["_id"]
    db.genomes.insert_many(genomes)
    db.eval_runs.insert_many(build_eval_runs(genomes))
    db.agents.insert_many(build_agents(champion))
    now = datetime.now(timezone.utc)
    db.events.insert_many([build_event(k, "agent-a", champion, now) for k in EVENT_KINDS])
    return champion


def stream(db, champion: str) -> None:
    rng = random.Random()
    for i in itertools.count():
        agent = "agent-a" if i % 2 == 0 else "agent-b"
        kind = rng.choice(EVENT_KINDS)
        db.events.insert_one(build_event(kind, agent, champion, datetime.now(timezone.utc)))
        print(f"event {i}: {agent} {kind}")
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    check_target_db(settings.mongodb_db, args.force)
    db = get_db(settings)
    champion = seed(db)
    print(f"✓ seeded {settings.mongodb_db}: {', '.join(SEEDED)} (champion {champion})")
    if args.stream:
        stream(db, champion)


if __name__ == "__main__":
    main()
