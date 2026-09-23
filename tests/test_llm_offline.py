"""LLM-шлюз app/llm.py против поддельного HTTP-сервера OpenAI: цикл инструментов, Structured Outputs,
эскалация на умную модель, откат при ошибке, кэш, маскировка персональных данных. Без сети и без ключа."""
import json

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel

from app import config, llm


class Answer(BaseModel):
    answer: str
    gids: list[str]
    confidence: float


class FakeTools:
    """Минимальный поставщик инструментов с тем же интерфейсом, что app.graph_store.GraphTools."""

    def __init__(self):
        self.calls = []

    def openai_tools(self, names=None):
        return [{"type": "function", "name": "get_node", "description": "узел по gid", "strict": True,
                 "parameters": {"type": "object", "properties": {"gid": {"type": "string"}},
                                "required": ["gid"], "additionalProperties": False}}]

    def call_tool(self, name, arguments):
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        self.calls.append((name, args))
        return {"id": args["gid"], "role": "consolidator", "in_deg": 9}


GOOD = {"answer": "Признаки консолидации: 9 плательщиков.", "gids": ["100000004015047100"], "confidence": 0.9}


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


def _stub(_text):
    return Answer(answer="LLM недоступен", gids=[], confidence=0.0)


def ask(text, tools, **kw):
    return llm.run_structured(instructions="Отвечай по графу.", user_text=text, schema=Answer, stub=_stub,
                              tools=["get_node"], tool_provider=tools, use_demo_cache=False, **kw)


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

        llm.set_client(OpenAI(api_key="sk-test", max_retries=0,
                              http_client=httpx.Client(transport=httpx.MockTransport(handler))))
        return seen

    return install


def test_tool_loop_structured_output_and_cost(live):
    tools = FakeTools()
    seen = live([
        _resp("r1", [_fcall("get_node", {"gid": "100000004015047100"})], "gpt-5.6-luna"),
        _resp("r2", [_msg(GOOD)], "gpt-5.6-luna"),
    ])
    answer, meta = ask("Что за узел 100000004015047100?", tools, force_tier="fast")
    assert answer.gids == ["100000004015047100"]
    assert tools.calls == [("get_node", {"gid": "100000004015047100"})]
    assert meta["tools_called"][0]["result"]["role"] == "consolidator"
    assert meta["input_tokens"] == 2000 and meta["output_tokens"] == 400
    assert meta["cost_usd"] == pytest.approx(0.00088)
    first, second = seen
    assert first["text"]["format"]["type"] == "json_schema" and first["text"]["format"]["strict"] is True
    assert all(t["strict"] for t in first["tools"])
    assert second["previous_response_id"] == "r1"
    assert second["input"][0]["type"] == "function_call_output"


def test_low_confidence_escalates_to_smart(live):
    seen = live([
        _resp("r1", [_msg({**GOOD, "confidence": 0.3})], "gpt-5.6-luna"),
        _resp("r2", [_msg(GOOD)], "gpt-5.6-sol"),
    ])
    answer, meta = ask("Кто собирает деньги?", FakeTools())
    assert meta["escalated"] and meta["tier"] == "smart" and meta["model"] == "gpt-5.6-sol"
    assert seen[1]["model"] == "gpt-5.6-sol" and answer.confidence == 0.9


def test_api_error_falls_back_without_crash(live):
    live([401])
    answer, meta = ask("Кто собирает деньги?", FakeTools())
    assert meta["mode"] == "fallback" and "AuthenticationError" in meta["error"]
    assert meta["cache"] == "stub" and answer.answer == "LLM недоступен"


def test_memory_cache_skips_second_call(live):
    seen = live([_resp("r1", [_msg(GOOD)], "gpt-5.6-luna")])
    ask("Кто главный в кластере 3?", FakeTools(), force_tier="fast")
    _, meta = ask("Кто главный в кластере 3?", FakeTools(), force_tier="fast")
    assert len(seen) == 1 and meta["cache"] == "memory" and meta["cost_usd"] == 0.0


def test_pii_masked_but_graph_gid_kept(live):
    seen = live([_resp("r1", [_msg(GOOD)], "gpt-5.6-luna")])
    ask("Карта 4111 1111 1111 1111, ИИН 123456789012, узел 100000004015047100", FakeTools(),
        force_tier="fast", protected_gids={"100000004015047100"})
    sent = json.dumps(seen[0], ensure_ascii=False)
    assert "4111 1111" not in sent and "123456789012" not in sent
    assert "100000004015047100" in sent


def test_budget_exhausted_switches_to_demo(live, monkeypatch):
    monkeypatch.setattr(config, "BUDGET_USD", 0.0)
    live([])
    _, meta = ask("Кто собирает деньги?", FakeTools())
    assert meta["mode"] == "demo"
