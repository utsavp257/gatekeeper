"""Build the real dataset in the `gatekeeper` DB. Idempotent; GLEIF responses cached in data/raw/gleif_cache."""
import argparse
import urllib.request
from pathlib import Path

from harness.config import load_settings
from harness.data.cases import build_cases
from harness.data.csl import load_csl
from harness.data.gleif import GleifClient, to_entity
from harness.data.search_indexes import ENTITY_INDEX, SCREENING_INDEX, ensure_search_index
from harness.db import get_db

CSL_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv"
RAW = Path("data/raw")
CLEAN_COUNTRIES = ["DE", "NL", "AE", "HK", "CY", "TR", "IN", "SG"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-cases", action="store_true")
    args = ap.parse_args()
    db = get_db(load_settings())
    RAW.mkdir(parents=True, exist_ok=True)

    csl_path = RAW / "csl.csv"
    if not csl_path.exists():
        urllib.request.urlretrieve(CSL_URL, csl_path)
    print(f"screening_list: {load_csl(db, str(csl_path))} docs")

    listed = list(db.screening_list.find({"leis.0": {"$exists": True}}))
    gleif = GleifClient(str(RAW / "gleif_cache"))
    parent_leis = sorted({l for d in listed for l in d["leis"]})
    entities = {r["id"]: to_entity(r) for r in gleif.records(parent_leis)}
    edges, children, grandchildren = [], {}, {}
    for i, lei in enumerate(parent_leis):
        kids = [to_entity(r) for r in gleif.direct_children(lei)]
        children[lei] = kids
        for k in kids:
            entities[k["_id"]] = k
            edges.append({"child_lei": k["_id"], "parent_lei": lei, "type": "direct"})
        if i % 20 == 0:
            print(f"  gleif children {i}/{len(parent_leis)}")
    for lei, kids in list(children.items()):
        for k in kids[:1]:
            gk = [to_entity(r) for r in gleif.direct_children(k["_id"])]
            grandchildren[k["_id"]] = gk
            for g in gk:
                entities[g["_id"]] = g
                edges.append({"child_lei": g["_id"], "parent_lei": k["_id"], "type": "direct"})
    clean = []
    for c in CLEAN_COUNTRIES:
        clean += [to_entity(r) for r in gleif.by_country(c, 20)]
    for e in clean:
        entities.setdefault(e["_id"], e)

    db.entities.drop()
    db.entities.insert_many(list(entities.values()))
    db.ownership_edges.drop()
    db.ownership_edges.insert_many(edges)
    db.ownership_edges.create_index("child_lei")
    db.ownership_edges.create_index("parent_lei")
    print(f"entities: {len(entities)}  ownership_edges: {len(edges)}")

    if db.cases.count_documents({}) and not args.rebuild_cases:
        print("cases exist — keeping locked held-out set (pass --rebuild-cases to regenerate)")
    else:
        rng_clean = sorted(clean, key=lambda e: e["_id"])
        cases, labels = build_cases(listed + list(db.screening_list.find({"leis": [], "country": {"$ne": None}}).limit(400)),
                                    children, grandchildren, rng_clean)
        db.cases.drop()
        db.case_labels.drop()
        db.cases.insert_many(cases)
        db.case_labels.insert_many(labels)
        db.case_labels.create_index("case_id", unique=True)
        print(f"cases: {len(cases)}")

    ensure_search_index(db.screening_list, SCREENING_INDEX)
    ensure_search_index(db.entities, ENTITY_INDEX)
    print("search indexes ready")


if __name__ == "__main__":
    main()
