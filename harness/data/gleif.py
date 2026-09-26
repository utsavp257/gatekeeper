import hashlib
import json
import time
import urllib.error
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
                if e.code == 404:  # LEI unknown to GLEIF (e.g. retired) — treat as empty
                    data = {"data": [], "meta": {"pagination": {"lastPage": 1}}}
                    break
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
