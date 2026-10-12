"""
AutoInsight — LLM Client Factory  (reasoning-model aware)
==========================================================
Provider-agnostic wrapper over the OpenAI-compatible chat completions API.

Supported providers (set LLM_PROVIDER in .env):
    * groq       — https://api.groq.com/openai/v1    (default, free tier)
    * openai     — https://api.openai.com/v1
    * together   — https://api.together.xyz/v1

Reasoning models (openai/gpt-oss-*, qwen/qwen3-*, etc.) burn output tokens on
internal "thinking" before writing visible content. For Groq, we pass
`reasoning_effort="low"` to keep responses prompt and avoid empty outputs
when a token cap is set. We also raise max_tokens for these models so the
visible answer has room after the reasoning phase.

Models worth knowing on Groq (free tier):
    * llama-3.3-70b-versatile     — recommended default, no reasoning
    * llama-3.1-8b-instant        — fast + cheap, use for routing
    * openai/gpt-oss-20b          — reasoning model (needs effort flag)
    * openai/gpt-oss-120b         — larger reasoning model
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Provider endpoints
# ---------------------------------------------------------------------------
PROVIDER_BASE_URLS = {
    "groq":     "https://api.groq.com/openai/v1",
    "openai":   "https://api.openai.com/v1",
    "together": "https://api.together.xyz/v1",
}

DEFAULT_MODELS = {
    "groq":     "llama-3.3-70b-versatile",
    "openai":   "gpt-4o-mini",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
}

FAST_MODELS = {
    "groq":     "llama-3.1-8b-instant",
    "openai":   "gpt-4o-mini",
    "together": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
}

# Model-name substrings that identify reasoning models.
# These need `reasoning_effort` + larger token budgets to produce visible output.
_REASONING_MARKERS = ("gpt-oss", "qwen3", "deepseek-r1", "o1", "o3")


def _is_reasoning_model(model: str) -> bool:
    if not model:
        return False
    name = model.lower()
    return any(marker in name for marker in _REASONING_MARKERS)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class LLMConfig:
    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "groq").lower()
        self.api_key = os.environ.get("LLM_API_KEY") or os.environ.get(
            f"{self.provider.upper()}_API_KEY"
        )
        self.base_url = os.environ.get("LLM_BASE_URL") or PROVIDER_BASE_URLS.get(
            self.provider
        )
        self.model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(self.provider)
        self.fast_model = os.environ.get("LLM_FAST_MODEL") or FAST_MODELS.get(
            self.provider
        )
        # How much "thinking" to let reasoning models do: low / medium / high
        self.reasoning_effort = os.environ.get("LLM_REASONING_EFFORT", "low")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def __repr__(self) -> str:
        key_preview = (self.api_key[:7] + "...") if self.api_key else "None"
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"fast_model={self.fast_model!r}, key={key_preview})"
        )


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfig:
    return LLMConfig()


@lru_cache(maxsize=1)
def get_llm_client():
    """Return an OpenAI-compatible client, or None if LLM is unconfigured."""
    config = get_llm_config()
    if not config.is_configured():
        print(
            "[llm] LLM not configured — set LLM_PROVIDER, LLM_API_KEY, "
            "and (optionally) LLM_MODEL in .env. Falling back to stub mode."
        )
        return None

    try:
        from openai import OpenAI
    except ImportError:
        print("[llm] openai package not installed. Run: pip install openai")
        return None

    return OpenAI(api_key=config.api_key, base_url=config.base_url)


# ---------------------------------------------------------------------------
# chat() — the one function every agent calls
# ---------------------------------------------------------------------------
def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    fast: bool = False,
    max_tokens: int | None = None,
) -> str:
    """
    One-shot chat completion returning the assistant's content string.

    Reasoning-model handling:
      * passes `reasoning_effort` (configurable via LLM_REASONING_EFFORT)
      * when a token cap is set, raises it to leave headroom for both
        the thinking phase and the visible answer
    """
    client = get_llm_client()
    if client is None:
        return ""

    config = get_llm_config()
    chosen_model = model or (config.fast_model if fast else config.model)
    is_reasoning = _is_reasoning_model(chosen_model)

    kwargs: dict = {
        "model": chosen_model,
        "messages": messages,
        "temperature": temperature,
    }

    # Token budget — reasoning models need more headroom
    if max_tokens is not None:
        if is_reasoning:
            # Reserve space for internal reasoning + the actual answer
            kwargs["max_tokens"] = max(max_tokens * 4, 1500)
        else:
            kwargs["max_tokens"] = max_tokens

    # Reasoning effort — Groq's convention
    if is_reasoning and config.provider == "groq":
        kwargs["reasoning_effort"] = config.reasoning_effort

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""

    # If the reasoning model somehow returned empty, surface a readable error
    # instead of silent emptiness
    if not content and is_reasoning:
        print(
            f"[llm] Reasoning model {chosen_model!r} returned empty content. "
            "Try raising LLM_REASONING_EFFORT, or switch to a non-reasoning "
            "model like llama-3.3-70b-versatile."
        )

    return content


def is_llm_available() -> bool:
    return get_llm_client() is not None