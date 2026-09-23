"""Pick a model tier for a request. Cheap first, strong only when needed.

Same idea as Yandex Alice routing: most requests go to the fast model, complex
ones go to the strong model, and a low-confidence fast answer is escalated.
The reason is returned so the UI and the pitch can show it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SIMPLE_TASKS = {"classify", "extract", "summarize_short"}

COMPLEX_MARKERS = [
    # ru
    "почему", "объясни", "сравни", "рассчитай", "посчитай", "план", "стратеги",
    "оцени", "проанализируй", "шаг за шагом", "что будет если", "варианты", "риск",
    # kk
    "неге", "түсіндір", "салыстыр", "есепте", "талда", "жоспар", "бағала",
]


@dataclass
class Route:
    tier: str  # "fast" | "smart"
    reason: str
    score: int


def choose_tier(task: str, text: str) -> Route:
    if task in SIMPLE_TASKS:
        return Route("fast", f"простая задача ({task})", 0)

    lowered = text.lower()
    reasons: list[str] = []
    score = 0

    markers = [m for m in COMPLEX_MARKERS if m in lowered]
    if markers:
        score += min(2, len(markers))
        reasons.append("маркеры сложности: " + ", ".join(markers[:3]))
    numbers = re.findall(r"\d[\d\s.,]*", text)
    if len(numbers) >= 3:
        score += 1
        reasons.append(f"{len(numbers)} чисел")
    if text.count("?") >= 2:
        score += 1
        reasons.append("несколько вопросов")
    if len(text) > 500:
        score += 1
        reasons.append("длинный запрос")

    if score >= 2:
        return Route("smart", "; ".join(reasons), score)
    return Route("fast", "; ".join(reasons) or "короткий простой запрос", score)
