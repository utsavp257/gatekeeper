import pytest
from harness.config import load_settings, ConfigError


def test_missing_uri_raises_named_error():
    with pytest.raises(ConfigError, match="MONGODB_URI"):
        load_settings({})


def test_blank_uri_raises_named_error():
    with pytest.raises(ConfigError, match="MONGODB_URI"):
        load_settings({"MONGODB_URI": "   "})


def test_defaults_db_to_gatekeeper():
    s = load_settings({"MONGODB_URI": "mongodb://localhost"})
    assert s.mongodb_db == "gatekeeper"
    assert s.tavily_api_key is None


def test_reads_optional_keys():
    s = load_settings({"MONGODB_URI": "mongodb://x", "MONGODB_DB": "gatekeeper_mock", "TAVILY_API_KEY": "t"})
    assert s.mongodb_db == "gatekeeper_mock"
    assert s.tavily_api_key == "t"
