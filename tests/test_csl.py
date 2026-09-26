from harness.data.csl import parse_csl_row

ROW = {"_id": "30882", "source": "Non-SDN Chinese Military-Industrial Complex Companies List (CMIC) - Treasury Department",
       "type": "Entity", "programs": "CMIC-EO13959", "name": "China Telecom Corporation Limited",
       "addresses": "31 Jinrong Street, Beijing, 100033, CN; Hong Kong, HK", "alt_names": "CHINA TELECOM; CHINA TELECOM CORP LTD",
       "remarks": "", "ids": "Legal Entity Number, 5493001Q6RZ4XQJEXX91, CN"}


def test_parses_entity_row():
    d = parse_csl_row(ROW)
    assert d["_id"] == "csl-30882"
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
