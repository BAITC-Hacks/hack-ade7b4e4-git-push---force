"""Граф и признаки узлов: структура, потоки денег, охват seed, посредничество, время, циклы, маршруты."""
from __future__ import annotations

from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

from . import config as C


def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame) -> nx.DiGraph:
    """Направленный взвешенный граф. Вес ребра: сумма за июль, n_tx: число переводов."""
    G = nx.DiGraph()
    G.add_nodes_from(nodes["gid"].tolist())
    for r in edges.itertuples(index=False):
        G.add_edge(int(r.src), int(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return G


def undirected(G: nx.DiGraph) -> nx.Graph:
    """Неориентированная проекция ТОЛЬКО для кластеризации и раскладки. Встречные рёбра складываются."""
    U = nx.Graph()
    U.add_nodes_from(G.nodes)
    for u, v, a in G.edges(data=True):
        if U.has_edge(u, v):
            U[u][v]["sum_kzt"] += a["sum_kzt"]
            U[u][v]["n_tx"] += a["n_tx"]
        else:
            U.add_edge(u, v, sum_kzt=a["sum_kzt"], n_tx=a["n_tx"])
    return U


def _temporal(tx: pd.DataFrame) -> pd.DataFrame:
    """Сквозной транзит, синхронные поступления, активные дни."""
    inflow = tx.groupby(["dst", "date"]).agg(amt=("sum_kzt", "sum"), payers=("src", "nunique")).reset_index()
    outflow = tx.groupby(["src", "date"]).agg(amt=("sum_kzt", "sum"), recips=("dst", "nunique")).reset_index()

    in_dates: dict[int, set] = defaultdict(set)
    for r in inflow.itertuples(index=False):
        in_dates[int(r.dst)].add(r.date)

    fast_amt: dict[int, float] = defaultdict(float)
    lag = [pd.Timedelta(days=k) for k in range(C.FAST_DAYS + 1)]
    for r in outflow.itertuples(index=False):
        dates = in_dates.get(int(r.src))
        if dates and any((r.date - k) in dates for k in lag):
            fast_amt[int(r.src)] += float(r.amt)

    out_total = outflow.groupby("src")["amt"].sum()
    res = pd.DataFrame({
        "max_payers_same_day": inflow.groupby("dst")["payers"].max(),
        "max_recipients_same_day": outflow.groupby("src")["recips"].max(),
        "active_days_in": inflow.groupby("dst")["date"].nunique(),
        "active_days_out": outflow.groupby("src")["date"].nunique(),
    })
    fast = pd.Series(fast_amt, dtype=float)
    res["fast_out_share"] = (fast / out_total).reindex(res.index)
    return res


def recurring_routes(tx: pd.DataFrame) -> pd.DataFrame:
    """Устойчивые цепочки A->B->C: B переслал C в течение FAST_DAYS после поступления от A, минимум дважды."""
    a = tx.rename(columns={"src": "a", "dst": "b", "date": "d1", "sum_kzt": "s1"})
    b = tx.rename(columns={"src": "b", "dst": "c", "date": "d2", "sum_kzt": "s2"})
    m = a.merge(b, on="b")
    m = m[(m["a"] != m["c"]) & (m["d2"] >= m["d1"]) & ((m["d2"] - m["d1"]).dt.days <= C.FAST_DAYS)]
    if m.empty:
        return pd.DataFrame(columns=["a", "b", "c", "times", "sum_in_kzt", "sum_out_kzt"])
    r = (m.groupby(["a", "b", "c"])
         .agg(times=("d1", "nunique"), sum_in_kzt=("s1", "sum"), sum_out_kzt=("s2", "sum"))
         .reset_index())
    r = r[r["times"] >= C.ROUTE_MIN_TIMES].sort_values(["times", "sum_out_kzt"], ascending=False)
    return r.reset_index(drop=True)


def cycles(G: nx.DiGraph) -> list[list[int]]:
    """Возвратные потоки: простые циклы длиной до CYCLE_MAX_LEN."""
    return [c for c in nx.simple_cycles(G, length_bound=C.CYCLE_MAX_LEN)]


def node_features(G: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    seeds = set(nodes.loc[nodes["is_seed"], "gid"].astype("int64"))
    df = nodes[["gid", "depth", "is_seed"]].copy().set_index("gid")
    df["in_deg"] = pd.Series(dict(G.in_degree()))
    df["out_deg"] = pd.Series(dict(G.out_degree()))
    df["in_kzt"] = pd.Series(dict(G.in_degree(weight="sum_kzt"))).astype(float)
    df["out_kzt"] = pd.Series(dict(G.out_degree(weight="sum_kzt"))).astype(float)
    df["in_tx"] = pd.Series(dict(G.in_degree(weight="n_tx")))
    df["out_tx"] = pd.Series(dict(G.out_degree(weight="n_tx")))
    df["pass_through"] = np.where(df["in_kzt"] > 0, df["out_kzt"] / df["in_kzt"].replace(0, np.nan), np.nan)

    df["seed_payers"] = [sum(1 for p in G.predecessors(n) if p in seeds) for n in df.index]
    # сколько разных seed имеют направленный путь к узлу: здесь сходятся деньги известных участников
    upstream: dict[int, int] = defaultdict(int)
    for s in seeds:
        for n in nx.descendants(G, s):
            upstream[n] += 1
    df["seeds_upstream"] = pd.Series(upstream).reindex(df.index).fillna(0).astype(int)

    # максимальная доля одного контрагента: сбор от многих или от одного
    max_in_share, max_out_share = {}, {}
    for n in df.index:
        ins = [a["sum_kzt"] for _, _, a in G.in_edges(n, data=True)]
        outs = [a["sum_kzt"] for _, _, a in G.out_edges(n, data=True)]
        max_in_share[n] = max(ins) / sum(ins) if ins else np.nan
        max_out_share[n] = max(outs) / sum(outs) if outs else np.nan
    df["max_in_share"] = pd.Series(max_in_share)
    df["max_out_share"] = pd.Series(max_out_share)

    df["betweenness"] = pd.Series(nx.betweenness_centrality(G, normalized=True))
    df["pagerank"] = pd.Series(nx.pagerank(G, weight="sum_kzt", alpha=0.85))

    t = _temporal(tx).reindex(df.index)
    df = df.join(t)
    for col in ("max_payers_same_day", "max_recipients_same_day", "active_days_in", "active_days_out"):
        df[col] = df[col].fillna(0).astype(int)

    cyc = cycles(G)
    in_cycles: dict[int, int] = defaultdict(int)
    mutual: dict[int, int] = defaultdict(int)
    for c in cyc:
        bucket = mutual if len(c) == 2 else in_cycles
        for n in c:
            bucket[n] += 1
    # возвратный поток: деньги вернулись к отправителю через посредников (цикл длиной 3+)
    df["n_cycles"] = pd.Series(in_cycles).reindex(df.index).fillna(0).astype(int)
    # встречные переводы A <-> B (цикл длиной 2): слабый сигнал, в приоритет не входит
    df["n_mutual"] = pd.Series(mutual).reindex(df.index).fillna(0).astype(int)

    routes = recurring_routes(tx)
    route_mid = routes.groupby("b")["times"].sum() if not routes.empty else pd.Series(dtype=int)
    df["route_hits"] = route_mid.reindex(df.index).fillna(0).astype(int)

    df["cutoff"] = (df["depth"] >= C.MAX_DEPTH) & (df["out_deg"] == 0)
    df["isolated"] = (df["in_deg"] == 0) & (df["out_deg"] == 0)
    df["fast_transit"] = (~df["is_seed"]) & (df["out_kzt"] > 0) & (df["in_kzt"] > 0) & (df["fast_out_share"].fillna(0) >= C.FAST_SHARE)
    df["sync_inflow"] = df["max_payers_same_day"] >= C.SYNC_PAYERS

    extras = {"cycles": cyc, "routes": routes}
    return df, extras
