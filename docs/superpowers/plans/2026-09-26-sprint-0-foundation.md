# Sprint 0 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get a Python `harness` package that connects to the Atlas sandbox cluster, and a mock-data seeder. The seeder writes contract-shaped documents (HANDOFF.md §6) so the teammate can build the dashboard immediately.

**Architecture:**
- The `harness` package is managed with `uv`.
- `harness/config.py` loads the env vars and fails loudly when one is missing.
- `harness/db.py` is the single place that creates a Mongo client.
- `harness/mock/builders.py` holds pure functions that build contract-shaped documents, and can be tested without a database.
- `harness/scripts/seed_mock.py` writes those documents into a separate `gatekeeper_mock` database. With `--stream` it keeps appending `events` so the dashboard's change-stream feed can be tested live.

**Tech Stack:** Python 3.12 (via uv), pymongo 4.x, python-dotenv, pytest.

**Spec:** `HANDOFF.md` (sections §6 Collections contract, §8 Ownership, §11 Env vars)

## Global Constraints

- The `.env` file is never committed; only `.env.example` is. The repo is public.
- Database for real data: `gatekeeper`. Database for mock data: `gatekeeper_mock`, selected with the `MONGODB_DB` env var and defaulting to `gatekeeper`.
- Collection and field names must match HANDOFF.md §6 exactly.
- Person A commits only under `/harness`, `/docs` and the root config files.

## Review Focus

- Missing or empty `MONGODB_URI` → the program exits with a clear message naming the variable. There must be no pymongo traceback.
- Wrong password, or an IP not on the Atlas allowlist → `ping` prints a hint that points at Atlas Network Access or Database Access, instead of hanging for 30s.
- Running `seed_mock` twice → the result is the same (the collections are dropped and reseeded), not duplicated documents.
- `seed_mock` pointed at the real `gatekeeper` DB by accident → it refuses unless `--force` is given.
- Mock genome lineage → every `parent` points to an existing genome, and exactly one genome is `champion`.

---

## Human setup (Utsav — do these first, ~15 min)

1. **Atlas sandbox cluster (required to be a finalist):**
   1. Open the "MongoDB Atlas Hackathon Sandbox" email and click the join link. Sign in, or create an account.
   2. Create a **Project** named `gatekeeper` through that link, then **Build a Cluster**. Use whatever tier the sandbox offers and a region near NYC (e.g. AWS us-east-1).
   3. Go to **Security → Database Access → Add New Database User**. Choose the password method with username `gatekeeper-app` and click *Autogenerate Secure Password*. Copy the password. Role: *Read and write to any database*.
   4. Go to **Security → Network Access → Add IP Address → Allow access from anywhere (`0.0.0.0/0`)**. This is needed because Vercel's IPs aren't fixed. It's acceptable for a hackathon sandbox, and we delete the cluster afterwards.
   5. Go to **Database → Connect → Drivers → Python**. Copy the `mongodb+srv://...` string and put the password in it.
   6. **Project → Access Manager → Invite to Project** your teammate's email, so they can see the data in Atlas.
2. **API keys** (each one goes into `.env`):
   - **OpenRouter:** redeem the code that arrives around 10:30am, then go to openrouter.ai → Keys → Create.
   - **Voyage AI:** sign up at dash.voyageai.com, then go to Organization → API Keys → Create and save the key. Also **add a payment method** to unlock the normal rate limits. There's no charge within the 200M free tokens.
   - **Tavily:** get the key from your teammate, or from app.tavily.com.
3. **Create `.env`** in the repo root:
   ```bash
   cd /Users/utsav/projects/gatekeeper && cp .env.example .env && open -e .env
   ```
   Paste the values in. `AGENT_MODEL` and `CRITIC_MODEL` can stay blank until Sprint 2.
4. **MongoDB MCP server for Claude Code** (lets Claude inspect the cluster, read-only):
   ```bash
   claude mcp add mongodb -e MDB_MCP_CONNECTION_STRING="<your mongodb+srv URI>" -- npx -y mongodb-mcp-server@latest --readOnly
   ```
   Then restart Claude Code in this repo. Optionally, install **MongoDB Agent Skills** from the link in the hackathon resource guide.
5. **Send to your teammate (by DM, never in the repo):**
   - the `MONGODB_URI`
   - "set `MONGODB_DB=gatekeeper_mock` until the sync after Sprint 2"
   - the repo URL: https://github.com/utsavp257/gatekeeper

---

## File structure

```
pyproject.toml                 # uv project, deps, pytest config
harness/__init__.py
harness/config.py              # Settings dataclass + load_settings()
harness/db.py                  # get_client(), get_db(), ping()
harness/__main__.py            # `python -m harness ping`
harness/mock/__init__.py
harness/mock/builders.py       # pure builders for contract-shaped mock docs
harness/scripts/__init__.py
harness/scripts/seed_mock.py   # CLI: seed gatekeeper_mock, optional --stream
tests/test_config.py
tests/test_mock_builders.py
tests/test_seed_guard.py
```

---

### Task 1: Project skeleton, config and Atlas ping

**Files:**
- Create: `pyproject.toml`, `harness/__init__.py`, `harness/config.py`, `harness/db.py`, `harness/__main__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `harness.config.Settings(mongodb_uri: str, mongodb_db: str, openrouter_api_key: str | None, agent_model: str | None, critic_model: str | None, voyage_api_key: str | None, tavily_api_key: str | None)`
  - `harness.config.load_settings(env: Mapping[str, str] | None = None) -> Settings`, which raises `ConfigError` if `MONGODB_URI` is missing or blank
  - `harness.db.get_db(settings: Settings | None = None) -> pymongo.database.Database`
  - `harness.db.ping(settings) -> None`, which raises `ConfigError` with a hint on failure

- [ ] **Step 1: Create the uv project**

Write `pyproject.toml`. There's no build system: this is an app run from the repo root, not a published package.

```toml
[project]
name = "harness"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pymongo[srv]>=4.8", "python-dotenv>=1.0"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Run `uv python pin 3.12 && uv sync`. Expected: it creates `.venv` with Python 3.12 and resolves without errors. The system python is 3.9, so the pin matters.

- [ ] **Step 2: Write the failing config tests**

`tests/test_config.py`:
```python
import pytest
from harness.config import load_settings, ConfigError


def test_missing_uri_raises_named_error():
    with pytest.raises(ConfigError, match="MONGODB_URI"):
        load_settings({})


def test_blank_uri_raises_named_error():
    with pytest.raises(ConfigError, match="MONGODB_URI"):
        load_settings({"MONGODB_URI": "   "})


def test_defaults_db_to_gatekeeper():
    s = load_settings({"MONGODB_URI": "mongodb://localhost"})
    assert s.mongodb_db == "gatekeeper"
    assert s.tavily_api_key is None


def test_reads_optional_keys():
    s = load_settings({"MONGODB_URI": "mongodb://x", "MONGODB_DB": "gatekeeper_mock", "TAVILY_API_KEY": "t"})
    assert s.mongodb_db == "gatekeeper_mock"
    assert s.tavily_api_key == "t"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.config'`

- [ ] **Step 4: Implement config, db and the CLI**

`harness/__init__.py`: empty.

`harness/config.py`:
```python
import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongodb_db: str
    openrouter_api_key: str | None
    agent_model: str | None
    critic_model: str | None
    voyage_api_key: str | None
    tavily_api_key: str | None


def _opt(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key, "").strip()
    return value or None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ
    uri = _opt(env, "MONGODB_URI")
    if not uri:
        raise ConfigError("MONGODB_URI is not set. Copy .env.example to .env and paste your Atlas connection string.")
    return Settings(
        mongodb_uri=uri,
        mongodb_db=_opt(env, "MONGODB_DB") or "gatekeeper",
        openrouter_api_key=_opt(env, "OPENROUTER_API_KEY"),
        agent_model=_opt(env, "AGENT_MODEL"),
        critic_model=_opt(env, "CRITIC_MODEL"),
        voyage_api_key=_opt(env, "VOYAGE_API_KEY"),
        tavily_api_key=_opt(env, "TAVILY_API_KEY"),
    )
```

`harness/db.py`:
```python
from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError

from harness.config import ConfigError, Settings, load_settings


@lru_cache(maxsize=4)
def _client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=8000, appname="gatekeeper-harness")


def get_db(settings: Settings | None = None) -> Database:
    settings = settings or load_settings()
    return _client(settings.mongodb_uri)[settings.mongodb_db]


def ping(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    try:
        _client(settings.mongodb_uri).admin.command("ping")
    except OperationFailure as e:
        raise ConfigError(f"Atlas rejected the credentials ({e.code}). Check Security → Database Access user/password in the URI.") from e
    except ServerSelectionTimeoutError as e:
        raise ConfigError("Could not reach Atlas within 8s. Check Security → Network Access allows your IP (or 0.0.0.0/0).") from e
    except ConfigurationError as e:
        raise ConfigError(f"MONGODB_URI looks malformed: {e}") from e
```

`harness/__main__.py`:
```python
import sys

from harness.config import ConfigError, load_settings
from harness.db import ping


def main(argv: list[str]) -> int:
    if argv[:1] != ["ping"]:
        print("usage: python -m harness ping")
        return 2
    try:
        settings = load_settings()
        ping(settings)
    except ConfigError as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ Atlas reachable, database = {settings.mongodb_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run the tests and the ping**

Run: `uv run pytest tests/test_config.py -v` → Expected: 4 passed
Run: `uv run python -m harness ping` → Expected: `✓ Atlas reachable, database = gatekeeper` (this needs the human setup to be done). Also check the failure path: `MONGODB_URI= uv run python -m harness ping` should print `✗ MONGODB_URI is not set...` with no traceback.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .python-version harness/ tests/test_config.py
git commit -m "feat(harness): project skeleton, config loading, Atlas ping"
```

---

### Task 2: Mock document builders (the contract, as code)

**Files:**
- Create: `harness/mock/__init__.py`, `harness/mock/builders.py`
- Test: `tests/test_mock_builders.py`

**Interfaces:**
- Consumes: nothing (pure functions)
- Produces:
  - `build_genomes(n: int = 6, seed: int = 0) -> list[dict]`: genome docs per §5, with a valid lineage, exactly one `champion`, some `rejected`, and scores trending upward
  - `build_eval_runs(genomes: list[dict]) -> list[dict]`: one held-out run per non-rejected genome
  - `build_agents(champion_id: str) -> list[dict]`: `agent-a` and `agent-b`
  - `build_event(kind: str, agent_instance: str, genome_id: str, ts: datetime) -> dict`: `kind` is one of `decision|blocked|promotion|rejection|antibody|hot_swap`
  - `EVENT_KINDS: tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

`tests/test_mock_builders.py`:
```python
from datetime import datetime, timezone

import pytest

from harness.mock.builders import EVENT_KINDS, build_agents, build_eval_runs, build_event, build_genomes

GENOME_KEYS = {"_id", "version", "parent", "status", "created_at", "rationale", "diff", "policy", "scores"}
METRIC_KEYS = {"catch_rate", "false_block_rate", "injection_block_rate", "cost_per_case_usd"}


def test_genomes_have_contract_fields():
    for g in build_genomes():
        assert GENOME_KEYS <= g.keys()
        assert METRIC_KEYS <= g["scores"]["heldout"].keys()
        assert {"screening", "ownership", "required_checks", "web", "antibodies"} <= g["policy"].keys()


def test_lineage_is_valid_with_one_champion():
    genomes = build_genomes(n=8)
    ids = {g["_id"] for g in genomes}
    assert genomes[0]["parent"] is None
    assert all(g["parent"] in ids for g in genomes[1:])
    assert sum(g["status"] == "champion" for g in genomes) == 1
    assert any(g["status"] == "rejected" for g in genomes)


def test_champion_scores_beat_root():
    genomes = build_genomes(n=8)
    root = genomes[0]["scores"]["heldout"]["catch_rate"]
    champ = next(g for g in genomes if g["status"] == "champion")["scores"]["heldout"]["catch_rate"]
    assert champ > root


def test_eval_runs_skip_rejected_and_use_heldout():
    genomes = build_genomes(n=8)
    runs = build_eval_runs(genomes)
    rejected = {g["_id"] for g in genomes if g["status"] == "rejected"}
    assert runs and all(r["genome_id"] not in rejected for r in runs)
    assert all(r["split"] == "heldout" and METRIC_KEYS <= r["metrics"].keys() for r in runs)


def test_agents_point_at_champion():
    agents = build_agents("g-0005")
    assert [a["_id"] for a in agents] == ["agent-a", "agent-b"]
    assert all(a["genome_id"] == "g-0005" for a in agents)


@pytest.mark.parametrize("kind", EVENT_KINDS)
def test_event_shape(kind):
    ts = datetime(2026, 9, 26, tzinfo=timezone.utc)
    e = build_event(kind, "agent-a", "g-0001", ts)
    assert e["type"] == kind and e["ts"] == ts and isinstance(e["payload"], dict)


def test_unknown_event_kind_rejected():
    with pytest.raises(ValueError):
        build_event("nope", "agent-a", "g-0001", datetime.now(timezone.utc))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_mock_builders.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.mock'`

- [ ] **Step 3: Implement the builders**

`harness/mock/__init__.py`: empty.

`harness/mock/builders.py`:
```python
"""Contract-shaped mock documents (HANDOFF.md §5–§6) so the dashboard can be built before real data exists."""
import random
from datetime import datetime, timedelta, timezone

EVENT_KINDS = ("decision", "blocked", "promotion", "rejection", "antibody", "hot_swap")

_MUTATIONS = [
    ("policy.ownership.depth_by_country.AE", 1, 3, "3 held-out misses were subsidiaries of listed parents at depth 2 in AE"),
    ("policy.screening.fuzzy_max_edits", 0, 1, "Transliterated names (e.g. 'Rosneft' vs 'Rosnyeft') slipped past exact match"),
    ("policy.screening.min_score", 0.9, 0.8, "Near-miss matches scored 0.82-0.88 and were ignored"),
    ("policy.web.sanitize", [], ["strip_imperatives"], "Vendor page instructed the agent to call approve_vendor"),
    ("policy.ownership.block_if_listed_ancestor_within", 1, 2, "Grandparent was on the Entity List"),
    ("policy.required_checks", [], [{"before_tool": "approve_vendor", "require": ["web_research"], "when": {"amount_gt": 25000}}],
     "High-value approvals happened without any web research"),
]


def _base_policy() -> dict:
    return {
        "screening": {"fuzzy_max_edits": 0, "min_score": 0.9, "fields": ["name", "alt_names"], "lists": ["ALL"]},
        "ownership": {"default_depth": 1, "depth_by_country": {}, "block_if_listed_ancestor_within": 1},
        "required_checks": [{"before_tool": "approve_vendor", "require": ["screen_name"]}],
        "web": {"sanitize": [], "treat_as_untrusted": False},
        "antibodies": [],
    }


def _scores(catch: float, rng: random.Random) -> dict:
    split = lambda c: {  # noqa: E731
        "catch_rate": round(min(c, 0.97), 3),
        "false_block_rate": round(rng.uniform(0.03, 0.08), 3),
        "injection_block_rate": round(min(c + rng.uniform(-0.1, 0.1), 1.0), 3),
        "cost_per_case_usd": round(rng.uniform(0.003, 0.006), 4),
    }
    return {"train": split(catch + 0.03), "heldout": split(catch)}


def build_genomes(n: int = 6, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    start = datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc)
    genomes = [{
        "_id": "g-0001", "version": 1, "parent": None, "status": "retired", "created_at": start,
        "rationale": "Baseline harness", "diff": [], "policy": _base_policy(), "scores": _scores(0.5, rng),
    }]
    best, catch = genomes[0], 0.5
    for v in range(2, n + 1):
        path, before, after, why = _MUTATIONS[(v - 2) % len(_MUTATIONS)]
        rejected = v % 3 == 0
        cand_catch = catch - 0.04 if rejected else catch + rng.uniform(0.05, 0.1)
        genomes.append({
            "_id": f"g-{v:04d}", "version": v, "parent": best["_id"],
            "status": "rejected" if rejected else "retired",
            "created_at": start + timedelta(minutes=12 * v), "rationale": why,
            "diff": [{"op": "set", "path": path, "from": before, "to": after}],
            "policy": _base_policy(), "scores": _scores(cand_catch, rng),
        })
        if not rejected:
            best, catch = genomes[-1], cand_catch
    best["status"] = "champion"
    return genomes


def build_eval_runs(genomes: list[dict]) -> list[dict]:
    runs = []
    for g in genomes:
        if g["status"] == "rejected":
            continue
        metrics = dict(g["scores"]["heldout"], n=20)
        runs.append({
            "_id": f"run-{g['_id']}-heldout", "genome_id": g["_id"], "split": "heldout",
            "started_at": g["created_at"], "finished_at": g["created_at"] + timedelta(minutes=3),
            "metrics": metrics, "per_case": [],
        })
    return runs


def build_agents(champion_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [{"_id": a, "genome_id": champion_id, "last_heartbeat": now} for a in ("agent-a", "agent-b")]


def build_event(kind: str, agent_instance: str, genome_id: str, ts: datetime) -> dict:
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind {kind!r}; expected one of {EVENT_KINDS}")
    payloads = {
        "decision": {"vendor": "Acme Trading FZE", "decision": "reject", "case_id": "c-017"},
        "blocked": {"tool": "approve_vendor", "blocked_by": "policy.ownership.block_if_listed_ancestor_within",
                    "reason": "Listed ancestor within 2 hops"},
        "promotion": {"from": "g-0004", "to": genome_id, "heldout_catch_rate": 0.8},
        "rejection": {"candidate": genome_id, "reason": "false_block_rate rose 0.05 → 0.12"},
        "antibody": {"antibody_id": "ab-012", "kind": "injection", "source_attack": "atk-0044"},
        "hot_swap": {"from": "g-0004", "to": genome_id, "latency_ms": 1400},
    }
    return {"ts": ts, "type": kind, "agent_instance": agent_instance, "genome_id": genome_id, "payload": payloads[kind]}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mock_builders.py -v`
Expected: all pass (7 test functions, 12 cases once the parametrized one expands)

- [ ] **Step 5: Commit**

```bash
git add harness/mock tests/test_mock_builders.py
git commit -m "feat(harness): contract-shaped mock document builders"
```

---

### Task 3: `seed_mock` CLI (with a guard and a live event stream)

**Files:**
- Create: `harness/scripts/__init__.py`, `harness/scripts/seed_mock.py`
- Test: `tests/test_seed_guard.py`

**Interfaces:**
- Consumes: `harness.config.load_settings`, `harness.db.get_db`, and everything in `harness.mock.builders`
- Produces: the CLI `uv run python -m harness.scripts.seed_mock [--force] [--stream]`, plus `check_target_db(db_name: str, force: bool) -> None`, which raises `SystemExit` when the target is the real `gatekeeper` DB and `--force` is not given

- [ ] **Step 1: Write the failing guard test**

`tests/test_seed_guard.py`:
```python
import pytest

from harness.scripts.seed_mock import check_target_db


def test_refuses_real_db_without_force():
    with pytest.raises(SystemExit):
        check_target_db("gatekeeper", force=False)


def test_allows_real_db_with_force():
    check_target_db("gatekeeper", force=True)


def test_allows_mock_db():
    check_target_db("gatekeeper_mock", force=False)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_seed_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.scripts'`

- [ ] **Step 3: Implement the seeder**

`harness/scripts/__init__.py`: empty.

`harness/scripts/seed_mock.py`:
```python
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
```

- [ ] **Step 4: Run the tests, then seed for real**

Run: `uv run pytest -v` → Expected: every test in the suite passes
Run: `MONGODB_DB=gatekeeper_mock uv run python -m harness.scripts.seed_mock` → Expected: `✓ seeded gatekeeper_mock: genomes, eval_runs, agents, events (champion g-00XX)`
Run it a second time. In Atlas → Browse Collections, `gatekeeper_mock.genomes` should still have exactly 8 documents.
Run: `uv run python -m harness.scripts.seed_mock` (no `MONGODB_DB`) → Expected: the refusal message, and nothing written.

- [ ] **Step 5: Update the handoff, then commit and push**

In `HANDOFF.md` §8, under "Rules of engagement", replace the seed-script bullet with:
```
- Until real data exists, B points the dashboard at `MONGODB_DB=gatekeeper_mock` and uses the seed script, which writes fake genomes, events and eval runs matching §6: `MONGODB_DB=gatekeeper_mock uv run python -m harness.scripts.seed_mock` (add `--stream` to emit a live event every 2s for testing the change-stream feed). B should never be blocked on A's progress. B switches to `MONGODB_DB=gatekeeper` after the Sprint 2 sync.
```

```bash
git add harness/scripts tests/test_seed_guard.py HANDOFF.md
git commit -m "feat(harness): seed_mock CLI with real-db guard and live event stream"
git push
```

---

## Done when (Sprint 0 exit)

- `uv run python -m harness ping` prints ✓ against the Atlas sandbox cluster
- `gatekeeper_mock` holds genomes, eval_runs, agents and events, visible in Atlas
- The teammate has the URI and the repo, and their dashboard shell reads `gatekeeper_mock.genomes`
- The MongoDB MCP server is connected in Claude Code
