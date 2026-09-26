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
