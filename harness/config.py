import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongodb_db: str
    openrouter_api_key: str | None
    agent_model: str | None
    critic_model: str | None
    voyage_api_key: str | None
    tavily_api_key: str | None


def _opt(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key, "").strip()
    return value or None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ
    uri = _opt(env, "MONGODB_URI")
    if not uri:
        raise ConfigError("MONGODB_URI is not set. Copy .env.example to .env and paste your Atlas connection string.")
    return Settings(
        mongodb_uri=uri,
        mongodb_db=_opt(env, "MONGODB_DB") or "gatekeeper",
        openrouter_api_key=_opt(env, "OPENROUTER_API_KEY"),
        agent_model=_opt(env, "AGENT_MODEL"),
        critic_model=_opt(env, "CRITIC_MODEL"),
        voyage_api_key=_opt(env, "VOYAGE_API_KEY"),
        tavily_api_key=_opt(env, "TAVILY_API_KEY"),
    )
