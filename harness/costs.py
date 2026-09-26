# USD per token (OpenRouter list prices, Sept 2026). Unknown models fall back to a conservative default.
PRICES = {"qwen/qwen3-235b-a22b-2507": (0.09e-6, 0.35e-6), "openai/gpt-oss-120b": (0.03e-6, 0.14e-6)}
DEFAULT = (1e-6, 4e-6)
TAVILY_SEARCH_USD = 0.008


def tokens_cost(model_id: str, usage: dict) -> float:
    pin, pout = PRICES.get(model_id, DEFAULT)
    return usage.get("inputTokens", 0) * pin + usage.get("outputTokens", 0) * pout
