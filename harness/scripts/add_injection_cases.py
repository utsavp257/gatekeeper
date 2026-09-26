"""Append prompt-injection cases (idempotent: replaces previous injection cases)."""
from collections import Counter

from harness.data.injections import build_injection_cases
from harness.db import get_db


def main() -> None:
    db = get_db()
    variants = list(db.cases.find({"attack_type": "name_variant"}))
    labels = list(db.case_labels.find({"case_id": {"$in": [c["_id"] for c in variants]}}))
    cases, inj_labels = build_injection_cases(variants, labels)
    old = [c["_id"] for c in db.cases.find({"attack_type": "injection"}, {"_id": 1})]
    db.cases.delete_many({"_id": {"$in": old}})
    db.case_labels.delete_many({"case_id": {"$in": old}})
    db.cases.insert_many(cases)
    db.case_labels.insert_many(inj_labels)
    print(f"injection cases: {len(cases)}", Counter((c["split"], c["attack_family"]) for c in cases))


if __name__ == "__main__":
    main()
