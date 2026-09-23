from app.agent import AgentAnswer
from app.guardrails import enforce


def make(**kw):
    base = dict(answer="ok", decision="approve", risk_level="low", reasons=["r"], confidence=0.9, needs_human=False)
    base.update(kw)
    return AgentAnswer(**base)


def test_high_risk_cannot_be_auto_approved():
    a, fired = enforce(make(risk_level="high", answer="Можно одобрить."))
    assert a.decision == "review" and a.needs_human is True
    assert "high_risk_no_auto_approve" in fired and "risky_decision_needs_human" in fired
    assert "нужна проверка" in a.answer and a.answer.startswith("Можно одобрить.")


def test_decline_always_needs_human():
    a, fired = enforce(make(decision="decline", risk_level="medium"))
    assert a.needs_human is True and fired == ["risky_decision_needs_human"]


def test_low_confidence_goes_to_review():
    a, fired = enforce(make(confidence=0.3))
    assert a.decision == "review" and a.needs_human is True
    assert "low_confidence_review" in fired


def test_confidence_is_clamped():
    a, fired = enforce(make(confidence=1.7))
    assert a.confidence == 1.0 and "confidence_clamped" in fired


def test_safe_answer_is_untouched():
    a, fired = enforce(make())
    assert fired == [] and a.decision == "approve" and a.needs_human is False and a.answer == "ok"
