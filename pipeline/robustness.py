"""Проверка обоснованности: устойчивость кластеров к seed алгоритма и чувствительность ролей и топа к порогам."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx
import pandas as pd

from . import config as C
from . import priority as P
from . import roles as R

STABILITY_SEEDS = (1, 2, 3, 4)


def cluster_stability(U: nx.Graph, cluster_of: dict[int, int]) -> dict[int, float]:
    """Для каждого кластера: доля пар его узлов, которые остаются вместе при других seed Louvain (среднее)."""
    connected = [n for n in U.nodes if U.degree(n) > 0]
    sub = U.subgraph(connected)
    runs = []
    for s in STABILITY_SEEDS:
        comms = nx.community.louvain_communities(sub, weight="sum_kzt", resolution=1.0, seed=s)
        lab = {}
        for i, c in enumerate(comms):
            for n in c:
                lab[n] = i
        runs.append(lab)
    members: dict[int, list[int]] = defaultdict(list)
    for n, c in cluster_of.items():
        members[c].append(n)
    out = {}
    for c, ns in members.items():
        if c == 0 or len(ns) < 2:
            out[c] = 1.0
            continue
        pairs = list(combinations(ns, 2))
        if len(pairs) > 20000:  # большой кластер: равномерная выборка пар
            step = len(pairs) // 20000 + 1
            pairs = pairs[::step]
        together = [sum(1 for a, b in pairs if lab[a] == lab[b]) / len(pairs) for lab in runs]
        out[c] = round(sum(together) / len(together), 3)
    return out


def sensitivity(df_features: pd.DataFrame, G: nx.DiGraph, base: pd.DataFrame) -> pd.DataFrame:
    """Меняем ключевые пороги на шаг вверх и вниз: сколько узлов сменило роль, насколько сохранился топ-20."""
    grid = {
        "HUB_IN": (4, 6), "HUB_OUT": (4, 6), "FAN_IN": (4, 6), "FAN_OUT": (8, 12),
        "TERMINAL_MIN_KZT": (50_000, 200_000), "TRANSIT_LO": (0.7, 0.9),
    }
    base_top = set(base.sort_values("priority_score", ascending=False).index[:20])
    rows = []
    for param, values in grid.items():
        original = getattr(C, param)
        for v in values:
            setattr(C, param, v)
            try:
                d = R.assign_roles(df_features, G)
                d["flags"] = pd.Series([R.flags(r) for r in d.itertuples()], index=d.index)
                d["priority_score"], _ = P.score(d)
            finally:
                setattr(C, param, original)
            top = set(d.sort_values("priority_score", ascending=False).index[:20])
            rows.append({
                "param": param, "base": original, "value": v,
                "roles_changed": int((d["role"] != base["role"]).sum()),
                "top20_overlap": round(len(top & base_top) / 20, 2),
            })
    return pd.DataFrame(rows)
