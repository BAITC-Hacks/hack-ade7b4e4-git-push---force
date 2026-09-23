"""Проверка масштабирования: синтетический граф той же схемы (edges, nodes, transactions) и замер пайплайна.

    python scripts/scale_test.py --nodes 50000 200000

Граф строится как выгрузка из ТЗ: seed, обход исходящих на 4 колена, веерные распределители, точки сбора,
транзакции от 5 000 ₸ за июль. Это не реальные данные, а нагрузочный тест. Пайплайн запускается в режиме --core
(роли, кластеры, приоритет, три CSV).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from pipeline.run import run  # noqa: E402

BASE = 10 ** 17


def synth(n_target: int, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_seed = max(81, n_target // 77)  # на выданных данных 81 seed дают 2 248 узлов; здесь рост с веерами ~77x
    counter = 0

    def new_gid() -> int:
        nonlocal counter
        counter += 1
        return BASE + counter * 100

    depth: dict[int, int] = {}
    seeds = [new_gid() for _ in range(n_seed)]
    for g in seeds:
        depth[g] = 0
    collectors: list[int] = []
    pairs: dict[tuple[int, int], int] = {}
    level = seeds
    for d in range(1, 5):
        nxt = []
        for s in level:
            k = int(rng.poisson(2.0))
            if rng.random() < 0.02:
                k += int(rng.integers(10, 80))  # веерный распределитель
            for _ in range(k):
                if collectors and rng.random() < 0.12:
                    t = collectors[int(rng.integers(len(collectors)))]  # точка сбора: вход от многих
                else:
                    t = new_gid()
                    depth[t] = d
                    nxt.append(t)
                    if rng.random() < 0.01:
                        collectors.append(t)
                if t != s:
                    pairs[(s, t)] = pairs.get((s, t), 0) + 1 + int(rng.poisson(0.6))
        level = nxt
    rows = []
    for (s, t), n in pairs.items():
        amounts = np.maximum(5_000, np.round(rng.lognormal(np.log(30_000), 1.1, n), -2))
        days = rng.integers(1, 32, n)
        for a, day in zip(amounts, days):
            rows.append((s, t, f"2026-07-{int(day):02d}", float(a)))
    tx = pd.DataFrame(rows, columns=["src", "dst", "date", "sum_kzt"])
    tx["date"] = pd.to_datetime(tx["date"]).dt.date
    edges = (tx.groupby(["src", "dst"]).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size")).reset_index())
    edges["depth"] = edges["dst"].map(depth).clip(lower=1).astype("int8")
    nodes = pd.DataFrame({"gid": list(depth), "depth": list(depth.values())})
    nodes["is_seed"] = nodes["depth"] == 0
    return edges, nodes, tx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[50_000])
    a = ap.parse_args()
    print(f"{'узлов':>9} {'рёбер':>9} {'транзакций':>11} {'генерация, с':>13} {'пайплайн --core, с':>19}")
    for n in a.nodes:
        t0 = time.perf_counter()
        edges, nodes, tx = synth(n)
        gen = time.perf_counter() - t0
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "data", Path(tmp) / "out"
            data.mkdir()
            edges.to_parquet(data / "edges.parquet", index=False)
            nodes.to_parquet(data / "nodes.parquet", index=False)
            tx.to_parquet(data / "transactions.parquet", index=False)
            t1 = time.perf_counter()
            summary = run(data, out, build_viewer=False, log=lambda *_: None, core_only=True)
            took = time.perf_counter() - t1
            assert len(pd.read_csv(out / "nodes_roles.csv")) == len(nodes)
        print(f"{len(nodes):>9} {len(edges):>9} {len(tx):>11} {gen:>13.1f} {took:>19.1f}", flush=True)
        print(f"          этапы (с от старта): {summary['timings_s']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
