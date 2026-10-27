# Which chat model backs the classify, draft and verify Steps (ADR-0036).
# Chosen once at startup by LLM_PROVIDER; embeddings are not switchable here
# because stored vectors are tied to one embedding model (ADR-0026).

import os

from langchain_core.language_models import BaseChatModel
from ollama import ResponseError
from openai import APIError

DEFAULT_PROVIDER = "ollama"

# One model per provider for all three roles. JUDGE_MODEL can override the
# judge's (ADR-0035).
DEFAULT_MODELS = {
    "ollama": "qwen2.5:7b-instruct",
    "openai": "gpt-4o-mini",
}

# USD per million (input, output) tokens, as published by OpenAI; check their
# pricing page before trusting a total. Only local Ollama models cost 0, so the
# openai provider rejects a model missing here.
PRICES_PER_MILLION_TOKENS = {
    "gpt-4o-mini": (0.15, 0.60),
}

# What a failing model server raises, whichever provider is configured: Ollama
# aborting a run, or OpenAI refusing a key, a quota or a rate limit.
PROVIDER_ERRORS = (ResponseError, APIError)


def provider_from_env() -> str:
    provider = os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER
    if provider not in DEFAULT_MODELS:
        known = ", ".join(sorted(DEFAULT_MODELS))
        raise ValueError(f"unknown LLM_PROVIDER {provider!r}; expected one of: {known}")
    return provider


def build_chat_model(provider: str, model_name: str) -> BaseChatModel:
    # Imported here so only the chosen provider's package has to load.
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        # Checked here for a clear startup error; ChatOpenAI's own would only
        # surface from deep inside the first request.
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("LLM_PROVIDER=openai needs OPENAI_API_KEY to be set")
        # An unpriced model would record cost 0 on every Step.
        if model_name not in PRICES_PER_MILLION_TOKENS:
            priced = ", ".join(sorted(PRICES_PER_MILLION_TOKENS))
            raise ValueError(
                f"no price for OpenAI model {model_name!r}; add it to "
                f"PRICES_PER_MILLION_TOKENS (priced: {priced})"
            )
        return ChatOpenAI(model=model_name, temperature=0)
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model_name, temperature=0)


def cost_of(reply, model_name: str) -> float:
    prices = PRICES_PER_MILLION_TOKENS.get(model_name)
    usage = getattr(reply, "usage_metadata", None)
    if prices is None or not usage:
        return 0
    input_price, output_price = prices
    input_cost = usage["input_tokens"] * input_price
    output_cost = usage["output_tokens"] * output_price
    return (input_cost + output_cost) / 1_000_000
