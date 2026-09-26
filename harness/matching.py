from rapidfuzz import fuzz

from harness.data.normalize import normalize_name


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    return round(fuzz.token_sort_ratio(na, nb) / 100, 3)


def best_similarity(name: str, doc: dict) -> float:
    return max(name_similarity(name, n) for n in [doc["name"], *doc.get("alt_names", [])])
