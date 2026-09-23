"""Роли по формальным правилам. Порядок проверки сверху вниз, первое совпадение побеждает.

Каждое правило даёт: роль из словаря ТЗ, уверенность role_score 0..1 и обоснование с числами.
Для seed не используем «отдал / получил»: входящие seed в выгрузке занижены.
"""
from __future__ import annotations

import math

import networkx as nx
import numpy as np
import pandas as pd

from . import config as C
from .fmt import cut, kzt, pct, plural


def _ramp(x: float, lo: float, hi: float) -> float:
    """0.5 на пороге, 1.0 на «сильном» уровне."""
    if hi <= lo:
        return 1.0
    return float(min(1.0, max(0.5, 0.5 + 0.5 * (x - lo) / (hi - lo))))


def _payers(n: int) -> str:
    return f"{n} {plural(n, 'плательщика', 'плательщиков', 'плательщиков')}"


def _recips(n: int) -> str:
    return f"{n} {plural(n, 'получателю', 'получателям', 'получателям')}"


def _base_role(r: pd.Series) -> tuple[str, float, str, str]:
    """Первый проход: роль по собственным метрикам узла. Возвращает (role, score, evidence, rule_id)."""
    seed = bool(r.is_seed)
    pt = r.pass_through
    tag = "seed. " if seed else ""

    if r.isolated:
        text = ("Seed без внутрибанковских переводов от 5 000 ₸ в июле: связей в выборке нет. "
                "Признаков роли по данным нет, нужны другие источники.") if seed else "Нет переводов в выборке."
        return "peripheral", 0.9, text, "isolated"

    if r.in_deg >= C.HUB_IN and r.out_deg >= C.HUB_OUT:
        score = _ramp(min(r.in_deg, r.out_deg), C.HUB_IN, 3 * C.HUB_IN)
        text = (f"{tag}Собирает от {_payers(r.in_deg)} {kzt(r.in_kzt)} и рассылает {_recips(r.out_deg)} "
                f"{kzt(r.out_kzt)}; сюда ведут пути от {r.seeds_upstream} seed. Признаки координации.")
        return "coordinator", score, text, "hub"

    if r.out_deg >= C.FAN_OUT:
        avg = r.out_kzt / r.out_deg if r.out_deg else 0
        score = _ramp(r.out_deg, C.FAN_OUT, 6 * C.FAN_OUT)
        text = (f"{tag}Рассылает {_recips(r.out_deg)} {kzt(r.out_kzt)}, в среднем {kzt(avg)} на получателя; "
                f"входящих плательщиков {r.in_deg}. Признаки веерного распределения.")
        return "distributor", score, text, "fan_out"

    by_seeds = r.in_deg >= C.FAN_IN_SEED and r.seed_payers >= C.SEED_PAYERS
    if r.in_deg >= C.FAN_IN or by_seeds:
        score = _ramp(r.in_deg, C.FAN_IN, 3 * C.FAN_IN) if r.in_deg >= C.FAN_IN else 0.6
        seed_part = f" (из них seed: {r.seed_payers})" if r.seed_payers else ""
        if r.cutoff:
            tail = "исходящие не собраны (4-е колено, обрыв выборки)"
        elif seed or math.isnan(pt):
            tail = f"дальше отдаёт {kzt(r.out_kzt)} {_recips(r.out_deg)}"
        elif pt > C.TRANSIT_HI:
            tail = f"отдаёт больше полученного в выборке ({kzt(r.out_kzt)}): есть источники вне данных"
        else:
            tail = f"дальше отдаёт {pct(pt)} ({kzt(r.out_kzt)})"
        text = f"{tag}Получает от {_payers(r.in_deg)}{seed_part} {kzt(r.in_kzt)}; {tail}. Признаки консолидации."
        return "consolidator", score, text, "fan_in_seed" if (by_seeds and r.in_deg < C.FAN_IN) else "fan_in"

    if (not seed) and not math.isnan(pt) and C.TRANSIT_LO <= pt <= C.TRANSIT_HI and r.out_deg > 0:
        score = 1.0 - 0.5 * abs(pt - 1.0) / (C.TRANSIT_HI - 1.0)
        fast = r.fast_out_share if not math.isnan(r.fast_out_share) else 0.0
        fast_part = f"; {pct(fast)} ушло в течение {C.FAST_DAYS} дней" if fast > 0 else ""
        if r.fast_transit:
            score = min(1.0, score + 0.1)
        text = (f"Получил {kzt(r.in_kzt)} от {_payers(r.in_deg)}, передал дальше {pct(pt)} ({kzt(r.out_kzt)}) "
                f"{_recips(r.out_deg)}{fast_part}. Признаки транзита.")
        return "transit", float(score), text, "pass_through"

    keeps = r.out_deg == 0 or ((not seed) and not math.isnan(pt) and pt <= C.TERMINAL_PT)
    enough = r.in_kzt >= C.TERMINAL_MIN_KZT or r.in_deg >= C.TERMINAL_MIN_PAYERS
    if keeps and enough and r.depth < C.MAX_DEPTH and r.in_deg > 0:
        score = _ramp(math.log10(max(r.in_kzt, 1.0)), math.log10(C.TERMINAL_MIN_KZT), 6.0)
        if r.out_deg == 0:
            tail = f"исходящих от 5 000 ₸ в июле нет (колено {r.depth})"
        else:
            tail = f"дальше ушло только {pct(pt)}"
        text = f"{tag}Получил {kzt(r.in_kzt)} от {_payers(r.in_deg)}, {tail}. Деньги остаются."
        return "terminal", score, text, "keeps"

    if r.cutoff:
        prob = r.get("forward_prob", np.nan)
        prob_part = (f" Похожие узлы 1-3 колена пересылают дальше в {pct(prob)} случаев."
                     if prob is not None and not (isinstance(prob, float) and math.isnan(prob)) else "")
        text = (f"4-е колено: исходящие не собирались (обрыв выборки). Вход {kzt(r.in_kzt)} от "
                f"{_payers(r.in_deg)}. Конечным получателем не считаем.{prob_part}")
        return "peripheral", 0.4, text, "cutoff"

    signals = max(r.in_deg / C.FAN_IN, r.out_deg / C.FAN_OUT, 0.0)
    score = float(max(0.5, 1.0 - 0.5 * min(1.0, signals)))
    text = (f"{tag}Вход {kzt(r.in_kzt)} от {_payers(r.in_deg)}, выход {kzt(r.out_kzt)} {_recips(r.out_deg)}. "
            f"Пороги ролей не достигнуты, признаков роли нет.")
    return "peripheral", score, text, "none"


def cutoff_forward_prob(df: pd.DataFrame) -> pd.Series:
    """Учёт обрыва 4-го колена: доля узлов 1-3 колена с похожим входом, которые переслали деньги дальше.

    Похожесть: число плательщиков (1, 2, 3+) и корзина суммы входа (до 50 тыс., до 300 тыс., больше).
    """
    ref = df[(~df["is_seed"]) & (df["depth"].between(1, C.MAX_DEPTH - 1)) & (df["in_deg"] > 0)].copy()

    def key(frame: pd.DataFrame) -> pd.Series:
        payers = frame["in_deg"].clip(upper=3).astype(int).astype(str)
        amount = pd.cut(frame["in_kzt"], [-1, 50_000, 300_000, float("inf")], labels=["s", "m", "l"]).astype(str)
        return payers + amount

    ref["k"] = key(ref)
    rate = ref.groupby("k")["out_deg"].apply(lambda s: float((s > 0).mean()))
    cut_nodes = df[df["cutoff"]]
    return key(cut_nodes).map(rate).astype(float)


def assign_roles(df: pd.DataFrame, G: nx.DiGraph) -> pd.DataFrame:
    df = df.copy()
    df["forward_prob"] = np.nan
    fp = cutoff_forward_prob(df)
    df.loc[fp.index, "forward_prob"] = fp

    out = df.apply(_base_role, axis=1, result_type="expand")
    out.columns = ["role", "role_score", "evidence", "rule"]
    df = df.join(out)

    # второй проход: получатель денег от нескольких точек консолидации = кандидат в организаторы
    cons = set(df.index[df["role"] == "consolidator"])
    from_cons = {n: [p for p in G.predecessors(n) if p in cons] for n in df.index}
    df["from_consolidators"] = pd.Series({n: len(v) for n, v in from_cons.items()})
    upgrade = (df["from_consolidators"] >= C.COORD_FROM_CONS) & (df["role"] != "coordinator")
    for n in df.index[upgrade]:
        r = df.loc[n]
        amount = sum(G[p][n]["sum_kzt"] for p in from_cons[n])
        tag = "seed. " if r.is_seed else ""
        df.at[n, "evidence"] = (f"{tag}Получает от {r.from_consolidators} точек консолидации {kzt(amount)}; "
                                f"всего плательщиков {r.in_deg}, получателей {r.out_deg}. Кандидат в организаторы.")
        df.at[n, "role"] = "coordinator"
        df.at[n, "role_score"] = _ramp(r.from_consolidators, C.COORD_FROM_CONS, 2 * C.COORD_FROM_CONS)
        df.at[n, "rule"] = "from_consolidators"

    # не seed, но отдаёт больше, чем получил в выборке: входящие извне выборки не видны (ловушка ТЗ)
    extra = "Отдаёт больше, чем получил в выборке: есть источники вне данных."
    mask = (~df["is_seed"]) & (df["pass_through"] > C.TRANSIT_HI) & df["role"].isin(["coordinator", "distributor", "peripheral"])
    for n in df.index[mask]:
        text = f"{df.at[n, 'evidence']} {extra}"
        if len(text) <= 200:
            df.at[n, "evidence"] = text
    df["evidence"] = df["evidence"].map(cut)
    df["role_score"] = df["role_score"].astype(float).round(3)
    return df


def flags(r: pd.Series) -> list[str]:
    f = []
    if r.is_seed:
        f.append("seed")
    if r.cutoff:
        f.append("cutoff_depth4")
    if r.isolated:
        f.append("isolated")
    if r.fast_transit:
        f.append("fast_transit")
    if r.sync_inflow:
        f.append("sync_inflow")
    if r.n_cycles > 0:
        f.append("cycle")
    if r.n_mutual > 0:
        f.append("mutual_transfers")
    if r.route_hits > 0:
        f.append("recurring_route")
    return f
