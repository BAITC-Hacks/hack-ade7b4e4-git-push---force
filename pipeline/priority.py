"""Приоритет для аналитика: прозрачная взвешенная сумма пяти компонент (веса в config.PRIORITY_WEIGHTS).

role    вес роли из словаря
seeds   сколько из 81 seed имеют направленный путь к узлу (деньги известных участников сходятся здесь)
volume  оборот узла, лог-шкала от 5 тыс. до 30 млн ₸
bridge  посредничество: процентиль betweenness среди узлов с ненулевым значением
signals временные и маршрутные признаки: сквозной транзит, синхронные поступления, циклы, устойчивые маршруты
Seed умножаем на SEED_DISCOUNT: они уже известны следствию, ищем новые узлы.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from .fmt import cut, kzt, plural


def components(df: pd.DataFrame) -> pd.DataFrame:
    comp = pd.DataFrame(index=df.index)
    comp["role"] = df["role"].map(C.ROLE_WEIGHT).astype(float)
    max_up = max(1, int(df["seeds_upstream"].max()))
    comp["seeds"] = df["seeds_upstream"] / max_up
    vol = (df["in_kzt"] + df["out_kzt"]).clip(lower=1.0)
    lo, hi = math.log10(C.VOLUME_LO), math.log10(C.VOLUME_HI)
    comp["volume"] = ((np.log10(vol) - lo) / (hi - lo)).clip(0, 1)
    b = df["betweenness"]
    comp["bridge"] = b.where(b > 0).rank(pct=True).fillna(0.0)
    sig = (df["fast_transit"].astype(int) + df["sync_inflow"].astype(int)
           + (df["n_cycles"] > 0).astype(int) + (df["route_hits"] > 0).astype(int))
    comp["signals"] = sig / 4.0
    return comp


def score(df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    comp = components(df)
    w = C.PRIORITY_WEIGHTS
    raw = sum(comp[k] * w[k] for k in w)
    raw = raw * np.where(df["is_seed"], C.SEED_DISCOUNT, 1.0)
    return raw.clip(0, 1).round(4), comp


def _why(r: pd.Series, c: pd.Series, rank: int) -> str:
    reasons = []
    if c["seeds"] >= 0.5:
        reasons.append(f"сюда ведут пути от {r.seeds_upstream} seed")
    if r.in_kzt + r.out_kzt >= 1_000_000:
        reasons.append(f"оборот {kzt(r.in_kzt + r.out_kzt)}")
    if c["bridge"] >= 0.9:
        reasons.append(f"мост между частями сети (посредничество выше, чем у {c['bridge'] * 100:.0f}% узлов)")
    extra = []
    if r.fast_transit:
        extra.append("сквозной транзит за 2 дня")
    if r.sync_inflow:
        extra.append(f"{r.max_payers_same_day} {plural(r.max_payers_same_day, 'плательщик', 'плательщика', 'плательщиков')} в один день")
    if r.n_cycles > 0:
        extra.append("возвратные потоки")
    if r.route_hits > 0:
        extra.append("повторяющийся маршрут")
    if extra:
        reasons.append(", ".join(extra))
    if r.is_seed:
        reasons.append("seed уже в деле, приоритет снижен")
    head = f"{C.ROLE_LABEL[r.role]}. {r.evidence.rstrip('.')}."
    tail = ("Почему в топе: " + "; ".join(reasons) + ".") if reasons else ""
    return cut(f"{head} {tail}", 400)


def top_table(df: pd.DataFrame, comp: pd.DataFrame, n: int = C.TOP_N) -> pd.DataFrame:
    ordered = df.sort_values(["priority_score", "in_kzt"], ascending=[False, False])
    rows = []
    for rank, (gid, r) in enumerate(ordered.head(n).iterrows(), start=1):
        rows.append({
            "rank": rank,
            "gid": int(gid),
            "role": r.role,
            "priority_score": float(r.priority_score),
            "why": _why(r, comp.loc[gid], rank),
            "cluster_id": int(r.cluster_id),
            "is_seed": bool(r.is_seed),
        })
    return pd.DataFrame(rows)
