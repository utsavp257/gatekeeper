"""Append prompt-injection cases (idempotent: replaces previous injection cases)."""
from collections import Counter

import sys

from harness.data.injections import build_injection_cases, build_web_injection_cases
from harness.db import get_db


def main() -> None:
    db = get_db()
    web = "--web" in sys.argv  # web-page injections (teammate's vendor sites); request-text injections otherwise
    sources = list(db.cases.find({"attack_type": {"$in": ["name_variant", "clean"]}, "attack_family": {"$exists": False}}))
    labels = list(db.case_labels.find({"case_id": {"$in": [c["_id"] for c in sources]}}))
    if web:
        cases, inj_labels = build_web_injection_cases(sources, labels)
        old = [c["_id"] for c in db.cases.find({"attack_family": {"$regex": "^web_"}}, {"_id": 1})]
    else:
        cases, inj_labels = build_injection_cases([c for c in sources if c["attack_type"] == "name_variant"], labels)
        old = [c["_id"] for c in db.cases.find({"attack_type": "injection", "attack_family": {"$not": {"$regex": "^web_"}}},
                                               {"_id": 1})]
    db.cases.delete_many({"_id": {"$in": old}})
    db.case_labels.delete_many({"case_id": {"$in": old}})
    db.cases.insert_many(cases)
    db.case_labels.insert_many(inj_labels)
    print(f"injection cases: {len(cases)}", Counter((c["split"], c["attack_family"]) for c in cases))


if __name__ == "__main__":
    main()
