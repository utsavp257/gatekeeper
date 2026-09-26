from harness.tools import rank_screening_hits


def test_exact_listed_entry_ranks_first_among_common_token_noise():
    noise = [{"_id": f"csl-SDN-{i}", "name": f"PUBLIC JOINT STOCK COMMERCIAL BANK FILLER{i}", "alt_names": [],
              "source_list": "SDN"} for i in range(30)]
    target = {"_id": "csl-SDN-51839", "name": "PUBLIC JOINT STOCK COMMERCIAL BANK DERZHAVA", "alt_names": ["BANK DERZHAVA"],
              "source_list": "SDN"}
    ranked = rank_screening_hits("PUBLIC JOINT STOCK COMMERCIAL BANK DERZHAVA", noise + [target])
    assert ranked[0]["id"] == "csl-SDN-51839" and ranked[0]["similarity"] == 1.0
    assert len(ranked) <= 5
