"""Labeled vendor cases. Each non-clean case has a `group` = the listed entity it traces back to,
so train and held-out never share a listed party."""
import random

from harness.data.normalize import is_latin, normalize_name

_SWAPS = [("Y", "I"), ("KS", "X"), ("PH", "F"), ("OV", "OFF"), ("EV", "EFF"), ("SH", "SCH"), ("KH", "H"), ("TS", "TZ"),
          ("AND", "&"), ("OIL", "OYL"), ("BANK", "BANC")]
_JUSTIFICATIONS = ["Raw materials supplier for Q4 production", "Logistics and freight forwarding services",
                   "Industrial components, recurring monthly order", "IT hardware reseller", "Consulting engagement"]


_GENERIC = {"BANK", "COMMERCIAL", "TRADING", "GROUP", "INTERNATIONAL", "INDUSTRIAL", "HOLDING", "HOLDINGS", "IMPORT",
            "EXPORT", "INVESTMENT", "TECHNOLOGY", "TECHNOLOGIES", "ELECTRONICS", "SERVICES", "ENGINEERING", "OF", "&"}
_SUFFIX_OUT = ["LLC", "Ltd", "FZE", "Co", "Limited"]


def _perturb(token: str, rng: random.Random) -> str:
    for a, b in rng.sample(_SWAPS, len(_SWAPS)):
        if a in token and token != a:
            return token.replace(a, b, 1)
    vowels = [i for i, c in enumerate(token) if c in "AEIOU" and 0 < i < len(token) - 1]
    if vowels:
        i = rng.choice(vowels)
        return token[:i] + token[i + 1:]
    return token + token[-1]


def name_variants(name: str, forbidden_norms: set[str], rng: random.Random, k: int = 1) -> list[str]:
    """Realistic evasion: keep every distinctive word, perturb exactly one (transliteration swap or dropped letter)."""
    tokens = normalize_name(name).split()
    targets = [i for i, t in enumerate(tokens) if t not in _GENERIC and len(t) >= 4] or \
              [i for i, t in enumerate(tokens) if len(t) >= 3]
    out, attempts = [], 0
    while targets and len(out) < k and attempts < 50:
        attempts += 1
        i = rng.choice(targets)
        new = _perturb(tokens[i], rng)
        if new == tokens[i] or new in tokens:
            continue
        v = " ".join(tokens[:i] + [new] + tokens[i + 1:]).title() + " " + rng.choice(_SUFFIX_OUT)
        if normalize_name(v) not in forbidden_norms and v not in out:
            out.append(v)
    return out


def _case(cid, attack, name, country, lei, group, rng, opaque):
    return {"_id": cid, "split": None, "attack_type": attack, "group": group, "opaque": opaque,
            "vendor": {"name": name, "country": country, "lei": lei, "website": None},
            "request": {"amount_usd": rng.randrange(5, 121) * 1000, "justification": rng.choice(_JUSTIFICATIONS)}}


def _opaque(vendor_name: str, listed: dict) -> bool:
    """True when the vendor name gives no lexical hint of the listed party (no shared distinctive token)."""
    v = {t for t in normalize_name(vendor_name).split() if len(t) >= 4 and t not in _GENERIC}
    names = [listed["name"], *listed.get("alt_names", [])]
    return not any(v & {t for t in normalize_name(n).split() if len(t) >= 4} for n in names)


def _assign_splits(cases: list[dict]) -> None:
    """Every third group within each stratum goes to held-out, so both splits see every attack type and both
    opaque and name-leaking variants. A group never spans splits."""
    groups: dict = {}
    for c in cases:
        key = c["group"] or c["_id"]
        groups.setdefault(key, []).append(c)
    strata: dict = {}
    for key, members in sorted(groups.items()):
        sig = tuple(sorted({(m["attack_type"], m["opaque"]) for m in members}))
        strata.setdefault(sig, []).append(members)
    for members_list in strata.values():
        for i, members in enumerate(members_list):
            for m in members:
                m["split"] = "heldout" if i % 3 == 1 else "train"


def build_cases(listed, children, grandchildren, clean, seed: int = 7, clean_quota: dict | None = None):
    rng = random.Random(seed)
    listed = sorted(listed, key=lambda d: d["_id"])
    forbidden = {d["name_norm"] for d in listed} | {normalize_name(a) for d in listed for a in d["alt_names"]}
    listed_leis = {lei for d in listed for lei in d["leis"]}
    with_kids = [d for d in listed if any(children.get(l) for l in d["leis"])]
    others = [d for d in listed if d not in with_kids]
    rng.shuffle(with_kids)
    rng.shuffle(others)

    cases, labels = [], []

    def add(attack, name, country, lei, group, evidence, opaque=False):
        cid = f"c-{len(cases) + 1:03d}"
        cases.append(_case(cid, attack, name, country, lei, group, rng, opaque))
        labels.append({"case_id": cid, "expected": "approve" if attack == "clean" else "reject",
                       "reason": attack, "evidence": evidence})

    def usable(ents):
        return sorted((e for e in ents if e["_id"] not in listed_leis and normalize_name(e["display_name"]) not in forbidden),
                      key=lambda e: (not is_latin(e["display_name"]), e["_id"]))  # prefer demo-readable names

    n_indirect = 0
    for d in with_kids:
        parent_lei = next(l for l in d["leis"] if children.get(l))
        for kid in usable(children[parent_lei])[:2]:
            if n_indirect >= 24:
                break
            add("indirect_ownership", kid["display_name"], kid["country"], kid["_id"], d["_id"],
                {"listed_id": d["_id"], "path": [kid["_id"], parent_lei], "depth": 1}, _opaque(kid["display_name"], d))
            n_indirect += 1
            grand = usable(grandchildren.get(kid["_id"], []))
            if grand and n_indirect < 24:
                g = grand[0]
                add("indirect_ownership", g["display_name"], g["country"], g["_id"], d["_id"],
                    {"listed_id": d["_id"], "path": [g["_id"], kid["_id"], parent_lei], "depth": 2},
                    _opaque(g["display_name"], d))
                n_indirect += 1

    pool = [d for d in others if d["country"]]
    for d in pool[:10]:
        add("direct_listed", d["name"], d["country"], None, d["_id"], {"listed_id": d["_id"], "match": "exact"})
    for d in pool[10:24]:
        v = name_variants(d["name"], forbidden, rng)
        if v:
            add("name_variant", v[0], d["country"], None, d["_id"], {"listed_id": d["_id"], "original": d["name"]})

    by_country: dict = {}
    for e in sorted(clean, key=lambda e: e["_id"]):
        if e["_id"] not in listed_leis and normalize_name(e["display_name"]) not in forbidden:
            by_country.setdefault(e["country"], []).append(e)
    if clean_quota:  # explicit per-country counts, e.g. to match the country mix of the risky cases
        by_country = {c: v[: clean_quota.get(c, 0)] for c, v in by_country.items()}
    picked, i = [], 0
    while len(picked) < 28 and any(len(v) > i for v in by_country.values()):
        picked += [v[i] for _, v in sorted(by_country.items()) if len(v) > i][: 28 - len(picked)]
        i += 1
    for e in picked:  # round-robin so country is never a proxy for the label
        add("clean", e["display_name"], e["country"], e["_id"], None, {})

    _assign_splits(cases)
    return cases, labels
