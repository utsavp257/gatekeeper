"""Antibodies: learned, embedded signatures of injection attacks, applied deterministically to untrusted text
(request justifications and web content) before the model sees it."""
import hashlib
import math
import re

_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def chunks(text: str, max_len: int = 300) -> list[str]:
    out = []
    for part in _SENT.split(text or ""):
        part = part.strip()
        while len(part) > max_len:
            out.append(part[:max_len])
            part = part[max_len:]
        if part:
            out.append(part)
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def scan(text: str, antibodies: list[dict], embed) -> list[dict]:
    """Return one hit per chunk that matches an antibody at/above its threshold (best antibody wins)."""
    if not antibodies or not text:
        return []
    parts = chunks(text)
    hits = []
    for part, vec in zip(parts, embed(parts)):
        best = max(((ab, cosine(vec, ab["embedding"])) for ab in antibodies), key=lambda x: x[1])
        ab, score = best
        if score >= ab.get("similarity_threshold", 0.8):
            hits.append({"antibody_id": ab["id"], "score": round(score, 3), "chunk": part, "action": ab.get("action", "escalate")})
    return hits


def neutralize(text: str, hits: list[dict]) -> str:
    for h in hits:
        text = text.replace(h["chunk"], f"[removed by antibody {h['antibody_id']}: suspected instruction injection]")
    return text


def embed_cached(db, texts: list[str]) -> list[list[float]]:
    """Voyage embeddings with an Atlas-backed cache keyed by text hash."""
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    have = {d["_id"]: d["v"] for d in db.embed_cache.find({"_id": {"$in": keys}})}
    missing = [(k, t) for k, t in zip(keys, texts) if k not in have]
    if missing:
        import voyageai

        from harness.config import load_settings
        vecs = voyageai.Client(api_key=load_settings().voyage_api_key).embed(
            [t for _, t in missing], model="voyage-3.5-lite", input_type="document").embeddings
        for (k, _), v in zip(missing, vecs):
            have[k] = v
            db.embed_cache.update_one({"_id": k}, {"$set": {"v": v}}, upsert=True)
    return [have[k] for k in keys]
