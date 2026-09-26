"""Genome policy helpers. The policy is structured data the enforcer applies — never prompt text."""
import copy

BASELINE_POLICY = {
    "screening": {"fuzzy_max_edits": 0, "min_score": 0.95, "fields": ["name", "alt_names"], "lists": ["ALL"]},
    "ownership": {"default_depth": 1, "depth_by_country": {}, "block_if_listed_ancestor_within": 1},
    "required_checks": [{"before_tool": "approve_vendor", "require": ["screen_name"]}],
    "web": {"sanitize": [], "treat_as_untrusted": False},
    "antibodies": [],
}


def get_path(doc: dict, path: str):
    for key in path.split("."):
        if not isinstance(doc, dict) or key not in doc:
            return None
        doc = doc[key]
    return doc


def set_path(doc: dict, path: str, value) -> dict:
    out = copy.deepcopy(doc)
    cur = out
    keys = path.split(".")
    for key in keys[:-1]:
        cur = cur.setdefault(key, {})
    cur[keys[-1]] = value
    return out


def _applies(when: dict | None, case: dict) -> bool:
    if not when:
        return True
    if "amount_gt" in when and not case["request"]["amount_usd"] > when["amount_gt"]:
        return False
    if "country_in" in when and case["vendor"].get("country") not in when["country_in"]:
        return False
    return True


def required_checks_for(policy: dict, tool: str, case: dict) -> list[str]:
    out: list[str] = []
    for rule in policy.get("required_checks", []):
        if rule["before_tool"] == tool and _applies(rule.get("when"), case):
            out += [c for c in rule["require"] if c not in out]
    return out


def depth_for(policy: dict, country: str | None) -> int:
    own = policy["ownership"]
    return own["depth_by_country"].get(country, own["default_depth"]) if country else own["default_depth"]
