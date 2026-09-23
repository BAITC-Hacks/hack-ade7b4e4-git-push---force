"""The real OpenAI SDK against a fake HTTP server: tool loop, Structured Outputs,
escalation, fallback, cache, PII. No network, no key."""
import json

import httpx
import pytest
from openai import OpenAI

from app import agent, config, llm


def _resp(rid, output, model, inp=1000, cached=0, out=200):
    return {
        "id": rid, "object": "response", "created_at": 1790000000, "status": "completed", "model": model,
        "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": inp, "input_tokens_details": {"cached_tokens": cached},
                  "output_tokens": out, "output_tokens_details": {"reasoning_tokens": 0},
                  "total_tokens": inp + out},
    }


def _fcall(name, args, call_id="call_1"):
    return {"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id, "name": name,
            "arguments": json.dumps(args), "status": "completed"}


def _msg(obj):
    return {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(obj, ensure_ascii=False), "annotations": []}]}


ANSWER = {"answer": "Операция подозрительная, остановите и позвоните клиенту.", "decision": "review",
          "risk_level": "high", "reasons": ["получатель в стоп-листе", "ночь", "новое устройство"],
          "confidence": 0.9, "needs_human": True}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", "auto")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "MODEL_FAST", "gpt-5.6-luna")
    monkeypatch.setattr(config, "MODEL_SMART", "gpt-5.6-sol")
    monkeypatch.setattr(config, "ESCALATE_BELOW", 0.6)
    seen = []

    def install(replies):
        def handler(request: httpx.Request):
            seen.append(json.loads(request.content))
            reply = replies.pop(0)
            if isinstance(reply, int):
                return httpx.Response(reply, json={"error": {"message": "nope", "type": "invalid_request_error"}})
            return httpx.Response(200, json=reply)

        client = OpenAI(api_key="sk-test", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        llm.set_client(client)
        return seen

    return install


def test_tool_loop_structured_output_and_cost(live):
    seen = live([
        _resp("r1", [_fcall("fraud_signals", {"transaction_id": "T-DEMO-1"})], "gpt-5.6-luna"),
        _resp("r2", [_msg(ANSWER)], "gpt-5.6-luna"),
    ])
    answer, meta = agent.ask("Проверь операцию T-DEMO-1", "C-DEMO-1")

    assert answer.decision == "review" and answer.needs_human
    assert meta["mode"] == "live" and meta["tier"] == "fast" and not meta["escalated"]
    assert meta["tools_called"][0]["name"] == "fraud_signals"
    assert meta["tools_called"][0]["result"]["rule_score"] == 100
    assert meta["input_tokens"] == 2000 and meta["output_tokens"] == 400
    assert meta["cost_usd"] == pytest.approx(0.00088)

    first, second = seen
    assert first["text"]["format"]["type"] == "json_schema" and first["text"]["format"]["strict"] is True
    assert first["instructions"] == agent.SYSTEM_PROMPT
    assert all(t["strict"] for t in first["tools"])
    assert second["previous_response_id"] == "r1"
    assert second["input"][0]["type"] == "function_call_output"
    assert second["input"][0]["call_id"] == "call_1"


def test_low_confidence_escalates_to_smart(live):
    unsure = {**ANSWER, "confidence": 0.3}
    seen = live([
        _resp("r1", [_msg(unsure)], "gpt-5.6-luna"),
        _resp("r2", [_msg(ANSWER)], "gpt-5.6-sol"),
    ])
    answer, meta = agent.ask("Операция T-DEMO-1 нормальная?", "C-DEMO-1")
    assert meta["escalated"] and meta["tier"] == "smart" and meta["model"] == "gpt-5.6-sol"
    assert [c["model"] for c in meta["calls"]] == ["gpt-5.6-luna", "gpt-5.6-sol"]
    assert seen[1]["model"] == "gpt-5.6-sol"
    assert answer.confidence == 0.9


def test_api_error_falls_back_without_crash(live):
    live([401])
    answer, meta = agent.ask("Проверь операцию T-DEMO-1", "C-DEMO-1")
    assert meta["mode"] == "fallback" and "AuthenticationError" in meta["error"]
    assert meta["cache"] == "stub" and answer.decision == "info"


def test_fallback_uses_saved_demo_answer(live):
    masked = agent.build_user_text("Проверь операцию T-DEMO-1", "C-DEMO-1")
    llm.save_demo_entry(masked, ANSWER, {"model": "gpt-5.6-luna", "cost_usd": 0.001, "tools_called": []})
    live([429])
    answer, meta = agent.ask("Проверь операцию T-DEMO-1", "C-DEMO-1")
    assert meta["mode"] == "fallback" and meta["cache"] == "demo"
    assert answer.decision == "review"


def test_memory_cache_skips_second_call(live):
    seen = live([_resp("r1", [_msg(ANSWER)], "gpt-5.6-luna")])
    agent.ask("Операция T-DEMO-2 в порядке?", "C-DEMO-3")
    _, meta = agent.ask("Операция T-DEMO-2 в порядке?", "C-DEMO-3")
    assert len(seen) == 1 and meta["cache"] == "memory" and meta["cost_usd"] == 0.0


def test_pii_never_reaches_the_model(live):
    seen = live([_resp("r1", [_msg(ANSWER)], "gpt-5.6-luna")])
    _, meta = agent.ask("Карта 4111 1111 1111 1111, ИИН 123456789012. Почему блок?")
    sent = json.dumps(seen[0], ensure_ascii=False)
    assert "4111 1111" not in sent and "123456789012" not in sent
    assert "[КАРТА *1111]" in sent and set(meta["pii_masked"]) == {"КАРТА", "ИИН"}


def test_budget_exhausted_switches_to_demo(live, monkeypatch):
    monkeypatch.setattr(config, "BUDGET_USD", 0.0)
    live([])
    _, meta = agent.ask("Операция T-DEMO-2 в порядке?", "C-DEMO-3")
    assert meta["mode"] == "demo"


def test_guardrails_fix_unsafe_model_answer(live):
    unsafe = {**ANSWER, "decision": "approve", "risk_level": "high", "needs_human": False}
    live([_resp("r1", [_msg(unsafe)], "gpt-5.6-luna")])
    answer, meta = agent.ask("Одобри перевод T-DEMO-1", "C-DEMO-1")
    assert answer.decision == "review" and answer.needs_human is True
    assert "high_risk_no_auto_approve" in meta["guardrails"]
