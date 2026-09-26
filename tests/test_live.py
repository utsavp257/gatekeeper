from harness.live import champion_from_change


def test_promotion_update_yields_new_champion():
    ev = {"operationType": "update", "fullDocument": {"_id": "g-0007", "status": "champion", "policy": {}},
          "updateDescription": {"updatedFields": {"status": "champion"}}}
    assert champion_from_change(ev, current_id="g-0004")["_id"] == "g-0007"


def test_ignores_non_champion_and_same_champion():
    rej = {"operationType": "update", "fullDocument": {"_id": "g-0008", "status": "rejected"},
           "updateDescription": {"updatedFields": {"status": "rejected"}}}
    assert champion_from_change(rej, current_id="g-0004") is None
    same = {"operationType": "update", "fullDocument": {"_id": "g-0004", "status": "champion"},
            "updateDescription": {"updatedFields": {"scores.train": {}}}}
    assert champion_from_change(same, current_id="g-0004") is None
