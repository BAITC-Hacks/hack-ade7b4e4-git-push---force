"""Оркестратор: parquet -> граф -> признаки -> роли -> кластеры -> приоритет -> выгрузки."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from . import cards as CA
from . import clusters as CL
from . import config as C
from . import export as EX
from . import extras as XT
from . import features as F
from . import layout as L
from . import priority as P
from . import robustness as RB
from . import roles as R
from .load import load, sanity


def run(data_dir: Path, out_dir: Path, build_viewer: bool = True, log=print) -> dict:
    t0 = time.perf_counter()
    timings = {}

    def mark(name: str) -> None:
        timings[name] = round(time.perf_counter() - t0, 2)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    edges, nodes, tx = load(Path(data_dir))
    meta = sanity(edges, nodes, tx)
    log(f"Данные: {meta['n_nodes']} узлов, {meta['n_edges']} рёбер, {meta['n_tx']} транзакций, "
        f"{meta['n_seed']} seed, период {meta['period']}")
    mark("load")

    G = F.build_graph(edges, nodes)
    df, extra = F.node_features(G, nodes, tx)
    mark("features")

    feats = df.copy()
    df = R.assign_roles(df, G)
    df["flags"] = df.apply(R.flags, axis=1)
    mark("roles")

    U = F.undirected(G)
    cluster_of = CL.louvain(U)
    df["cluster_id"] = pd.Series(cluster_of).reindex(df.index).astype(int)
    mark("clusters")

    df["priority_score"], comp = P.score(df)
    top = P.top_table(df, comp)
    df["rank"] = pd.Series(dict(zip(top["gid"], top["rank"]))).reindex(df.index)
    df["why"] = pd.Series(dict(zip(top["gid"], top["why"]))).reindex(df.index).fillna("")
    df["role_label"] = df["role"].map(C.ROLE_LABEL)
    clusters = CL.cluster_table(df, G)
    stab = RB.cluster_stability(U, cluster_of)
    clusters["stability"] = clusters["cluster_id"].map(stab)
    df["card"] = CA.all_cards(df, G)
    mark("priority")

    pos = L.to_frame(L.cluster_layout(U, cluster_of))
    df = df.join(pos)
    mark("layout")

    EX.write_csvs(df, clusters, top, out_dir)
    graph = EX.graph_json(df, G, clusters, top, meta)
    EX.write_json(graph, out_dir / "graph.json")
    XT.resilience(G, df).to_csv(out_dir / "resilience.csv", index=False)
    XT.next_requests(df).to_csv(out_dir / "next_requests.csv", index=False)
    XT.cycles_table(extra["cycles"], G).to_csv(out_dir / "cycles.csv", index=False)
    extra["routes"].to_csv(out_dir / "routes.csv", index=False)
    mark("export")
    sens = RB.sensitivity(feats, G, df)
    sens.to_csv(out_dir / "sensitivity.csv", index=False)
    mark("sensitivity")

    viewer_msg = EX.try_build_viewer(out_dir / "graph.json", out_dir / "viewer.html") if build_viewer else "экран: пропущен флагом"
    mark("viewer")

    summary = {
        **meta,
        "roles": {k: int((df["role"] == k).sum()) for k in C.ROLES},
        "clusters": int(len(clusters)),
        "clusters_multi_seed": int(((clusters["n_seed"] > 1) & (clusters["cluster_id"] != 0)).sum()),
        "cutoff_nodes": int(df["cutoff"].sum()),
        "cycles_len_le_6": len(extra["cycles"]),
        "recurring_routes": int(len(extra["routes"])),
        "top_n": int(len(top)),
        "sensitivity_min_top20_overlap": float(sens["top20_overlap"].min()),
        "cluster_stability_median": float(clusters.loc[clusters["cluster_id"] != 0, "stability"].median()),
        "timings_s": timings,
        "viewer": viewer_msg,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Роли: " + ", ".join(f"{k} {v}" for k, v in summary["roles"].items()))
    log(f"Кластеров: {summary['clusters']}, из них сообществ с 2+ seed: {summary['clusters_multi_seed']}. "
        f"Обрыв 4-го колена: {summary['cutoff_nodes']}. Циклов до {C.CYCLE_MAX_LEN}: {summary['cycles_len_le_6']}. "
        f"Устойчивых маршрутов: {summary['recurring_routes']}.")
    log(viewer_msg)
    log(f"Готово за {timings['viewer']} с. Выгрузки в {out_dir}/: nodes_roles.csv, clusters.csv, top_nodes.csv, graph.json")
    return summary
