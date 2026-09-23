"""All settings come from environment variables.

Locally they are read from `.env` (copy `.env.example`). On Vercel set them in
Project Settings -> Environment Variables. Nothing secret lives in code.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
LOG_DIR = ROOT / "logs"

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL")  # leave empty unless organizers give a custom endpoint

# Two tiers. Check the real model names on the day: python scripts/check_key.py
MODEL_FAST = _env("MODEL_FAST", "gpt-5.6-luna")
MODEL_SMART = _env("MODEL_SMART", "gpt-5.6-sol")

# Reasoning effort is sent only when set (e.g. "low", "medium", "high").
REASONING_FAST = _env("REASONING_FAST")
REASONING_SMART = _env("REASONING_SMART")

MAX_OUTPUT_TOKENS_FAST = int(_env("MAX_OUTPUT_TOKENS_FAST", "3000"))
MAX_OUTPUT_TOKENS_SMART = int(_env("MAX_OUTPUT_TOKENS_SMART", "8000"))
MAX_TOOL_ROUNDS = int(_env("MAX_TOOL_ROUNDS", "4"))
OPENAI_TIMEOUT = float(_env("OPENAI_TIMEOUT", "45"))

# A fast-tier answer with confidence below this is re-asked on the smart tier.
ESCALATE_BELOW = float(_env("ESCALATE_BELOW", "0.6"))

# Spending cap for this process. After it the app answers from the demo cache.
BUDGET_USD = float(_env("BUDGET_USD", "5"))

# National Bank rate on the day (tenge per 1 USD). 0 hides tenge in the UI.
USD_KZT = float(_env("USD_KZT", "0"))

# auto: live if a key is set, demo otherwise. on: always demo. off: always live.
DEMO_MODE = _env("DEMO_MODE", "auto").lower()

# Requests per minute per IP for /api/ask (protects the budget on a public link).
RATE_LIMIT_PER_MIN = int(_env("RATE_LIMIT_PER_MIN", "20"))

APP_TITLE = _env("APP_TITLE", "Fintech AI Agent")

# USD per 1M tokens: (input, cached input, output).
# Source: developers.openai.com/api/docs/pricing, checked 21.09.2026.
# gpt-5.6-sol is on promo pricing until 21.11.2026.
PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
}


def price_for(model: str) -> tuple[float, float, float] | None:
    """Exact match first, then the longest known prefix (dated snapshots)."""
    if model in PRICES:
        return PRICES[model]
    matches = [name for name in PRICES if model.startswith(name)]
    if matches:
        return PRICES[max(matches, key=len)]
    return None
