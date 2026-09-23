"""Кластеры: Louvain на неориентированной проекции (вес ребра = сумма переводов), seed=42.

Направление здесь сознательно не учитываем: кластер отвечает на вопрос «кто с кем связан деньгами».
Направление потоков остаётся в ролях и на схеме. Узлы без связей собраны в кластер 0.
"""
from __future__ import annotations

from collections import Counter

import networkx as nx
import pandas as pd

from . import config as C
from .fmt import cut, kzt, plural


def louvain(U: nx.Graph) -> dict[int, int]:
    connected = [n for n in U.nodes if U.degree(n) > 0]
    sub = U.subgraph(connected)
    comms = nx.community.louvain_communities(sub, weight="sum_kzt", resolution=1.0, seed=C.SEED)
    comms = sorted(comms, key=lambda c: (-len(c), min(c)))
    cid = {n: 0 for n in U.nodes}      # 0 = узлы без связей в выборке
    for i, c in enumerate(comms, start=1):
        for n in c:
            cid[n] = i
    return cid


def _hypothesis(cid: int, g: pd.DataFrame, internal: float, key: int | None) -> str:
    n, n_seed = len(g), int(g["is_seed"].sum())
    roles = Counter(g["role"])
    co, cons, dist = roles["coordinator"], roles["consolidator"], roles["distributor"]
    tr, term = roles["transit"], roles["terminal"]
    if cid == 0:
        return cut(f"Гипотеза: {n} узлов без переводов в выборке ({n_seed} seed). Связи вне данных: "
                   f"нужны переводы ниже 5 000 ₸, межбанковские и наличные.", 300)
    n_cons = f"{cons} {plural(cons, 'точка', 'точки', 'точек')} консолидации"
    n_dist = f"{dist} {plural(dist, 'распределитель', 'распределителя', 'распределителей')}"
    if co and (cons or dist):
        if cons and dist:
            link = f"связывает сбор ({n_cons}) и раздачу ({n_dist})"
        elif dist:
            link = f"стоит над раздачей денег через {n_dist}"
        else:
            link = f"принимает деньги от контура сбора ({n_cons})"
        return cut(f"Гипотеза: ядро схемы. Координатор {key} {link}; "
                   f"{n_seed} seed, оборот внутри {kzt(internal)}. Проверять в первую очередь.", 300)
    if co:
        return cut(f"Гипотеза: узел-хаб {key} собирает и раздаёт деньги внутри группы из {n} участников; "
                   f"{n_seed} seed, оборот {kzt(internal)}.", 300)
    if dist and dist >= cons:
        recips = int(g.loc[g["role"] == "distributor", "out_deg"].sum())
        verb = "рассылает" if dist == 1 else "рассылают"
        return cut(f"Гипотеза: контур раздачи. {n_dist.capitalize()} {verb} деньги {recips} получателям; "
                   f"{n_seed} seed, оборот {kzt(internal)}. Возможны выплаты участникам или обналичивание.", 300)
    if cons:
        verb = "аккумулирует" if cons == 1 else "аккумулируют"
        return cut(f"Гипотеза: контур сбора. {n_cons.capitalize()} {verb} средства участников группы "
                   f"из {n}; {n_seed} seed, оборот {kzt(internal)}.", 300)
    if tr:
        return cut(f"Гипотеза: транзитная цепочка из {n} узлов, {tr} транзитных счетов; {n_seed} seed, "
                   f"оборот {kzt(internal)}.", 300)
    if term:
        return cut(f"Гипотеза: периферия, деньги оседают у {term} "
                   f"{plural(term, 'конечного получателя', 'конечных получателей', 'конечных получателей')}; {n_seed} seed, "
                   f"оборот {kzt(internal)}. Низкий приоритет.", 300)
    return cut(f"Гипотеза: периферийная группа из {n} узлов без выраженных ролей; {n_seed} seed.", 300)


def cluster_table(df: pd.DataFrame, G: nx.DiGraph) -> pd.DataFrame:
    internal: Counter = Counter()
    for u, v, a in G.edges(data=True):
        cu, cv = df.at[u, "cluster_id"], df.at[v, "cluster_id"]
        if cu == cv:
            internal[cu] += a["sum_kzt"]
    rows = []
    for cid, g in df.groupby("cluster_id"):
        g = g.sort_values("priority_score", ascending=False)
        top = [str(x) for x in g.index[:5]]
        coords = g.index[g["role"] == "coordinator"]
        key = int(coords[0]) if len(coords) else (int(g.index[0]) if len(g) else None)
        roles = Counter(g["role"])
        rows.append({
            "cluster_id": int(cid),
            "n_nodes": int(len(g)),
            "n_seed": int(g["is_seed"].sum()),
            "sum_kzt_internal": round(float(internal[cid]), 2),
            "top_gids": ";".join(top),
            "hypothesis": _hypothesis(int(cid), g, float(internal[cid]), key),
            "roles": ", ".join(f"{k}:{v}" for k, v in sorted(roles.items(), key=lambda kv: -kv[1])),
            "max_priority": round(float(g["priority_score"].max()), 3),
        })
    t = pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)
    return t
