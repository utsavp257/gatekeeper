import pytest

from harness.scripts.seed_mock import check_target_db


def test_refuses_real_db_without_force():
    with pytest.raises(SystemExit):
        check_target_db("gatekeeper", force=False)


def test_allows_real_db_with_force():
    check_target_db("gatekeeper", force=True)


def test_allows_mock_db():
    check_target_db("gatekeeper_mock", force=False)
