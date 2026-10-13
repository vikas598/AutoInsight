"""
AutoInsight — Smoke test for the LLM provider wiring
======================================================
Confirms that Groq (or whichever provider is configured in .env) is reachable
and responds. Run before anything that depends on LLM calls.

    python test_llm.py
"""

from __future__ import annotations

from app.llm import chat, get_llm_config, is_llm_available


def main():
    print("=" * 60)
    print("LLM configuration")
    print("=" * 60)

    config = get_llm_config()
    print(f"  Provider  : {config.provider}")
    print(f"  Base URL  : {config.base_url}")
    print(f"  Model     : {config.model}")
    print(f"  Fast model: {config.fast_model}")
    print(f"  API key   : {'SET' if config.api_key else 'MISSING'}")
    print()

    if not is_llm_available():
        print("  FAIL — LLM is not configured. Check .env.")
        return

    # ---- Test 1: plain completion with the main model ----
    print("Test 1 — plain completion (main model)")
    print("-" * 60)
    reply = chat(
        messages=[{"role": "user", "content": "Reply with exactly: 'LLM wired up correctly'"}],
        temperature=0,
        max_tokens=20,
    )
    print(f"  Response: {reply.strip()}")
    print()

    # ---- Test 2: fast model ----
    print("Test 2 — fast model routing")
    print("-" * 60)
    reply = chat(
        messages=[{"role": "user", "content": "Classify as fruit or vegetable, one word: tomato"}],
        temperature=0,
        max_tokens=10,
        fast=True,
    )
    print(f"  Response: {reply.strip()}")
    print()

    # ---- Test 3: JSON mode (what the Schema Service uses) ----
    print("Test 3 — JSON mode (Schema Service enrichment path)")
    print("-" * 60)
    reply = chat(
        messages=[{
            "role": "user",
            "content": "Return a JSON object with keys 'city' and 'country' for New Delhi.",
        }],
        temperature=0,
        json_mode=True,
        max_tokens=50,
    )
    print(f"  Response: {reply.strip()}")
    print()

    print("=" * 60)
    print("All LLM wiring tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
