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
