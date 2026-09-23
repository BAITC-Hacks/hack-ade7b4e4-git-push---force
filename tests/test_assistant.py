"""Contract-sized graph and an in-process API: no network, key, or server."""
from __future__ import annotations

import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

from app import assistant, config, llm
from app.graph_store import GraphStore, GraphTools
from app.main import create_app


# This graph identifier also passes Luhn: PII masking must preserve known gids.
A = "100000003684369103"
B = "100000003037660100"
RECEIVER = "100000001234567890"
PARTIAL = "100000009876543210"
BOUNDARY = "100000002222222222"
ISOLATED = "100000003333333333"
UNKNOWN = "100000009999999999"


@pytest.fixture
def graph():
    """Every field follows docs/CONTRACT.md; metrics match the directed edges."""
    edges = [
        {"source": A, "target": RECEIVER, "sum_kzt": 100.0, "n_tx": 2, "depth": 1},
        {"source": B, "target": RECEIVER, "sum_kzt": 200.0, "n_tx": 4, "depth": 1},
        {"source": A, "target": PARTIAL, "sum_kzt": 70.0, "n_tx": 3, "depth": 1},
        {"source": RECEIVER, "target": BOUNDARY, "sum_kzt": 250.0, "n_tx": 5, "depth": 4},
        {"source": BOUNDARY, "target": A, "sum_kzt": 40.0, "n_tx": 6, "depth": 4},
        {"source": PARTIAL, "target": B, "sum_kzt": 10.0, "n_tx": 1, "depth": 2},
    ]
    nodes = []
    specs = [
        (A, "transit", .8, ["cycle"], True),
        (B, "transit", .7, [], True),
        (RECEIVER, "consolidator", .95, ["sync_inflow"], False),
        (PARTIAL, "transit", .5, [], False),
        (BOUNDARY, "transit", .4, ["cutoff_depth4"], False),
        (ISOLATED, "isolated", .1, ["isolated_seed"], True),
    ]
    for index, (gid, role, priority, flags, seed) in enumerate(specs):
        incoming = [edge for edge in edges if edge["target"] == gid]
        outgoing = [edge for edge in edges if edge["source"] == gid]
        in_kzt = sum(edge["sum_kzt"] for edge in incoming)
        out_kzt = sum(edge["sum_kzt"] for edge in outgoing)
        nodes.append({
            "id": gid, "role": role, "role_score": priority, "cluster_id": 9 if gid == ISOLATED else 7,
            "priority_score": priority, "rank": 1 if gid == RECEIVER else None,
            "is_seed": seed, "depth": 0 if seed else 4 if gid == BOUNDARY else 1,
            "in_deg": len(incoming), "out_deg": len(outgoing),
            "in_kzt": in_kzt, "out_kzt": out_kzt,
            "in_tx": sum(edge["n_tx"] for edge in incoming),
            "out_tx": sum(edge["n_tx"] for edge in outgoing),
            "pass_through": out_kzt / in_kzt if in_kzt else 0.0,
            "seeds_upstream": 2 if gid == RECEIVER else 0,
            "evidence": "Входящих связей: %s; исходящих: %s" % (len(incoming), len(outgoing)),
            "why": "Два источника, входящий поток 300 KZT" if gid == RECEIVER else "",
            "flags": flags, "x": float(index), "y": 0.0,
        })
    return {
        "meta": {"generated_at": "2026-09-23T14:00:00", "n_nodes": 6, "n_edges": 6,
                 "n_tx": 21, "n_seed": 3, "period": "2026-07-01..2026-07-31", "turnover_kzt": 670.0},
        "roles": [{"key": role, "label": label, "color": color, "rule": "Проверить структуру потоков"}
                  for role, label, color in [("transit", "Транзит", "#123456"),
                                            ("consolidator", "Точка консолидации", "#d62728"),
                                            ("isolated", "Изолированный узел", "#aaaaaa")]],
        "nodes": nodes, "edges": edges,
        "clusters": [{"cluster_id": 7, "n_nodes": 5, "n_seed": 2, "sum_kzt_internal": 670.0,
                      "top_gids": [RECEIVER], "hypothesis": "Проверить консолидацию переводов"},
                     {"cluster_id": 9, "n_nodes": 1, "n_seed": 1, "sum_kzt_internal": 0.0,
                      "top_gids": [], "hypothesis": "Недостаточно наблюдаемых связей"}],
        "top": [{"rank": 1, "gid": RECEIVER, "role": "consolidator", "priority_score": .95,
                 "why": "Два источника, входящий поток 300 KZT"}],
    }


@pytest.fixture
def store(graph):
    return GraphStore(graph)


@pytest.fixture
def graph_path(graph, tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def refuse_network(monkeypatch):
    """An accidental SDK client or normal HTTP request must fail the test."""
    def reject(*args, **kwargs):
        raise AssertionError("The assistant tests must not use the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject)


def test_file_loading_uses_graph_json_and_preserves_long_string_ids(graph_path, monkeypatch):
    monkeypatch.setenv("GRAPH_JSON", str(graph_path))
    loaded = GraphStore.from_file()
    assert loaded.get_node(A)["id"] == A
    assert set(loaded.nodes) == {A, B, RECEIVER, PARTIAL, BOUNDARY, ISOLATED}
    assert all(isinstance(gid, str) for gid in loaded.nodes)


def test_missing_graph_file_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPH_JSON", str(tmp_path / "not-ready.json"))
    with pytest.raises(FileNotFoundError):
        GraphStore.from_file()


def test_neighbors_obey_direction_and_limit(store):
    incoming = store.neighbors(RECEIVER, "in", 10)
    assert {edge["source"] for edge in incoming["incoming"]} == {A, B}
    assert incoming["outgoing"] == []
    outgoing = store.neighbors(RECEIVER, "out", 10)
    assert [edge["target"] for edge in outgoing["outgoing"]] == [BOUNDARY]
    assert outgoing["incoming"] == []
    limited = store.neighbors(RECEIVER, "both", 1)
    assert len(limited["incoming"]) + len(limited["outgoing"]) == 1
    assert limited["count"] == 3 and limited["truncated"]
    assert store.neighbors(UNKNOWN, "both", 5).get("error")


def test_rank_role_cluster_and_flag_filters(store):
    assert [node["id"] for node in store.top_nodes(2)["nodes"]] == [RECEIVER, A]
    assert [node["id"] for node in store.top_nodes(5, role="consolidator", cluster_id=7)["nodes"]] == [RECEIVER]
    assert store.top_nodes(5, role="consolidator", cluster_id=9)["nodes"] == []
    assert [node["id"] for node in store.search(role="transit", cluster_id=7, flag="cutoff_depth4")["nodes"]] == [BOUNDARY]
    cluster = store.cluster_info(9)
    assert cluster["cluster"]["n_seed"] == 1
    assert [node["id"] for node in cluster["nodes"]] == [ISOLATED]


def test_common_receivers_require_all_sources_and_sum_only_their_edges(store):
    result = store.common_receivers([A, B])
    assert [row["gid"] for row in result["receivers"]] == [RECEIVER]
    receiver = result["receivers"][0]
    assert receiver["sum_kzt"] == 300.0 and receiver["n_tx"] == 6
    assert {row["gid"] for row in receiver["sources"]} == {A, B}
    assert store.common_receivers([A, A, B])["receivers"] == result["receivers"]
    assert store.common_receivers([A, ISOLATED])["receivers"] == []
    assert store.common_receivers([A, UNKNOWN]).get("error")
    assert store.common_receivers([]).get("error")


def test_paths_are_directed_simple_and_bounded(store):
    assert [path["gids"] for path in store.paths(A, BOUNDARY, max_len=2)["paths"]] == [[A, RECEIVER, BOUNDARY]]
    assert store.paths(A, BOUNDARY, max_len=1)["paths"] == []
    assert store.paths(BOUNDARY, RECEIVER, max_len=1)["paths"] == []
    for path in store.paths(A, BOUNDARY, max_len=4)["paths"]:
        assert len(path["gids"]) == len(set(path["gids"]))
        assert len(path["edges"]) <= 4
        assert [(edge["source"], edge["target"]) for edge in path["edges"]] == list(zip(path["gids"], path["gids"][1:]))
    assert store.paths(A, UNKNOWN).get("error")
    assert store.paths(A, BOUNDARY, max_len=100).get("error")


def test_tool_audit_uses_returned_graph_fields_only(graph):
    # Even an existing graph gid mentioned in descriptive text is not evidence.
    graph["nodes"][0]["evidence"] = f"Текст с чужим идентификатором {B} и {UNKNOWN}"
    tools = GraphTools(GraphStore(graph))
    tools.call_tool("get_node", json.dumps({"gid": A, "unused": B}))
    # Unknown arguments can be rejected; the ordinary valid call still works.
    tools.call_tool("get_node", json.dumps({"gid": A}))
    assert tools.observed_gids == {A}
    tools.call_tool("get_node", json.dumps({"gid": UNKNOWN}))
    tools.call_tool("not_a_tool", json.dumps({"gid": B}))
    tools.call_tool("get_node", "not json")
    assert tools.observed_gids == {A}
    assert any(call["name"] == "get_node" and call["result"].get("error") for call in tools.calls)
    assert GraphTools(GraphStore(graph)).observed_gids == set()


def test_gid_guard_checks_text_list_and_link_targets(store):
    draft = assistant.AssistantAnswer(
        answer=f"Проверить [{A}](/viewer#gid={A}), [{B}](/viewer#gid={B}) и [{UNKNOWN}](/viewer#gid={UNKNOWN}).",
        gids=[A, A, B, UNKNOWN], confidence=.9,
    )
    clean, removed = assistant.enforce_gids(draft, store, {A, UNKNOWN})
    assert clean.gids == [A]
    assert A in clean.answer and f"/viewer#gid={A}" in clean.answer
    assert B not in clean.answer and UNKNOWN not in clean.answer
    assert set(removed) == {B, UNKNOWN}
    assert clean.answer != f"Проверить [{A}](/viewer#gid={A}), [](/viewer#gid=) и [](/viewer#gid=)."


def test_gid_guard_catches_hallucinations_absent_from_declared_list(store):
    draft = assistant.AssistantAnswer(answer=f"Гипотеза: перевод от {B} к {UNKNOWN}.", gids=[], confidence=.8)
    clean, removed = assistant.enforce_gids(draft, store, set())
    assert clean.gids == [] and B not in clean.answer and UNKNOWN not in clean.answer
    assert set(removed) == {B, UNKNOWN}


def test_gid_guard_checks_hidden_link_destination(store):
    draft = assistant.AssistantAnswer(answer=f"Проверить [узел](/viewer#gid={B}).", gids=[], confidence=.8)
    clean, removed = assistant.enforce_gids(draft, store, {A})
    assert B not in clean.answer and clean.gids == []
    assert removed == [B]


@pytest.mark.parametrize("prefix", ["gid-", "узел"])
def test_gid_guard_removes_numeric_reference_touching_prefix(store, prefix):
    draft = assistant.AssistantAnswer(answer=f"Проверить {prefix}{UNKNOWN}.", gids=[], confidence=.8)
    clean, removed = assistant.enforce_gids(draft, store, set())
    assert UNKNOWN not in clean.answer and clean.gids == []
    assert removed == [UNKNOWN]


@pytest.mark.parametrize("text", ["Узел 123456789", "gid 123456789"])
def test_gid_guard_removes_short_explicit_node_identifier(store, text):
    draft = assistant.AssistantAnswer(answer=text, gids=[], confidence=.8)
    clean, removed = assistant.enforce_gids(draft, store, set())
    assert "123456789" not in clean.answer and clean.gids == []
    assert removed == ["123456789"]


def test_without_key_common_receiver_rule_uses_graph(store, monkeypatch):
    monkeypatch.setattr(llm, "get_client", lambda: pytest.fail("No-key rule called the LLM"))
    answer, meta = assistant.ask(f"Кто собирает деньги с {A}, {B}?", store=store)
    assert RECEIVER in answer.gids and RECEIVER in answer.answer
    assert PARTIAL not in answer.gids and PARTIAL not in answer.answer
    # The frontend turns verified gids into links without trusting model HTML.
    assert assistant.viewer_url(RECEIVER) == f"/viewer#gid={RECEIVER}"
    assert "300" in answer.answer
    assert any(call["name"] == "common_receivers" for call in meta["tools_called"])
    assert all(gid in store.nodes for gid in answer.gids)


def test_without_key_card_and_other_questions_are_safe(store, monkeypatch):
    # Even explicitly selecting live mode cannot authorize a request without a key.
    monkeypatch.setattr(config, "DEMO_MODE", "off")
    monkeypatch.setattr(llm, "get_client", lambda: pytest.fail("No-key answer called the LLM"))
    answer, _ = assistant.ask(f"Карточка {RECEIVER}", store=store)
    assert RECEIVER in answer.gids and "300" in answer.answer
    assert assistant.get_card(RECEIVER, store)["viewer_url"] == f"/viewer#gid={RECEIVER}"
    disabled, _ = assistant.ask("Сравни гипотезы по всей сети", store=store)
    assert "llm" in disabled.answer.lower() and disabled.gids == []
    missing, _ = assistant.ask(f"Карточка {UNKNOWN}", store=store)
    assert missing.gids == [] and UNKNOWN not in missing.answer


def test_no_key_rule_rejects_unknown_source_instead_of_partial_intersection(store):
    answer, _ = assistant.ask(f"Кто собирает деньги с {A}, {UNKNOWN}?", store=store)
    assert RECEIVER not in answer.gids and RECEIVER not in answer.answer
    assert UNKNOWN not in answer.gids and UNKNOWN not in answer.answer


def test_card_explains_isolated_seed_and_depth_cutoff(store):
    isolated = assistant.get_card(ISOLATED, store)["attention"]
    boundary = assistant.get_card(BOUNDARY, store)["attention"]
    assert any("изолир" in text.lower() or "нет связ" in text.lower() for text in isolated)
    assert any("4" in text and any(word in text.lower() for word in ("границ", "глубин", "непол", "обрез", "обрыв"))
               for text in boundary)


def test_card_contains_role_flow_connections_and_viewer_link(store):
    card = assistant.get_card(RECEIVER, store)
    assert card["gid"] == RECEIVER
    assert card["role"]["key"] == "consolidator"
    assert card["role"]["label"] == "Точка консолидации"
    assert card["role"]["evidence"]
    assert card["flows"] == {"in_kzt": 300.0, "out_kzt": 250.0, "in_tx": 6, "out_tx": 5}
    assert {edge["source"] for edge in card["connections"]["incoming"]} == {A, B}
    assert [edge["target"] for edge in card["connections"]["outgoing"]] == [BOUNDARY]
    assert isinstance(card["attention"], list) and card["attention"]
    assert card["viewer_url"] == f"/viewer#gid={RECEIVER}"


def test_api_contract_and_string_ids(graph_path):
    with TestClient(create_app(graph_path=graph_path)) as client:
        response = client.post("/api/ask", json={"question": f"Карточка {RECEIVER}"})
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result["answer"], str)
        assert RECEIVER in result["gids"]
        assert all(isinstance(gid, str) for gid in result["gids"])
        assert isinstance(result["tools"], list) and isinstance(result["meta"], dict)
        assert client.get(f"/api/node/{RECEIVER}").status_code == 200
        assert client.get(f"/api/card/{RECEIVER}").status_code == 200
        assert client.get(f"/api/node/{UNKNOWN}").status_code == 404
        assert client.get(f"/api/card/{UNKNOWN}").status_code == 404
        assert client.post("/api/ask", json={"question": ""}).status_code == 422
        assert client.get("/").status_code == 200


def test_api_serves_viewer_next_to_selected_graph(graph_path):
    viewer = graph_path.parent / "viewer.html"
    viewer.write_text("<!doctype html><title>Тестовая схема</title>", encoding="utf-8")
    with TestClient(create_app(graph_path=graph_path)) as client:
        response = client.get("/viewer")
        assert response.status_code == 200
        assert "Тестовая схема" in response.text
        assert "text/html" in response.headers["content-type"]


def test_api_graph_not_ready_is_503_and_chat_is_available(tmp_path):
    with TestClient(create_app(graph_path=tmp_path / "absent.json")) as client:
        assert client.get("/").status_code == 200
        assert client.post("/api/ask", json={"question": "Карточка узла"}).status_code == 503
        assert client.get(f"/api/node/{A}").status_code == 503
        assert client.get(f"/api/card/{A}").status_code == 503


@pytest.mark.parametrize("content", ["{invalid-json", '{"nodes": "invalid", "edges": []}'])
def test_api_malformed_graph_is_503_without_breaking_chat(tmp_path, content):
    path = tmp_path / "malformed.json"
    path.write_text(content, encoding="utf-8")
    with TestClient(create_app(graph_path=path)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["graph_available"] is False
        assert client.post("/api/ask", json={"question": "Покажи узлы"}).status_code == 503
        assert client.get(f"/api/node/{A}").status_code == 503
        assert client.get(f"/api/card/{A}").status_code == 503


def _response(response_id, output):
    return {
        "id": response_id, "object": "response", "created_at": 1790000000,
        "status": "completed", "model": config.MODEL_FAST, "output": output,
        "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens": 50, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 150},
    }


def _tool_call(gid):
    return {"type": "function_call", "id": "fc_test", "call_id": "call_test", "name": "get_node",
            "arguments": json.dumps({"gid": gid}), "status": "completed"}


def _message(answer, gids):
    return {"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "annotations": [],
                         "text": json.dumps({"answer": answer, "gids": gids, "confidence": .95})}]}


@pytest.fixture
def fake_live(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", "auto")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-offline-test")
    requests = []

    def install(replies):
        queue = copy.deepcopy(replies)

        def handle(request):
            requests.append(json.loads(request.content))
            if not queue:
                pytest.fail("Unexpected model request")
            reply = queue.pop(0)
            if isinstance(reply, int):
                return httpx.Response(reply, json={"error": {"message": "Offline simulated failure",
                                                            "type": "invalid_request_error"}})
            return httpx.Response(200, json=reply)

        llm.set_client(OpenAI(api_key="sk-offline-test", max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(handle))))
        return requests

    return install


def test_live_gateway_preserves_gid_and_removes_unsupported_model_references(store, fake_live):
    seen = fake_live([
        _response("r1", [_tool_call(A)]),
        _response("r2", [_message(f"Проверить {A}, {B} и {UNKNOWN}.", [A, B, UNKNOWN])]),
    ])
    answer, meta = assistant.ask(f"Разбери связи узла {A}", store=store)
    assert answer.gids == [A]
    assert A in answer.answer and B not in answer.answer and UNKNOWN not in answer.answer
    assert A in json.dumps(seen[0], ensure_ascii=False)
    assert seen[1]["previous_response_id"] == "r1"
    assert seen[1]["input"][0]["type"] == "function_call_output"
    assert meta["mode"] == "live"
    assert meta["tools_called"][0]["name"] == "get_node"


def test_http_answer_does_not_republish_removed_gids_in_metadata(graph_path, fake_live):
    fake_live([
        _response("api_tools", [_tool_call(A)]),
        _response("api_answer", [_message(f"Проверить {A}, {B} и {UNKNOWN}.", [A, B, UNKNOWN])]),
    ])
    with TestClient(create_app(graph_path=graph_path)) as client:
        response = client.post("/api/ask", json={"question": f"Разбери связи узла {A}"})
        assert response.status_code == 200
        assert response.json()["gids"] == [A]
        assert B not in response.text and UNKNOWN not in response.text


def test_observed_gids_do_not_leak_to_next_request_or_memory_cache(store, fake_live):
    seen = fake_live([
        _response("first_tools", [_tool_call(A)]),
        _response("first_answer", [_message(f"Проверить {A}", [A])]),
        _response("second_answer", [_message(f"Проверить {A}", [A])]),
    ])
    first, _ = assistant.ask("Покажи приоритетный узел", store=store)
    second, _ = assistant.ask("Покажи приоритетный узел", store=store)
    assert first.gids == [A]
    assert second.gids == [] and A not in second.answer
    assert len(seen) == 3


def test_gateway_authentication_error_returns_safe_fallback(store, fake_live):
    seen = fake_live([401])
    answer, meta = assistant.ask("Сравни гипотезы по всей сети", store=store)
    assert meta["mode"] == "fallback" and "AuthenticationError" in meta["error"]
    assert "llm" in answer.answer.lower() and answer.gids == []
    assert meta["tools_called"] == [] and len(seen) == 1


@pytest.mark.parametrize("demo_mode", ["on", "auto"])
def test_stale_demo_cache_cannot_supply_graph_answer(store, fake_live, monkeypatch, demo_mode):
    question = "Сравни гипотезы по всей сети"
    llm.save_demo_entry(question,
                       {"answer": f"Устаревший ответ с узлом {A}", "gids": [A], "confidence": .99},
                       {"model": "old-model", "tools_called": [{"name": "get_node", "result": {"id": A}}]})
    seen = fake_live([] if demo_mode == "on" else [401])
    monkeypatch.setattr(config, "DEMO_MODE", demo_mode)
    answer, meta = assistant.ask(question, store=store)
    assert answer.gids == [] and A not in answer.answer
    assert "Устаревший ответ" not in answer.answer
    assert meta["tools_called"] == [] and meta.get("cache") != "demo"
    assert len(seen) == (0 if demo_mode == "on" else 1)
