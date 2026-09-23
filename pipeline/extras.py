"""Опции ТЗ: устойчивость сети при изъятии топ-N, запросы для полноты данных, циклы и маршруты."""
from __future__ import annotations

import networkx as nx
import pandas as pd

from . import config as C
from .fmt import kzt, plural


def resilience(G: nx.DiGraph, df: pd.DataFrame, ns=(5, 10, 20, 30)) -> pd.DataFrame:
    """Что будет с сетью, если заблокировать топ-N по нашему приоритету, и для сравнения топ-N по числу связей."""
    U = G.to_undirected()
    base_lcc = max((len(c) for c in nx.connected_components(U)), default=0)
    total = sum(a["sum_kzt"] for _, _, a in G.edges(data=True))
    by_priority = df.sort_values("priority_score", ascending=False).index.tolist()
    by_degree = (df["in_deg"] + df["out_deg"]).sort_values(ascending=False).index.tolist()
    rows = []
    for strategy, order in (("priority", by_priority), ("degree", by_degree)):
        for n in ns:
            removed = set(order[:n])
            H = U.subgraph([x for x in U.nodes if x not in removed])
            comps = [len(c) for c in nx.connected_components(H)]
            touched = sum(a["sum_kzt"] for u, v, a in G.edges(data=True) if u in removed or v in removed)
            rows.append({
                "strategy": strategy, "removed_top_n": n,
                "largest_component": max(comps, default=0), "largest_component_before": base_lcc,
                "n_components": len(comps), "turnover_share_touched": round(touched / total, 4) if total else 0,
            })
    return pd.DataFrame(rows)


def next_requests(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Оценка полноты: каких данных не хватает и какой запрос сделать следующим."""
    rows = []
    cut_nodes = df[df["cutoff"]].sort_values("in_kzt", ascending=False).head(top_n)
    for gid, r in cut_nodes.iterrows():
        rows.append({"gid": int(gid), "gap": "обрыв выборки на 4-м колене",
                     "request": "Запросить исходящие переводы за июль 2026",
                     "reason": f"получил {kzt(r.in_kzt)} от {r.in_deg} {plural(r.in_deg, 'плательщика', 'плательщиков', 'плательщиков')}, куда деньги ушли дальше, не видно"})
    seeds = df[df["is_seed"] & (df["out_kzt"] > 0)].sort_values("out_kzt", ascending=False).head(top_n)
    for gid, r in seeds.iterrows():
        rows.append({"gid": int(gid), "gap": "входящие seed не собирались",
                     "request": "Запросить входящие переводы (источник средств)",
                     "reason": f"отправил {kzt(r.out_kzt)}, а видимый вход только {kzt(r.in_kzt)}"})
    ext = df[(~df["is_seed"]) & (df["pass_through"] > C.TRANSIT_HI)].sort_values("out_kzt", ascending=False).head(top_n)
    for gid, r in ext.iterrows():
        rows.append({"gid": int(gid), "gap": "источник средств вне выборки",
                     "request": "Запросить входящие переводы за июль 2026",
                     "reason": f"отправил {kzt(r.out_kzt)}, а в выборке получил только {kzt(r.in_kzt)}"})
    term = df[df["role"] == "terminal"].sort_values("in_kzt", ascending=False).head(top_n)
    for gid, r in term.iterrows():
        rows.append({"gid": int(gid), "gap": "деньги оседают на счёте",
                     "request": "Запросить снятия наличных, межбанковские и карточные операции",
                     "reason": f"получил {kzt(r.in_kzt)}, исходящих внутрибанковских от 5 000 ₸ нет"})
    top = df.sort_values("priority_score", ascending=False).head(20)
    for gid, r in top.iterrows():
        rows.append({"gid": int(gid), "gap": "переводы ниже 5 000 ₸ не видны",
                     "request": "Запросить полную выписку без порога суммы",
                     "reason": "узел в топ-20, возможное дробление ниже порога не видно"})
    return pd.DataFrame(rows)


def cycles_table(cycles: list[list[int]], G: nx.DiGraph, limit: int = 200) -> pd.DataFrame:
    rows = []
    for c in cycles:
        pairs = list(zip(c, c[1:] + c[:1]))
        amounts = [G[u][v]["sum_kzt"] for u, v in pairs]
        rows.append({"length": len(c), "path": " -> ".join(str(x) for x in c + c[:1]),
                     "min_edge_kzt": min(amounts), "sum_kzt": sum(amounts)})
    t = pd.DataFrame(rows, columns=["length", "path", "min_edge_kzt", "sum_kzt"])
    return t.sort_values(["min_edge_kzt", "sum_kzt"], ascending=False).head(limit).reset_index(drop=True)
