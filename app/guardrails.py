"""Safety invariants enforced in code after every model answer.

The prompt asks the model to follow these rules. This module guarantees them even
when the model does not (a "sensor", not just a "guide"). Every rule that changes an
answer is reported by name, so the UI, the logs and the evals show it.

When the answer schema changes for the case, update these rules and
tests/test_guardrails.py in the same unit.
"""
from __future__ import annotations

from typing import Any

RULE_TEXT = {
    "confidence_clamped": "уверенность приведена к диапазону 0..1",
    "high_risk_no_auto_approve": "высокий риск: автоодобрение запрещено, решение отправлено на проверку",
    "low_confidence_review": "низкая уверенность: автоодобрение запрещено, решение отправлено на проверку",
    "risky_decision_needs_human": "рискованное решение: обязательно подтверждение сотрудником",
}

LOW_CONFIDENCE = 0.5


def enforce(answer: Any) -> tuple[Any, list[str]]:
    """Fix the answer in place where it breaks a rule. Returns (answer, fired rule names)."""
    fired: list[str] = []

    conf = getattr(answer, "confidence", None)
    if isinstance(conf, (int, float)):
        clamped = min(1.0, max(0.0, float(conf)))
        if clamped != conf:
            answer.confidence = clamped
            fired.append("confidence_clamped")
        conf = clamped

    risk = getattr(answer, "risk_level", None)
    decision = getattr(answer, "decision", None)

    if decision == "approve" and risk == "high":
        answer.decision = decision = "review"
        fired.append("high_risk_no_auto_approve")

    if decision == "approve" and isinstance(conf, float) and conf < LOW_CONFIDENCE:
        answer.decision = decision = "review"
        fired.append("low_confidence_review")

    needs_human = getattr(answer, "needs_human", None)
    if needs_human is False and (risk == "high" or decision in ("decline", "review")):
        answer.needs_human = True
        fired.append("risky_decision_needs_human")

    # Keep the text consistent with the corrected decision: the user must never read
    # "можно одобрить" next to a "на проверку" badge.
    text = getattr(answer, "answer", None)
    if isinstance(text, str):
        notes = []
        if {"high_risk_no_auto_approve", "low_confidence_review"} & set(fired):
            notes.append("По правилам безопасности решение изменено: нужна проверка.")
        if "risky_decision_needs_human" in fired:
            notes.append("Действие выполняет только сотрудник после проверки.")
        if notes:
            answer.answer = (text.rstrip() + " " + " ".join(notes)).strip()

    return answer, fired
