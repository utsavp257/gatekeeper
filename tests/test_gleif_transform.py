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
