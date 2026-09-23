"""Раскладка схемы: кластеры отдельными «островами», внутри кластера spring layout. seed=42, без случайности."""
from __future__ import annotations

import math
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

from . import config as C


def _spring(g: nx.Graph, **kw) -> dict:
    """spring_layout; для графов от 500 узлов networkx берёт scipy. Без scipy раскладываем по кругу."""
    try:
        return nx.spring_layout(g, seed=C.SEED, **kw)
    except ImportError:
        return nx.circular_layout(g)


def cluster_layout(U: nx.Graph, cluster_of: dict[int, int], unit: float = 18.0) -> dict[int, tuple[float, float]]:
    """Кластеры как острова: самый большой в центре, остальные по спирали без наложений. Внутри острова spring layout."""
    members: dict[int, list[int]] = defaultdict(list)
    for n, c in cluster_of.items():
        members[c].append(n)
    radius = {c: unit * math.sqrt(len(ns)) + unit for c, ns in members.items()}
    order = sorted((c for c in members if c != 0), key=lambda c: (-len(members[c]), c))

    placed: list[tuple[float, float, float]] = []  # (x, y, r)
    centers: dict[int, tuple[float, float]] = {}
    for c in order:
        r = radius[c]
        theta = 0.0
        while True:
            dist = unit * 1.2 * theta
            x, y = dist * math.cos(theta), dist * math.sin(theta)
            if all(math.hypot(x - px, y - py) >= r + pr + unit for px, py, pr in placed):
                break
            theta += 0.05
        placed.append((x, y, r))
        centers[c] = (x, y)

    pos: dict[int, tuple[float, float]] = {}
    for c in order:
        cx, cy = centers[c]
        ns = members[c]
        if len(ns) == 1:
            pos[ns[0]] = (cx, cy)
            continue
        sub = _spring(U.subgraph(ns), iterations=80)
        arr = np.array(list(sub.values()))
        span = float(np.abs(arr).max()) or 1.0
        r = radius[c] - unit / 2
        for n, (x, y) in sub.items():
            pos[n] = (float(cx + x / span * r), float(cy + y / span * r))

    # узлы без связей: аккуратная сетка справа от схемы
    lonely = sorted(members.get(0, []))
    if lonely:
        xs = [p[0] for p in pos.values()] or [0.0]
        ys = [p[1] for p in pos.values()] or [0.0]
        x0, y0 = max(xs) + 4 * unit, min(ys)
        cols = max(1, int(math.sqrt(len(lonely))))
        for i, n in enumerate(lonely):
            pos[n] = (x0 + (i % cols) * 2 * unit, y0 + (i // cols) * 2 * unit)
    return pos


def to_frame(pos: dict[int, tuple[float, float]]) -> pd.DataFrame:
    return pd.DataFrame({"x": {n: round(p[0], 1) for n, p in pos.items()},
                         "y": {n: round(p[1], 1) for n, p in pos.items()}})
