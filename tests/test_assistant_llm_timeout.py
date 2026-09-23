"""Bounded LLM waiting with a fake clock and HTTP transport: no network or sleeps."""
from __future__ import annotations

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


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Tools:
    def __init__(self, clock, delay=0):
        self.clock = clock
        self.delay = delay

    def openai_tools(self, names=None):
        return [{"type": "function", "name": "get_node", "description": "Graph node", "strict": True,
                 "parameters": {"type": "object", "properties": {"gid": {"type": "string"}},
                                "required": ["gid"], "additionalProperties": False}}]

    def call_tool(self, name, arguments):
        self.clock.advance(self.delay)
        return {"id": json.loads(arguments)["gid"], "in_deg": 3}


def _response(output, response_id="response_test"):
    return {"id": response_id, "object": "response", "created_at": 1790000000, "status": "completed",
            "model": config.MODEL_FAST, "output": output, "parallel_tool_calls": True,
            "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens": 20, "output_tokens_details": {"reasoning_tokens": 0},
                      "total_tokens": 120}}


def _message(confidence=.9):
    return {"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "annotations": [], "text": json.dumps({
                "answer": "Ответ из инструментов", "gids": ["node-a"], "confidence": confidence})}]}


def _tool_call():
    return {"type": "function_call", "id": "fc_test", "call_id": "call_test", "name": "get_node",
            "arguments": json.dumps({"gid": "node-a"}), "status": "completed"}


@pytest.fixture
def bounded_live(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(llm.time, "perf_counter", clock)
    monkeypatch.setattr(config, "DEMO_MODE", "auto")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-offline-test")
    monkeypatch.setattr(config, "OPENAI_TOTAL_TIMEOUT", 18.0)
    monkeypatch.setattr(config, "OPENAI_TIMEOUT", 45.0)
    monkeypatch.setattr(config, "ESCALATE_BELOW", .6)

    def reject_network(*args, **kwargs):
        pytest.fail("Timeout tests must not use the network")

    def reject_sleep(*args, **kwargs):
        pytest.fail("Timeout tests must not sleep or retry")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(llm.time, "sleep", reject_sleep)
    requests = []

    def install(replies):
        queue = list(replies)

        def handle(request):
            requests.append(request)
            if not queue:
                pytest.fail("Unexpected retry or model call after the request budget")
            elapsed, reply = queue.pop(0)
            clock.advance(elapsed)
            if reply == "timeout":
                raise httpx.ReadTimeout("Simulated upstream timeout", request=request)
            if isinstance(reply, int):
                return httpx.Response(reply, json={"error": {"message": "Offline simulated failure",
                                                            "type": "api_error"}})
            return httpx.Response(200, json=reply)

        # Deliberately enable retries on the base client: the gateway must turn
        # them off on every request, including injected or pre-existing clients.
        llm.set_client(OpenAI(api_key="sk-offline-test", max_retries=2,
                             http_client=httpx.Client(transport=httpx.MockTransport(handle))))
        return clock, requests

    return install


def _ask(clock, *, delay=0, force_tier="fast"):
    return llm.run_structured(
        instructions="Отвечай по инструментам.", user_text="Покажи узел", schema=Answer,
        stub=lambda _: Answer(answer="Резервный ответ", gids=[], confidence=0),
        tools=["get_node"], tool_provider=Tools(clock, delay), force_tier=force_tier,
        use_cache=False, use_demo_cache=False,
    )


def _timeout(request):
    options = request.extensions["timeout"]
    assert len(set(options.values())) == 1
    return options["read"]


@pytest.mark.parametrize("failure", ["timeout", 500, 429])
def test_upstream_failure_falls_back_without_retry(bounded_live, failure):
    clock, requests = bounded_live([(0, failure)])
    answer, meta = _ask(clock)
    assert answer.answer == "Резервный ответ"
    assert meta["mode"] == "fallback" and meta["cache"] == "stub"
    assert len(requests) == 1
    assert _timeout(requests[0]) == pytest.approx(18.0)


def test_each_request_keeps_smaller_configured_timeout(bounded_live, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_TIMEOUT", 4.0)
    clock, requests = bounded_live([(0, _response([_message()]))])
    answer, meta = _ask(clock)
    assert meta["mode"] == "live" and answer.confidence == .9
    assert _timeout(requests[0]) == pytest.approx(4.0)


def test_tool_rounds_share_remaining_time_budget(bounded_live):
    clock, requests = bounded_live([
        (7, _response([_tool_call()], "tool_response")),
        (6, _response([_message()])),
    ])
    answer, meta = _ask(clock)
    assert answer.answer == "Ответ из инструментов" and meta["mode"] == "live"
    assert [_timeout(request) for request in requests] == pytest.approx([18, 11])
    assert json.loads(requests[1].content)["previous_response_id"] == "tool_response"


def test_escalation_spends_same_budget_as_fast_tier(bounded_live):
    clock, requests = bounded_live([
        (13, _response([_message(.3)])),
        (2, _response([_message()])),
    ])
    answer, meta = _ask(clock, force_tier=None)
    assert answer.confidence == .9 and meta["escalated"]
    assert [_timeout(request) for request in requests] == pytest.approx([18, 5])
    assert json.loads(requests[1].content)["model"] == config.MODEL_SMART


def test_no_next_round_when_tool_work_exhausts_budget(bounded_live):
    clock, requests = bounded_live([(2, _response([_tool_call()]))])
    answer, meta = _ask(clock, delay=17)
    assert answer.answer == "Резервный ответ"
    assert meta["mode"] == "fallback" and "TimeoutError" in meta["error"]
    assert len(requests) == 1


def test_late_response_falls_back_without_escalating(bounded_live):
    clock, requests = bounded_live([(19, _response([_message(.3)]))])
    answer, meta = _ask(clock, force_tier=None)
    assert answer.answer == "Резервный ответ"
    assert meta["mode"] == "fallback" and "TimeoutError" in meta["error"]
    assert len(requests) == 1 and not meta["escalated"]
