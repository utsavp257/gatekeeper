from harness.matching import best_similarity, name_similarity


def test_exact_after_normalization():
    assert name_similarity("PJSC ROSBANK", "Rosbank") == 1.0


def test_variant_scores_high_but_below_exact():
    s = name_similarity("Gzprom Energo Ltd", "GAZPROM ENERGO, OOO")
    assert 0.8 < s < 1.0


def test_unrelated_scores_low():
    assert name_similarity("Clean Widgets GmbH", "BANK ROSSIYA") < 0.5


def test_best_similarity_uses_alt_names():
    doc = {"name": "JOINT STOCK COMPANY RUSSIAN AGRICULTURAL BANK", "alt_names": ["Rosselkhozbank"]}
    assert best_similarity("Rosselkhozbank LLC", doc) == 1.0
