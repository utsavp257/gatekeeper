from harness.policy import BASELINE_POLICY, depth_for, get_path, required_checks_for, set_path


def test_get_set_path_is_non_mutating():
    p2 = set_path(BASELINE_POLICY, "ownership.depth_by_country.AE", 3)
    assert get_path(p2, "ownership.depth_by_country.AE") == 3
    assert "AE" not in BASELINE_POLICY["ownership"]["depth_by_country"]


def test_required_checks_respect_when_amount():
    p = set_path(BASELINE_POLICY, "required_checks", [
        {"before_tool": "approve_vendor", "require": ["screen_name"]},
        {"before_tool": "approve_vendor", "require": ["web_research"], "when": {"amount_gt": 25000}}])
    small = {"request": {"amount_usd": 10000}, "vendor": {"country": "DE"}}
    big = {"request": {"amount_usd": 90000}, "vendor": {"country": "DE"}}
    assert required_checks_for(p, "approve_vendor", small) == ["screen_name"]
    assert required_checks_for(p, "approve_vendor", big) == ["screen_name", "web_research"]


def test_required_checks_when_country_in():
    p = set_path(BASELINE_POLICY, "required_checks", [
        {"before_tool": "approve_vendor", "require": ["check_ownership"], "when": {"country_in": ["CY", "AE"]}}])
    assert required_checks_for(p, "approve_vendor", {"request": {"amount_usd": 1}, "vendor": {"country": "CY"}}) == ["check_ownership"]
    assert required_checks_for(p, "approve_vendor", {"request": {"amount_usd": 1}, "vendor": {"country": "DE"}}) == []


def test_depth_for_country_override():
    p = set_path(BASELINE_POLICY, "ownership.depth_by_country.CY", 3)
    assert depth_for(p, "CY") == 3
    assert depth_for(p, "DE") == BASELINE_POLICY["ownership"]["default_depth"]
    assert depth_for(p, None) == BASELINE_POLICY["ownership"]["default_depth"]
