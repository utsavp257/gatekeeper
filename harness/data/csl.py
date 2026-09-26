import csv
import re

from harness.data.normalize import normalize_name

_SKIP_TYPES = {"Individual", "Vessel", "Aircraft"}
_LEI = re.compile(r"Legal Entity Number, ([A-Z0-9]{20})")


def _split(v: str) -> list[str]:
    return [p.strip() for p in (v or "").split(";") if p.strip()]


def _country(address: str) -> str | None:
    last = address.rsplit(",", 1)[-1].strip()
    return last if re.fullmatch(r"[A-Z]{2}", last) else None


def parse_csl_row(row: dict) -> dict | None:
    if row.get("type") in _SKIP_TYPES:
        return None
    m = re.search(r"\(([A-Z][A-Z-]*)\)", row["source"])
    source_list = m.group(1) if m else row["source"]
    addresses = _split(row.get("addresses", ""))
    return {
        "_id": f"csl-{source_list}-{row['_id']}",
        "source_list": source_list,
        "name": row["name"],
        "name_norm": normalize_name(row["name"]),
        "alt_names": _split(row.get("alt_names", "")),
        "country": _country(addresses[0]) if addresses else None,
        "addresses": addresses,
        "programs": _split(row.get("programs", "")),
        "remarks": row.get("remarks", ""),
        "leis": _LEI.findall(row.get("ids", "")),
    }


def load_csl(db, path: str) -> int:
    with open(path, encoding="utf-8-sig") as f:
        docs = list({d["_id"]: d for d in (parse_csl_row(r) for r in csv.DictReader(f)) if d}.values())
    db.screening_list.drop()
    db.screening_list.insert_many(docs)
    db.screening_list.create_index("leis")
    db.screening_list.create_index("name_norm")
    return len(docs)
