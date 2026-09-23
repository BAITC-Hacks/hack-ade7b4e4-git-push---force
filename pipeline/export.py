"""Выгрузки: три CSV по схеме ТЗ (+ служебные колонки), graph.json для экрана и ассистента, отчёты."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd

from . import config as C

REQUIRED_NODES = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
EXTRA_NODES = ["role_label", "rank", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
               "pass_through", "seed_payers", "seeds_upstream", "from_consolidators", "betweenness",
               "fast_out_share", "max_payers_same_day", "n_cycles", "n_mutual", "route_hits", "forward_prob", "flags", "rule"]


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
    return v


def nodes_frame(df: pd.DataFrame) -> pd.DataFrame:
    t = df.reset_index().rename(columns={"index": "gid"})
    t["flags"] = t["flags"].map(lambda f: ";".join(f))
    t = t[REQUIRED_NODES + EXTRA_NODES].copy()
    for col in ("pass_through", "fast_out_share", "forward_prob", "betweenness"):
        t[col] = t[col].astype(float).round(4)
    t["rank"] = t["rank"].astype("Int64")
    return t.sort_values(["priority_score", "gid"], ascending=[False, True])


def write_csvs(df: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame, out: Path) -> None:
    nodes_frame(df).to_csv(out / "nodes_roles.csv", index=False)
    clusters.to_csv(out / "clusters.csv", index=False)
    top.to_csv(out / "top_nodes.csv", index=False)


def graph_json(df: pd.DataFrame, G: nx.DiGraph, clusters: pd.DataFrame, top: pd.DataFrame, meta: dict) -> dict:
    rules = C.role_rules()
    roles = [{"key": k, "label": C.ROLE_LABEL[k], "color": C.ROLE_COLOR[k], "rule": rules[k],
              "count": int((df["role"] == k).sum())} for k in C.ROLES]
    nodes = []
    for gid, r in df.iterrows():
        nodes.append({
            "id": str(gid), "role": r.role, "role_score": _clean(float(r.role_score)),
            "cluster_id": int(r.cluster_id), "priority_score": _clean(float(r.priority_score)),
            "rank": None if pd.isna(r["rank"]) else int(r["rank"]),
            "is_seed": bool(r.is_seed), "depth": int(r.depth),
            "in_deg": int(r.in_deg), "out_deg": int(r.out_deg),
            "in_kzt": _clean(float(r.in_kzt)), "out_kzt": _clean(float(r.out_kzt)),
            "in_tx": int(r.in_tx), "out_tx": int(r.out_tx),
            "pass_through": _clean(float(r.pass_through)) if not pd.isna(r.pass_through) else None,
            "seeds_upstream": int(r.seeds_upstream),
            "evidence": r.evidence, "why": r.why if isinstance(r.why, str) else "",
            "flags": list(r["flags"]), "card": r.card, "x": _clean(float(r.x)), "y": _clean(float(r.y)),
        })
    edges = [{"source": str(u), "target": str(v), "sum_kzt": round(float(a["sum_kzt"]), 2),
              "n_tx": int(a["n_tx"]), "depth": int(a["depth"])} for u, v, a in G.edges(data=True)]
    cl = [{"cluster_id": int(r.cluster_id), "n_nodes": int(r.n_nodes), "n_seed": int(r.n_seed),
           "sum_kzt_internal": float(r.sum_kzt_internal), "top_gids": r.top_gids.split(";") if r.top_gids else [],
           "hypothesis": r.hypothesis, "roles": r.roles, "stability": _clean(float(r.stability))}
          for r in clusters.itertuples(index=False)]
    tp = [{"rank": int(r.rank), "gid": str(r.gid), "role": r.role, "priority_score": float(r.priority_score),
           "why": r.why} for r in top.itertuples(index=False)]
    meta = {**meta, "generated_at": datetime.now().isoformat(timespec="seconds")}
    return {"meta": meta, "roles": roles, "nodes": nodes, "edges": edges, "clusters": cl, "top": tp}


def write_json(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def try_build_viewer(graph_path: Path, html_path: Path) -> str:
    """Экран собирает модуль viewer/ (зона Напарника 1). Если его нет или он упал, собираем запасной экран."""
    reason = ""
    try:
        from viewer.build import build_viewer  # type: ignore
        build_viewer(graph_path, html_path)
        return f"экран: {html_path}"
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
    try:
        from .fallback_viewer import build
        build(graph_path, html_path)
        return f"экран (запасной): {html_path} (viewer/ недоступен: {reason[:80]})"
    except Exception as exc:  # noqa: BLE001
        return f"экран не собран: {type(exc).__name__}: {exc}"
