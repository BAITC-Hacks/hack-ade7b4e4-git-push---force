"""Local, bounded graph queries and request-scoped evidence for the assistant.

No tool reads external data. Node identifiers are strings even when a producer
supplies a Python integer, so int64 identifiers never pass through floats.
"""
from __future__ import annotations

import copy
import json
import math
import os
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_RESULTS = 200
MAX_PATHS = 100
MAX_PATH_WORK = 10_000
TOOL_NAMES = (
    "get_node", "neighbors", "top_nodes", "cluster_info", "common_receivers",
    "paths", "search",
)


def _gid(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("gid должен быть строкой или целым числом")
    value = str(value)
    if not value or len(value) > 128 or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Некорректный gid")
    return value


def _cluster_key(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)) or str(value).strip() != str(value) or not str(value):
        raise ValueError("cluster_id должен быть целым числом или непустой строкой")
    return str(value)


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} должен быть целым числом от {minimum} до {maximum}")
    return value


def _filter(value: Any, name: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} должен быть непустой строкой или null")
    return value


def _nonnegative_number(value: Any, name: str) -> None:
    finite = False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            pass
    if not finite or value < 0:
        raise ValueError(f"{name} должен быть конечным неотрицательным числом")


def _nonnegative_integer(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} должен быть неотрицательным целым числом")


def _nonempty_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} должен быть непустой строкой")


def _validate_node(node: dict) -> None:
    # Cards use these contract fields directly. Reject missing or malformed
    # metrics at load time instead of inventing zero flows or failing per request.
    _nonempty_string(node.get("role"), "role узла")
    for field in ("in_kzt", "out_kzt"):
        _nonnegative_number(node.get(field), field)
    for field in ("in_tx", "out_tx", "in_deg", "out_deg"):
        _nonnegative_integer(node.get(field), field)
    flags = node.get("flags")
    if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
        raise ValueError("flags узла должны быть списком строк")
    for field in ("evidence", "why"):
        if field in node and not isinstance(node[field], str):
            raise ValueError(f"{field} узла должен быть строкой")
    for field in ("role_score", "priority_score"):
        if field in node:
            _nonnegative_number(node[field], field)
    for field in ("depth", "seeds_upstream"):
        if field in node:
            _nonnegative_integer(node[field], field)
    if "is_seed" in node and not isinstance(node["is_seed"], bool):
        raise ValueError("is_seed узла должен быть логическим значением")
    if node.get("rank") is not None:
        _nonnegative_integer(node["rank"], "rank")
        if node["rank"] == 0:
            raise ValueError("rank узла должен быть положительным или null")
    # The pipeline uses null when the incoming flow is zero.
    if node.get("pass_through") is not None:
        _nonnegative_number(node["pass_through"], "pass_through")


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _money(edges: list[dict]) -> float:
    # Decimal avoids intermediate binary rounding when many edge totals are added.
    return float(sum((Decimal(str(edge["sum_kzt"])) for edge in edges), Decimal(0)))


def _priority(node: dict) -> tuple:
    score = node.get("priority_score", 0)
    score = score if isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score) else 0
    rank = node.get("rank")
    rank = rank if isinstance(rank, int) and not isinstance(rank, bool) else math.inf
    return (-score, rank, node["id"])


def _edge_order(edge: dict) -> tuple:
    return (-edge["sum_kzt"], edge["source"], edge["target"], -edge["n_tx"])


class GraphStore:
    """A validated graph snapshot with indexes shared by read-only queries."""

    def __init__(self, graph: dict):
        if not isinstance(graph, dict):
            raise ValueError("graph.json должен содержать объект")
        # Reject non-JSON objects and NaN/Infinity before exposing data to tools.
        try:
            json.dumps(graph, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Граф содержит недопустимые JSON-значения") from exc
        graph = copy.deepcopy(graph)
        self.meta = graph.get("meta", {})
        self.roles = graph.get("roles", [])
        if not isinstance(self.meta, dict) or not isinstance(self.roles, list):
            raise ValueError("Некорректные meta или roles")
        role_keys = set()
        for role in self.roles:
            if not isinstance(role, dict):
                raise ValueError("Каждая роль должна быть объектом")
            _nonempty_string(role.get("key"), "key роли")
            _nonempty_string(role.get("label"), "label роли")
            if role["key"] in role_keys:
                raise ValueError("Повторный key роли")
            role_keys.add(role["key"])
        raw_nodes, raw_edges = graph.get("nodes", []), graph.get("edges", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("nodes и edges должны быть списками")
        self.nodes: dict[str, dict] = {}
        self.clusters: dict[str, dict] = {}
        self.incoming: dict[str, list[dict]] = defaultdict(list)
        self.outgoing: dict[str, list[dict]] = defaultdict(list)
        self._cluster_nodes: dict[str, list[dict]] = defaultdict(list)
        self._pair_edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self._targets: dict[str, set[str]] = defaultdict(set)
        for node in raw_nodes:
            if not isinstance(node, dict) or "id" not in node:
                raise ValueError("У каждого узла должен быть id")
            node["id"] = gid = _gid(node["id"])
            _validate_node(node)
            if gid in self.nodes:
                raise ValueError(f"Повторный gid: {gid}")
            self.nodes[gid] = node
            if node.get("cluster_id") is not None:
                self._cluster_nodes[_cluster_key(node["cluster_id"])].append(node)
        self.edges: list[dict] = []
        for edge in raw_edges:
            if not isinstance(edge, dict) or "source" not in edge or "target" not in edge:
                raise ValueError("У каждой связи должны быть source и target")
            edge["source"], edge["target"] = _gid(edge["source"]), _gid(edge["target"])
            if edge["source"] not in self.nodes or edge["target"] not in self.nodes:
                raise ValueError("Связь ссылается на отсутствующий узел")
            amount, count = edge.get("sum_kzt"), edge.get("n_tx")
            _nonnegative_number(amount, "sum_kzt связи")
            _nonnegative_integer(count, "n_tx связи")
            edge["sum_kzt"], edge["n_tx"] = amount, count
            self.edges.append(edge)
            self.incoming[edge["target"]].append(edge)
            self.outgoing[edge["source"]].append(edge)
            self._pair_edges[(edge["source"], edge["target"])].append(edge)
            self._targets[edge["source"]].add(edge["target"])
        self._adjacency = {gid: sorted(targets) for gid, targets in self._targets.items()}
        for index in (self.incoming, self.outgoing, self._pair_edges):
            for edges in index.values():
                edges.sort(key=_edge_order)
        raw_clusters = graph.get("clusters", [])
        if not isinstance(raw_clusters, list):
            raise ValueError("clusters должен быть списком")
        for cluster in raw_clusters:
            if not isinstance(cluster, dict) or "cluster_id" not in cluster:
                raise ValueError("У каждого кластера должен быть cluster_id")
            key = _cluster_key(cluster["cluster_id"])
            if key in self.clusters:
                raise ValueError("Повторный cluster_id")
            if "top_gids" in cluster:
                if not isinstance(cluster["top_gids"], list):
                    raise ValueError("top_gids должен быть списком")
                cluster["top_gids"] = [_gid(gid) for gid in cluster["top_gids"]]
                if any(gid not in self.nodes for gid in cluster["top_gids"]):
                    raise ValueError("top_gids ссылается на отсутствующий узел")
            self.clusters[key] = cluster
        self._ranked = sorted(self.nodes.values(), key=_priority)

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "GraphStore":
        graph_path = Path(path) if path is not None else Path(os.getenv("GRAPH_JSON") or ROOT / "out" / "graph.json")
        with graph_path.open(encoding="utf-8") as stream:
            return cls(json.load(stream))

    def _node(self, gid: Any) -> dict:
        gid = _gid(gid)
        if gid not in self.nodes:
            raise LookupError("Узел отсутствует в графе")
        return self.nodes[gid]

    def get_node(self, gid: str) -> dict:
        try:
            return copy.deepcopy(self._node(gid))
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        except LookupError as exc:
            return _error("node_not_found", str(exc))

    def neighbors(self, gid: str, direction: str = "both", limit: int = 50) -> dict:
        try:
            node = self._node(gid)
            limit = _integer(limit, "limit", 1, MAX_RESULTS)
            direction = {"incoming": "in", "outgoing": "out"}.get(direction, direction)
            if direction not in ("in", "out", "both"):
                raise ValueError("direction должен быть in, out или both")
        except (ValueError, TypeError) as exc:
            return _error("invalid_arguments", str(exc))
        except LookupError as exc:
            return _error("node_not_found", str(exc))
        gid = node["id"]
        incoming = self.incoming.get(gid, []) if direction != "out" else []
        outgoing = self.outgoing.get(gid, []) if direction != "in" else []
        # Apply one combined limit, including when both directions are requested.
        selected = sorted([(e, "in") for e in incoming] + [(e, "out") for e in outgoing], key=lambda item: (_edge_order(item[0]), item[1]))[:limit]
        peers = sorted({e["source"] if side == "in" else e["target"] for e, side in selected})
        return copy.deepcopy({
            "node": node, "incoming": [e for e, side in selected if side == "in"],
            "outgoing": [e for e, side in selected if side == "out"],
            "nodes": [self.nodes[peer] for peer in peers],
            "count": len(incoming) + len(outgoing), "returned": len(selected),
            "truncated": len(incoming) + len(outgoing) > len(selected),
        })

    def _matching(self, role: str | None, cluster_id: int | str | None, flag: str | None = None) -> list[dict]:
        role, flag = _filter(role, "role"), _filter(flag, "flag")
        cluster = _cluster_key(cluster_id) if cluster_id is not None else None
        return [node for node in self._ranked
                if (role is None or node.get("role") == role)
                and (cluster is None or str(node.get("cluster_id")) == cluster)
                and (flag is None or flag in node.get("flags", []))]

    def top_nodes(self, n: int = 10, role: str | None = None, cluster_id: int | str | None = None) -> dict:
        try:
            n = _integer(n, "n", 1, MAX_RESULTS)
            nodes = self._matching(role, cluster_id)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        return copy.deepcopy({"nodes": nodes[:n], "count": len(nodes), "returned": min(n, len(nodes)), "truncated": len(nodes) > n})

    def cluster_info(self, cluster_id: int | str) -> dict:
        try:
            key = _cluster_key(cluster_id)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        nodes = sorted(self._cluster_nodes.get(key, []), key=_priority)
        if key not in self.clusters and not nodes:
            return _error("cluster_not_found", "Кластер отсутствует в графе")
        cluster = self.clusters.get(key, {"cluster_id": nodes[0]["cluster_id"]})
        return copy.deepcopy({"cluster": cluster, "nodes": nodes[:MAX_RESULTS], "count": len(nodes), "returned": min(MAX_RESULTS, len(nodes)), "truncated": len(nodes) > MAX_RESULTS})

    def common_receivers(self, gids: list[str]) -> dict:
        try:
            if not isinstance(gids, list) or not 1 <= len(gids) <= 100:
                raise ValueError("gids должен содержать от 1 до 100 идентификаторов")
            sources = list(dict.fromkeys(self._node(gid)["id"] for gid in gids))
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        except LookupError as exc:
            return _error("node_not_found", str(exc))
        receivers = set(self._targets.get(sources[0], set()))
        for source in sources[1:]:
            receivers.intersection_update(self._targets.get(source, set()))
        # Rank all matches from full totals, then bound sender/edge evidence.
        # Large source sets must not multiply a 200-row response into 20k rows.
        totals = []
        for receiver in receivers:
            all_edges = [edge for source in sources for edge in self._pair_edges[(source, receiver)]]
            totals.append((receiver, _money(all_edges), sum(e["n_tx"] for e in all_edges)))
        totals.sort(key=lambda row: (-row[1], row[0]))
        receiver_limit = max(1, MAX_RESULTS // len(sources))
        selected = totals[:receiver_limit]
        edge_limit = max(1, (2 * MAX_RESULTS) // max(1, len(selected) * len(sources)))
        rows, evidence_truncated = [], False
        for receiver, amount, count in selected:
            evidence = []
            for source in sources:
                edges = self._pair_edges[(source, receiver)]
                partial = len(edges) > edge_limit
                evidence_truncated |= partial
                evidence.append({"gid": source, "edges": edges[:edge_limit],
                                 "edge_count": len(edges), "truncated": partial,
                                 "sum_kzt": _money(edges), "n_tx": sum(e["n_tx"] for e in edges)})
            rows.append({"gid": receiver, "node": self.nodes[receiver], "sources": evidence,
                         "sum_kzt": amount, "n_tx": count})
        return copy.deepcopy({"gids": sources, "source_nodes": [self.nodes[gid] for gid in sources], "receivers": rows,
                              "count": len(totals), "returned": len(rows),
                              "truncated": len(totals) > len(rows) or evidence_truncated})

    def paths(self, src: str, dst: str, max_len: int = 4) -> dict:
        try:
            src, dst = self._node(src)["id"], self._node(dst)["id"]
            max_len = _integer(max_len, "max_len", 1, 4)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        except LookupError as exc:
            return _error("node_not_found", str(exc))
        found, queue, work, truncated = [], deque([[src]]), 0, False
        while queue:
            route = queue.popleft()
            if route[-1] == dst:
                pairs = [self._pair_edges[(source, target)] for source, target in zip(route, route[1:])]
                edge_limit = max(1, MAX_RESULTS // max(1, len(pairs)))
                route_edges = [edge for edges in pairs for edge in edges[:edge_limit]]
                edge_count = sum(len(edges) for edges in pairs)
                found.append({"gids": route, "edges": route_edges,
                              "edge_count": edge_count, "truncated": edge_count > len(route_edges)})
                if len(found) >= MAX_PATHS:
                    truncated = bool(queue)
                    break
                continue
            if len(route) - 1 >= max_len:
                continue
            for target in self._adjacency.get(route[-1], []):
                if work >= MAX_PATH_WORK:
                    truncated = True
                    break
                work += 1
                if target not in route:
                    queue.append(route + [target])
            if truncated:
                break
        return copy.deepcopy({"src": src, "dst": dst, "source_node": self.nodes[src], "target_node": self.nodes[dst],
                              "paths": found, "count": len(found),
                              "truncated": truncated or any(route["truncated"] for route in found)})

    def search(self, role: str | None = None, cluster_id: int | str | None = None, flag: str | None = None) -> dict:
        try:
            nodes = self._matching(role, cluster_id, flag)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))
        return copy.deepcopy({"nodes": nodes[:MAX_RESULTS], "count": len(nodes), "returned": min(MAX_RESULTS, len(nodes)), "truncated": len(nodes) > MAX_RESULTS})


_STRING = {"type": "string"}
_NULLABLE_STRING = {"type": ["string", "null"]}
_CLUSTER = {"type": ["integer", "string", "null"]}
_SCHEMAS = {
    "get_node": ("Карточка узла по точному строковому gid.", {"gid": _STRING}),
    "neighbors": ("Входящие и исходящие связи узла; общее число результатов ограничено limit.", {
        "gid": _STRING, "direction": {"type": "string", "enum": ["in", "out", "both"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}}),
    "top_nodes": ("Узлы по убыванию priority_score; фильтры роли и кластера необязательны.", {
        "n": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}, "role": _NULLABLE_STRING, "cluster_id": _CLUSTER}),
    "cluster_info": ("Метаданные кластера и его узлы; список узлов ограничен 200.", {"cluster_id": {"type": ["integer", "string"]}}),
    "common_receivers": ("Кто получает прямые переводы от каждого из перечисленных узлов; возвращает суммы и связи-доказательства.", {
        "gids": {"type": "array", "items": _STRING, "minItems": 1, "maxItems": 100}}),
    "paths": ("Направленные простые пути (без повторов узлов), до 4 связей; результат и работа ограничены.", {
        "src": _STRING, "dst": _STRING, "max_len": {"type": "integer", "minimum": 1, "maximum": 4}}),
    "search": ("Фильтр узлов по роли, кластеру и флагу. null означает отсутствие фильтра; максимум 200 узлов.", {
        "role": _NULLABLE_STRING, "cluster_id": _CLUSTER, "flag": _NULLABLE_STRING}),
}


def openai_tools(names: list[str] | None = None) -> list[dict]:
    result = []
    for name in TOOL_NAMES if names is None else names:
        if name not in _SCHEMAS:
            raise ValueError(f"Неизвестный инструмент: {name}")
        description, properties = _SCHEMAS[name]
        result.append({"type": "function", "name": name, "description": description, "strict": True,
                       "parameters": {"type": "object", "properties": copy.deepcopy(properties),
                                      "required": list(properties), "additionalProperties": False}})
    return result


class GraphTools:
    """Tool provider and evidence ledger. Create a fresh instance per answer."""

    def __init__(self, store: GraphStore):
        self.store = store
        self.calls: list[dict] = []
        self.observed_gids: set[str] = set()

    def openai_tools(self, names: list[str] | None = None) -> list[dict]:
        return openai_tools(names)

    def call_tool(self, name: str, arguments: dict | str) -> dict:
        decoded: Any = arguments
        try:
            if name not in TOOL_NAMES:
                raise ValueError("Неизвестный инструмент")
            decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(decoded, dict):
                raise ValueError("Аргументы инструмента должны быть объектом")
            result = getattr(self.store, name)(**decoded)
        except (TypeError, ValueError, OverflowError) as exc:
            result = _error("invalid_arguments", str(exc))
        self.calls.append({"name": name, "arguments": copy.deepcopy(decoded), "result": copy.deepcopy(result)})
        if "error" not in result:
            self._record_result(name, result)
        return result

    def _record_result(self, name: str, result: dict) -> None:
        # Follow the tool's schema, never arbitrary values or the argument list.
        def record(value: Any) -> None:
            if isinstance(value, str) and value in self.store.nodes:
                self.observed_gids.add(value)

        def node(value: Any) -> None:
            if isinstance(value, dict):
                record(value.get("id"))

        def edge(value: Any) -> None:
            if isinstance(value, dict):
                record(value.get("source"))
                record(value.get("target"))

        if name == "get_node":
            node(result)
        elif name in ("top_nodes", "search", "cluster_info"):
            for value in result.get("nodes", []):
                node(value)
            if name == "cluster_info":
                for gid in result.get("cluster", {}).get("top_gids", []):
                    record(gid)
        elif name == "neighbors":
            node(result.get("node"))
            for value in result.get("nodes", []):
                node(value)
            for value in result.get("incoming", []) + result.get("outgoing", []):
                edge(value)
        elif name == "common_receivers":
            for value in result.get("source_nodes", []):
                node(value)
            for receiver in result.get("receivers", []):
                node(receiver.get("node"))
                record(receiver.get("gid"))
                for source in receiver.get("sources", []):
                    record(source.get("gid"))
                    for value in source.get("edges", []):
                        edge(value)
        elif name == "paths":
            node(result.get("source_node"))
            node(result.get("target_node"))
            for route in result.get("paths", []):
                for gid in route.get("gids", []):
                    record(gid)
                for value in route.get("edges", []):
                    edge(value)
