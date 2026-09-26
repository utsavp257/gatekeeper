from harness.data.normalize import is_latin, normalize_name


def test_strips_suffixes_and_punctuation():
    assert normalize_name('PJSC "LUKOIL"') == "LUKOIL"
    assert normalize_name("China Telecom Co., Ltd.") == "CHINA TELECOM"
    assert normalize_name("Acme  Trading  FZE") == "ACME TRADING"


def test_is_latin():
    assert is_latin("VTB Bank (PJSC)")
    assert not is_latin("Банк ВТБ")
