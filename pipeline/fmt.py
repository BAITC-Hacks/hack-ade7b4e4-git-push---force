"""Форматирование чисел для человекочитаемых обоснований."""
from __future__ import annotations

import math


def kzt(x: float) -> str:
    """1 095 690 ₸ или 3,85 млн ₸."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "0 ₸"
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.2f}".replace(".", ",") + " млн ₸"
    return f"{x:,.0f}".replace(",", " ") + " ₸"


def pct(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "н/д"
    return f"{x * 100:.0f}%"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def cut(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;") + "…"
