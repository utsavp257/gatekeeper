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
