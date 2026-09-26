import random

from harness.data.cases import build_cases, name_variants
from harness.data.normalize import normalize_name


def _listed(i, lei=None):
    name = f"Volga Petro Trading {i} JSC"
    return {"_id": f"csl-{i}", "name": name, "name_norm": normalize_name(name), "alt_names": [], "country": "RU",
            "source_list": "SDN", "leis": [lei] if lei else []}


def _ent(lei, name, country="CY"):
    return {"_id": lei, "legal_name": name, "display_name": name, "other_names": [], "country": country, "status": "ACTIVE"}


def _fixture():
    listed = [_listed(i, lei=f"P{i:019d}") for i in range(12)] + [_listed(100 + i) for i in range(12)]
    children = {f"P{i:019d}": [_ent(f"C{i:019d}", f"Northwind Holdings {i} Ltd")] for i in range(12)}
    grandchildren = {f"C{i:019d}": [_ent(f"G{i:019d}", f"Bluefin Logistics {i} BV", "NL")] for i in range(6)}
    clean = [_ent(f"N{i:019d}", f"Clean Widgets {i} GmbH", "DE") for i in range(30)]
    return listed, children, grandchildren, clean


def test_variant_differs_from_original_and_alts():
    rng = random.Random(1)
    name = "Gazprombank Joint Stock Company"
    for v in name_variants(name, {normalize_name(name)}, rng, k=5):
        assert normalize_name(v) != normalize_name(name)


def test_cases_and_labels_are_separate_and_complete():
    cases, labels = build_cases(*_fixture())
    assert len(cases) == len(labels) >= 40
    assert all("expected" not in c and "evidence" not in c for c in cases)
    assert {l["case_id"] for l in labels} == {c["_id"] for c in cases}
    kinds = {c["attack_type"] for c in cases}
    assert kinds == {"clean", "direct_listed", "name_variant", "indirect_ownership"}


def test_expected_outcomes():
    cases, labels = build_cases(*_fixture())
    by_id = {l["case_id"]: l for l in labels}
    for c in cases:
        exp = by_id[c["_id"]]["expected"]
        assert exp == ("approve" if c["attack_type"] == "clean" else "reject")


def test_heldout_groups_disjoint_from_train():
    cases, _ = build_cases(*_fixture())
    train = {c["group"] for c in cases if c["split"] == "train" and c["group"]}
    held = {c["group"] for c in cases if c["split"] == "heldout" and c["group"]}
    assert train and held and not (train & held)


def test_deterministic():
    assert build_cases(*_fixture())[0] == build_cases(*_fixture())[0]


def test_variant_keeps_distinctive_tokens():
    rng = random.Random(3)
    name = "JOINT STOCK COMPANY COMMERCIAL BANK URAL FD"
    base = normalize_name(name).split()
    for v in name_variants(name, {normalize_name(name)}, rng, k=5):
        vt = normalize_name(v).split()
        changed = [t for t in base if t not in vt]
        assert len(changed) == 1, (v, changed)  # exactly one token perturbed, rest intact
