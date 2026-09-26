from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError

from harness.config import ConfigError, Settings, load_settings


@lru_cache(maxsize=4)
def _client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=8000, appname="gatekeeper-harness")


def get_db(settings: Settings | None = None) -> Database:
    settings = settings or load_settings()
    return _client(settings.mongodb_uri)[settings.mongodb_db]


def ping(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    try:
        _client(settings.mongodb_uri).admin.command("ping")
    except OperationFailure as e:
        raise ConfigError(f"Atlas rejected the credentials ({e.code}). Check Security → Database Access user/password in the URI.") from e
    except ServerSelectionTimeoutError as e:
        raise ConfigError("Could not reach Atlas within 8s. Check Security → Network Access allows your IP (or 0.0.0.0/0).") from e
    except ConfigurationError as e:
        raise ConfigError(f"MONGODB_URI looks malformed: {e}") from e
