from collections import Counter

from harness.config import load_settings
from harness.db import get_db


def main() -> None:
    db = get_db(load_settings())
    for c in ("screening_list", "entities", "ownership_edges", "cases", "case_labels"):
        print(f"{c}: {db[c].count_documents({})}")
    print(Counter((c["split"], c["attack_type"]) for c in db.cases.find()))
    v = db.cases.find_one({"attack_type": "name_variant"})
    label = db.case_labels.find_one({"case_id": v["_id"]})
    hits = list(db.screening_list.aggregate([
        {"$search": {"index": "screening_names", "compound": {"should": [
            {"text": {"query": v["vendor"]["name"], "path": ["name", "alt_names"], "fuzzy": {"maxEdits": 2}}}]}}},
        {"$limit": 3}, {"$project": {"name": 1, "score": {"$meta": "searchScore"}}}]))
    print(f"variant {v['vendor']['name']!r} (listed: {label['evidence']['original']!r}) → top hits:")
    for h in hits:
        print(f"   {h['score']:.2f}  {h['name']}")
    kid = db.cases.find_one({"attack_type": "indirect_ownership"})
    chain = list(db.ownership_edges.aggregate([
        {"$match": {"child_lei": kid["vendor"]["lei"]}},
        {"$graphLookup": {"from": "ownership_edges", "startWith": "$parent_lei", "connectFromField": "parent_lei",
                          "connectToField": "child_lei", "as": "ancestors", "maxDepth": 3}}]))
    ancestors = {chain[0]["parent_lei"]} | {a["parent_lei"] for a in chain[0]["ancestors"]} if chain else set()
    listed = db.screening_list.find_one({"leis": {"$in": list(ancestors)}})
    print(f"indirect {kid['vendor']['name']!r} → listed ancestor: {listed and listed['name']!r}")


if __name__ == "__main__":
    main()
