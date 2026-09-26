# Sprint 1 — Screening Data & Labeled Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load real US screening lists (CSL) and a GLEIF ownership slice into Atlas, with Atlas Search indexes, and generate about 60 labeled vendor cases. The cases are split into train and held-out, and the labels are stored apart from the cases.

**Architecture:**
- Pure transforms in `harness/data/` (CSL row → doc, GLEIF record → entity/edge, case generation) are unit-tested offline.
- A rate-limited GLEIF client caches every response on disk, so reruns are free and deterministic.
- `harness/scripts/build_dataset.py` orchestrates loading into the `gatekeeper` DB.
- `harness/scripts/verify_dataset.py` proves the fuzzy search works against a real name variant.

**Tech Stack:** Python 3.12, pymongo (including `SearchIndexModel`), stdlib `urllib`/`csv`, pytest.

**Spec:** `HANDOFF.md` §4 (data sources), §6 (the `screening_list`, `entities`, `ownership_edges`, `cases` and `case_labels` contract), §12 (risks)

## Global Constraints

- Field names are exactly as in HANDOFF §6. Use `cases.attack_type` ∈ {`clean`, `direct_listed`, `name_variant`, `indirect_ownership`} in this sprint; `injection` is added in Sprint 5.
- `case_labels` is a separate collection. `cases` documents must never contain the expected outcome or evidence.
- Held-out cases use **different listed parents** (groups) than train cases.
- The case set is generated with a fixed seed (`seed=7`), and `build_dataset` refuses to rebuild cases once they exist unless `--rebuild-cases` is given. The held-out set is locked after this sprint.
- GLEIF: sleep at least 1.0s between uncached requests, and cache under `data/raw/gleif_cache/` (gitignored).

## Review Focus

- A CSL row whose `type` is Individual, Vessel or Aircraft → excluded. Rows with an empty `type` (common on the BIS Entity List) → kept.
- A CSL address with no country code (e.g. `"Moscow"`) → `country` is `None`, not a garbage token.
- A GLEIF entity whose legal name is Cyrillic or Chinese → the vendor-facing `display_name` uses a Latin-script `otherNames` entry when one exists.
- A GLEIF child that is itself on the CSL (by LEI or normalized name) → not used as an `indirect_ownership` case, because that would be a direct hit.
- A name variant that is identical, after normalization, to the original name or one of its `alt_names` → rejected and regenerated, since otherwise the case is really `direct_listed`.

---

## File structure

```
harness/data/__init__.py
harness/data/normalize.py        # normalize_name(), is_latin()
harness/data/csl.py              # parse_csl_row(), load_csl()
harness/data/gleif.py            # GleifClient (cached, rate-limited), to_entity()
harness/data/search_indexes.py   # SCREENING_INDEX, ENTITY_INDEX, ensure_search_index()
harness/data/cases.py            # name_variants(), build_cases()
harness/scripts/build_dataset.py # CLI orchestrator
harness/scripts/verify_dataset.py
tests/test_normalize.py
tests/test_csl.py
tests/test_gleif_transform.py
tests/test_cases.py
```

---

### Task 1: Name normalization and CSL parsing, plus loader and search index

**Files:** Create `harness/data/__init__.py`, `harness/data/normalize.py`, `harness/data/csl.py`, `harness/data/search_indexes.py`. Test: `tests/test_normalize.py`, `tests/test_csl.py`

**Interfaces:**
- Produces:
  - `normalize_name(s: str) -> str`: uppercase, punctuation removed, corporate suffixes dropped, whitespace collapsed
  - `is_latin(s: str) -> bool`
  - `parse_csl_row(row: dict) -> dict | None`
  - `load_csl(db, path: str) -> int`
  - `ensure_search_index(collection, model: dict, timeout_s: int = 180) -> None`
  - `SCREENING_INDEX`, `ENTITY_INDEX`
  - the Atlas Search index names `screening_names` (on `screening_list`) and `entity_names` (on `entities`)

- [ ] **Step 1: Failing tests**

`tests/test_normalize.py`:
```python
from harness.data.normalize import is_latin, normalize_name


def test_strips_suffixes_and_punctuation():
    assert normalize_name('PJSC "LUKOIL"') == "LUKOIL"
    assert normalize_name("China Telecom Co., Ltd.") == "CHINA TELECOM"
    assert normalize_name("Acme  Trading  FZE") == "ACME TRADING"


def test_is_latin():
    assert is_latin("VTB Bank (PJSC)")
    assert not is_latin("Банк ВТБ")
```

`tests/test_csl.py`:
```python
from harness.data.csl import parse_csl_row

ROW = {"_id": "30882", "source": "Non-SDN Chinese Military-Industrial Complex Companies List (CMIC) - Treasury Department",
       "type": "Entity", "programs": "CMIC-EO13959", "name": "China Telecom Corporation Limited",
       "addresses": "31 Jinrong Street, Beijing, 100033, CN; Hong Kong, HK", "alt_names": "CHINA TELECOM; CHINA TELECOM CORP LTD",
       "remarks": "", "ids": "Legal Entity Number, 5493001Q6RZ4XQJEXX91, CN"}


def test_parses_entity_row():
    d = parse_csl_row(ROW)
    assert d["_id"] == "csl-CMIC-30882"
    assert d["source_list"] == "CMIC"
    assert d["alt_names"] == ["CHINA TELECOM", "CHINA TELECOM CORP LTD"]
    assert d["country"] == "CN"
    assert d["addresses"] == ["31 Jinrong Street, Beijing, 100033, CN", "Hong Kong, HK"]
    assert d["programs"] == ["CMIC-EO13959"]
    assert d["leis"] == ["5493001Q6RZ4XQJEXX91"]
    assert d["name_norm"] == "CHINA TELECOM"


def test_skips_individuals_vessels_aircraft():
    for t in ("Individual", "Vessel", "Aircraft"):
        assert parse_csl_row(dict(ROW, type=t)) is None


def test_keeps_blank_type_entity_list_rows():
    assert parse_csl_row(dict(ROW, type="", source="Entity List (EL) - Bureau of Industry and Security"))["source_list"] == "EL"


def test_country_none_when_no_code():
    assert parse_csl_row(dict(ROW, addresses="Moscow"))["country"] is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_normalize.py tests/test_csl.py -q` → Expected: collection errors (modules missing)

- [ ] **Step 3: Implement**

`harness/data/__init__.py`: empty.

`harness/data/normalize.py`:
```python
import re
import unicodedata

_SUFFIXES = {
    "LLC", "LTD", "LIMITED", "CO", "COMPANY", "CORP", "CORPORATION", "INC", "JSC", "PJSC", "OJSC", "CJSC", "OAO", "OOO",
    "ZAO", "PAO", "AO", "GMBH", "AG", "SA", "SAS", "SRL", "BV", "NV", "PLC", "FZE", "FZCO", "FZ", "LLP", "PTE", "SDN", "BHD",
    "PUBLIC", "JOINT", "STOCK", "OPEN", "CLOSED", "THE",
}


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).upper()
    s = re.sub(r"[^\w\s&]", " ", s)
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    return " ".join(tokens)


def is_latin(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)
```

`harness/data/csl.py`:
```python
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
        "_id": f"csl-{source_list}-{row['_id']}",  # CSL reuses row ids across lists
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
```

`harness/data/search_indexes.py`:
```python
import time

from pymongo.operations import SearchIndexModel

SCREENING_INDEX = {"name": "screening_names", "definition": {"mappings": {"dynamic": False, "fields": {
    "name": {"type": "string"}, "alt_names": {"type": "string"}, "country": {"type": "token"}}}}}
ENTITY_INDEX = {"name": "entity_names", "definition": {"mappings": {"dynamic": False, "fields": {
    "legal_name": {"type": "string"}, "display_name": {"type": "string"}, "other_names": {"type": "string"},
    "country": {"type": "token"}}}}}


def ensure_search_index(collection, model: dict, timeout_s: int = 180) -> None:
    existing = {i["name"]: i for i in collection.list_search_indexes()}
    if model["name"] in existing:
        collection.update_search_index(model["name"], model["definition"])
    else:
        collection.create_search_index(SearchIndexModel(definition=model["definition"], name=model["name"]))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        idx = next(iter(collection.list_search_indexes(model["name"])), None)
        if idx and idx.get("queryable"):
            return
        time.sleep(3)
    raise TimeoutError(f"search index {model['name']} not queryable after {timeout_s}s")
```

- [ ] **Step 4: Run tests** → `uv run pytest tests/test_normalize.py tests/test_csl.py -q` → Expected: all pass
- [ ] **Step 5: Commit** → `git add harness/data tests/test_normalize.py tests/test_csl.py && git commit -m "feat(data): CSL parsing, name normalization, search index helper"`

---

### Task 2: GLEIF client and entity/edge transform

**Files:** Create `harness/data/gleif.py`. Test: `tests/test_gleif_transform.py`

**Interfaces:**
- Produces:
  - `to_entity(record: dict) -> dict`: returns `{_id: LEI, legal_name, display_name, other_names[], country, status}`
  - `GleifClient(cache_dir: str, min_interval_s: float = 1.0)` with these methods:
    - `.records(leis: list[str]) -> list[dict]` (batches of up to 100)
    - `.direct_children(lei: str) -> list[dict]` (all pages)
    - `.by_country(country: str, n: int) -> list[dict]`

- [ ] **Step 1: Failing test**

`tests/test_gleif_transform.py`:
```python
from harness.data.gleif import to_entity

REC = {"id": "253400V1H6ART1UQ0N98", "attributes": {"entity": {
    "legalName": {"name": "Банк ВТБ (публичное акционерное общество)"},
    "otherNames": [{"name": "Банк ВТБ (ПАО)"}, {"name": "VTB Bank (PJSC)"}],
    "legalAddress": {"country": "RU"}, "status": "ACTIVE"}}}


def test_prefers_latin_display_name():
    e = to_entity(REC)
    assert e["_id"] == "253400V1H6ART1UQ0N98"
    assert e["display_name"] == "VTB Bank (PJSC)"
    assert e["country"] == "RU" and e["status"] == "ACTIVE"
    assert "Банк ВТБ (ПАО)" in e["other_names"]


def test_latin_legal_name_used_directly():
    rec = {"id": "X" * 20, "attributes": {"entity": {"legalName": {"name": "LUKOIL Securities B.V."}, "otherNames": [],
                                                      "legalAddress": {"country": "NL"}, "status": "ACTIVE"}}}
    assert to_entity(rec)["display_name"] == "LUKOIL Securities B.V."
```

- [ ] **Step 2: Run to verify fail** → `uv run pytest tests/test_gleif_transform.py -q` → Expected: collection error

- [ ] **Step 3: Implement** `harness/data/gleif.py`:
```python
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from harness.data.normalize import is_latin

BASE = "https://api.gleif.org/api/v1"


def to_entity(record: dict) -> dict:
    ent = record["attributes"]["entity"]
    legal = ent["legalName"]["name"]
    others = [o["name"] for o in ent.get("otherNames") or []]
    display = legal if is_latin(legal) else next((o for o in others if is_latin(o)), legal)
    return {"_id": record["id"], "legal_name": legal, "display_name": display, "other_names": others,
            "country": ent["legalAddress"]["country"], "status": ent.get("status")}


class GleifClient:
    def __init__(self, cache_dir: str, min_interval_s: float = 1.0):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def _get(self, path: str, params: dict) -> dict:
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        f = self.cache / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if f.exists():
            return json.loads(f.read_text())
        wait = self.min_interval_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"}), timeout=30) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
        self._last = time.time()
        f.write_text(json.dumps(data))
        return data

    def records(self, leis: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(leis), 100):
            chunk = leis[i:i + 100]
            out += self._get("/lei-records", {"filter[lei]": ",".join(chunk), "page[size]": 100})["data"]
        return out

    def direct_children(self, lei: str) -> list[dict]:
        out, page = [], 1
        while True:
            d = self._get(f"/lei-records/{lei}/direct-children", {"page[size]": 200, "page[number]": page})
            out += d["data"]
            if page >= d["meta"]["pagination"]["lastPage"]:
                return out
            page += 1

    def by_country(self, country: str, n: int) -> list[dict]:
        return self._get("/lei-records", {"filter[entity.legalAddress.country]": country,
                                          "filter[entity.status]": "ACTIVE", "page[size]": n})["data"]
```

- [ ] **Step 4: Run tests** → Expected: pass
- [ ] **Step 5: Commit** → `git add harness/data/gleif.py tests/test_gleif_transform.py && git commit -m "feat(data): cached rate-limited GLEIF client and entity transform"`

---

### Task 3: Case generation (variants, groups, split, hidden labels)

**Files:** Create `harness/data/cases.py`. Test: `tests/test_cases.py`

**Interfaces:**
- Consumes: `normalize_name`
- Produces:
  - `name_variants(name: str, forbidden_norms: set[str], rng: random.Random, k: int = 1) -> list[str]`
  - `build_cases(listed: list[dict], children: dict[str, list[dict]], grandchildren: dict[str, list[dict]], clean: list[dict], seed: int = 7) -> tuple[list[dict], list[dict]]`
  - `listed` holds `screening_list` docs, `children`/`grandchildren` map a parent LEI to entity docs, and `clean` holds entity docs
  - the function returns `(cases, case_labels)`

- [ ] **Step 1: Failing tests**

`tests/test_cases.py`:
```python
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
```

- [ ] **Step 2: Run to verify fail** → Expected: collection error

- [ ] **Step 3: Implement** `harness/data/cases.py`:
```python
"""Labeled vendor cases. Each non-clean case has a `group` = the listed entity it traces back to,
so train and held-out never share a listed party."""
import random

from harness.data.normalize import normalize_name

_SWAPS = [("Y", "I"), ("KS", "X"), ("PH", "F"), ("OV", "OFF"), ("EV", "EFF"), ("SH", "SCH"), ("KH", "H"), ("TS", "TZ"),
          ("AND", "&"), ("OIL", "OYL"), ("BANK", "BANC")]
_SUFFIXES = ["LLC", "Ltd", "Trading LLC", "Group", "FZE", "International"]
_JUSTIFICATIONS = ["Raw materials supplier for Q4 production", "Logistics and freight forwarding services",
                   "Industrial components, recurring monthly order", "IT hardware reseller", "Consulting engagement"]


def name_variants(name: str, forbidden_norms: set[str], rng: random.Random, k: int = 1) -> list[str]:
    out, attempts = [], 0
    while len(out) < k and attempts < 50:
        attempts += 1
        v = name.upper()
        for a, b in rng.sample(_SWAPS, len(_SWAPS)):
            if a in v:
                v = v.replace(a, b, 1)
                break
        else:
            i = rng.randrange(1, max(2, len(v) - 1))
            v = v[:i] + v[i + 1:]
        words = [w for w in v.split() if normalize_name(w)]
        v = " ".join(words[:3]).title() + " " + rng.choice(_SUFFIXES)
        if normalize_name(v) not in forbidden_norms and normalize_name(v) and v not in out:
            out.append(v)
    return out


def _case(cid, split, attack, name, country, lei, group, rng):
    return {"_id": cid, "split": split, "attack_type": attack, "group": group,
            "vendor": {"name": name, "country": country, "lei": lei, "website": None},
            "request": {"amount_usd": rng.randrange(5, 121) * 1000, "justification": rng.choice(_JUSTIFICATIONS)}}


def build_cases(listed, children, grandchildren, clean, seed: int = 7):
    rng = random.Random(seed)
    listed = sorted(listed, key=lambda d: d["_id"])
    forbidden = {d["name_norm"] for d in listed} | {normalize_name(a) for d in listed for a in d["alt_names"]}
    listed_leis = {lei for d in listed for lei in d["leis"]}

    with_kids = [d for d in listed if any(children.get(l) for l in d["leis"])]
    others = [d for d in listed if d not in with_kids]
    rng.shuffle(with_kids)
    rng.shuffle(others)
    groups = [d["_id"] for d in with_kids + others]
    held_groups = set(groups[::3])  # every third listed party goes to held-out
    split_of = lambda g: "heldout" if g in held_groups else "train"  # noqa: E731

    cases, labels = [], []

    def add(attack, name, country, lei, group, evidence):
        split = split_of(group) if group else ("heldout" if len(cases) % 3 == 0 else "train")
        cid = f"c-{len(cases) + 1:03d}"
        cases.append(_case(cid, split, attack, name, country, lei, group, rng))
        labels.append({"case_id": cid, "expected": "approve" if attack == "clean" else "reject",
                       "reason": attack, "evidence": evidence})

    for d in with_kids[:18]:
        parent_lei = next(l for l in d["leis"] if children.get(l))
        kids = [k for k in children[parent_lei] if k["_id"] not in listed_leis
                and normalize_name(k["display_name"]) not in forbidden]
        if not kids:
            continue
        kid = kids[0]
        add("indirect_ownership", kid["display_name"], kid["country"], kid["_id"], d["_id"],
            {"listed_id": d["_id"], "path": [kid["_id"], parent_lei], "depth": 1})
        grand = [g for g in grandchildren.get(kid["_id"], []) if g["_id"] not in listed_leis
                 and normalize_name(g["display_name"]) not in forbidden]
        if grand and sum(c["attack_type"] == "indirect_ownership" for c in cases) < 20:
            g = grand[0]
            add("indirect_ownership", g["display_name"], g["country"], g["_id"], d["_id"],
                {"listed_id": d["_id"], "path": [g["_id"], kid["_id"], parent_lei], "depth": 2})

    pool = [d for d in others + with_kids[18:] if d["country"]]
    for d in pool[:10]:
        add("direct_listed", d["name"], d["country"], None, d["_id"], {"listed_id": d["_id"], "match": "exact"})
    for d in pool[10:24]:
        v = name_variants(d["name"], forbidden, rng)
        if v:
            add("name_variant", v[0], d["country"], None, d["_id"], {"listed_id": d["_id"], "original": d["name"]})

    for e in clean[:20]:
        if normalize_name(e["display_name"]) not in forbidden:
            add("clean", e["display_name"], e["country"], e["_id"], None, {})

    return cases, labels
```

- [ ] **Step 4: Run tests** → `uv run pytest tests/test_cases.py -q` → Expected: pass
- [ ] **Step 5: Commit** → `git add harness/data/cases.py tests/test_cases.py && git commit -m "feat(data): labeled case generation with group-disjoint held-out split"`

---

### Task 4: `build_dataset` + `verify_dataset` against Atlas

**Files:** Create `harness/scripts/build_dataset.py`, `harness/scripts/verify_dataset.py`

**Interfaces:**
- Consumes: everything above, plus `get_db`, `load_settings`
- Produces:
  - `uv run python -m harness.scripts.build_dataset [--rebuild-cases]`, which writes `screening_list`, `entities`, `ownership_edges`, `cases` and `case_labels`, and ensures both search indexes
  - `uv run python -m harness.scripts.verify_dataset`

- [ ] **Step 1: Implement** `harness/scripts/build_dataset.py`:
```python
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
```

`harness/scripts/verify_dataset.py`:
```python
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
```

- [ ] **Step 2: Run the build (in the background, about 5 min for the uncached GLEIF calls)** → `uv run python -m harness.scripts.build_dataset` → Expected: counts printed and `search indexes ready`
- [ ] **Step 3: Verify** → `uv run python -m harness.scripts.verify_dataset` → Expected:
  - around 60 cases across 4 attack types and both splits
  - the variant's top fuzzy hit is its original listed name
  - the indirect case resolves to a listed ancestor via `$graphLookup`
- [ ] **Step 4: Run the full test suite** → `uv run pytest -q` → Expected: all pass
- [ ] **Step 5: Commit and push** → `git add harness/scripts/build_dataset.py harness/scripts/verify_dataset.py && git commit -m "feat(data): build and verify real screening dataset in Atlas" && git push`

## Done when (Sprint 1 exit)
- `screening_list` (~18k docs), `entities`, `ownership_edges`, `cases` (~60) and `case_labels` exist in `gatekeeper`
- A fuzzy Atlas Search finds a listed party from its name variant
- `$graphLookup` walks an indirect case up to its listed ancestor
