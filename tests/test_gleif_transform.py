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


def test_unknown_lei_404_means_no_children(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request

    from harness.data.gleif import GleifClient

    def not_found(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", not_found)
    assert GleifClient(str(tmp_path), min_interval_s=0).direct_children("X" * 20) == []
