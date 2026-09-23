"""Карточка узла: короткая справка для аналитика. Строится правилами из посчитанных метрик, без LLM."""
from __future__ import annotations

import math

import networkx as nx
import pandas as pd

from . import config as C
from .fmt import kzt, pct, plural

HINT = {
    "coordinator": "Проверить связи с точками консолидации и распределителями кластера, запросить входящие вне выборки.",
    "consolidator": "Проверить, от кого идут поступления (особенно от seed) и куда уходит остаток.",
    "distributor": "Проверить получателей веера: повторяющиеся суммы, снятия наличных, связи с seed.",
    "transit": "Восстановить цепочку: откуда пришли деньги и куда ушли в течение 2 дней.",
    "terminal": "Запросить снятия наличных, межбанковские и карточные операции: деньги оседают здесь.",
    "peripheral": "Низкий приоритет. Вернуться, если появятся новые данные.",
}

RULE_CHECK = {
    "hub": lambda r: f"плательщиков {r.in_deg} (порог {C.HUB_IN}) и получателей {r.out_deg} (порог {C.HUB_OUT})",
    "from_consolidators": lambda r: f"получает от {r.from_consolidators} точек консолидации (порог {C.COORD_FROM_CONS})",
    "fan_out": lambda r: f"получателей {r.out_deg} (порог {C.FAN_OUT})",
    "fan_in": lambda r: f"плательщиков {r.in_deg} (порог {C.FAN_IN})",
    "fan_in_seed": lambda r: f"плательщиков {r.in_deg} (порог {C.FAN_IN_SEED}), из них seed {r.seed_payers} (порог {C.SEED_PAYERS})",
    "pass_through": lambda r: f"пропуск {pct(r.pass_through)} (коридор {int(C.TRANSIT_LO * 100)}-{int(C.TRANSIT_HI * 100)}%)",
    "keeps": lambda r: f"дальше ушло {pct(r.pass_through) if not math.isnan(r.pass_through) else '0%'} (порог {int(C.TERMINAL_PT * 100)}%), колено {r.depth}",
    "cutoff": lambda r: "4-е колено без исходящих: обрыв выборки",
    "isolated": lambda r: "нет переводов в выборке",
    "none": lambda r: "пороги ролей не достигнуты",
}


def _top(pairs: list[tuple[int, float]], k: int = 3) -> str:
    pairs = sorted(pairs, key=lambda p: -p[1])[:k]
    return ", ".join(f"{g} ({kzt(s)})" for g, s in pairs) if pairs else "нет"


def card(gid: int, r: pd.Series, G: nx.DiGraph) -> str:
    ins = [(u, a["sum_kzt"]) for u, _, a in G.in_edges(gid, data=True)]
    outs = [(v, a["sum_kzt"]) for _, v, a in G.out_edges(gid, data=True)]
    rank = "вне топа" if pd.isna(r["rank"]) else f"№{int(r['rank'])}"
    seed = "seed" if r.is_seed else "не seed"
    if r.is_seed or math.isnan(r.pass_through):
        pt = ""
    elif r.pass_through > 2:
        pt = f", отдал в {r.pass_through:.1f} раза больше, чем получил в выборке".replace(".", ",", 1)
    else:
        pt = f", пропуск {pct(r.pass_through)}"
    signals = []
    if r.fast_transit:
        signals.append(f"сквозной транзит: {pct(r.fast_out_share)} ушло за {C.FAST_DAYS} дня")
    if r.sync_inflow:
        signals.append(f"{r.max_payers_same_day} {plural(r.max_payers_same_day, 'плательщик', 'плательщика', 'плательщиков')} в один день")
    if r.n_cycles:
        signals.append(f"возвратные потоки: {r.n_cycles} {plural(r.n_cycles, 'цикл', 'цикла', 'циклов')}")
    if r.route_hits:
        signals.append("повторяющийся маршрут A->B->C")
    if r.cutoff:
        signals.append(f"обрыв выборки, похожие узлы пересылают дальше в {pct(r.forward_prob)}")
    if r.cutoff:
        out_line = "Выход: не собирался (обрыв выборки на 4-м колене)."
        hint = "Запросить исходящие переводы за июль: узел на границе выборки, куда ушли деньги, не видно."
    elif r.isolated:
        out_line = "Выход: переводов в выборке нет."
        hint = "Запросить операции по другим каналам: переводы ниже 5 000 ₸, межбанковские, наличные."
    else:
        out_line = f"Выход: {kzt(r.out_kzt)} на {r.out_deg}{pt}."
        hint = HINT[r.role]
    lines = [
        f"Роль: {C.ROLE_LABEL[r.role]} (уверенность {r.role_score:.2f}). Правило: {RULE_CHECK.get(r.rule, lambda _: '')(r)}.",
        f"Приоритет {r.priority_score:.3f}, {rank}. Кластер {int(r.cluster_id)}, колено {int(r.depth)}, {seed}.",
        f"Вход: {kzt(r.in_kzt)} от {r.in_deg} (seed: {r.seed_payers}). {out_line}",
        f"Крупнейшие плательщики: {_top(ins)}.",
        f"Крупнейшие получатели: {_top(outs)}.",
        f"Сигналы: {'; '.join(signals) if signals else 'нет'}.",
        f"На что обратить внимание: {hint}",
    ]
    return "\n".join(lines)


def all_cards(df: pd.DataFrame, G: nx.DiGraph) -> pd.Series:
    return pd.Series({gid: card(gid, r, G) for gid, r in df.iterrows()})
