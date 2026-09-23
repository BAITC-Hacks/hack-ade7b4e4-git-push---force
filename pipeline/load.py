"""Загрузка трёх parquet и проверки консистентности (по мотивам стартового кода организаторов)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data_dir = Path(data_dir)
    missing = [f for f in ("edges.parquet", "nodes.parquet", "transactions.parquet") if not (data_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"В {data_dir} нет файлов: {', '.join(missing)}")
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    edges["src"] = edges["src"].astype("int64")
    edges["dst"] = edges["dst"].astype("int64")
    nodes["gid"] = nodes["gid"].astype("int64")
    nodes["is_seed"] = nodes["is_seed"].astype(bool)
    tx["src"] = tx["src"].astype("int64")
    tx["dst"] = tx["dst"].astype("int64")
    tx["date"] = pd.to_datetime(tx["date"])
    return edges, nodes, tx


def sanity(edges: pd.DataFrame, nodes: pd.DataFrame, tx: pd.DataFrame) -> dict:
    """Проверки до расчёта. Возвращает сводку, падает только на настоящей несогласованности."""
    agg = tx.groupby(["src", "dst"]).agg(s=("sum_kzt", "sum"), c=("sum_kzt", "size")).reset_index()
    merged = edges.merge(agg, on=["src", "dst"], how="outer", indicator=True)
    if not (merged["_merge"] == "both").all():
        raise ValueError("edges и transactions не сходятся по парам плательщик -> получатель")
    in_edges = set(edges["src"]) | set(edges["dst"])
    unknown = in_edges - set(nodes["gid"])
    if unknown:
        raise ValueError(f"{len(unknown)} gid из рёбер отсутствуют в nodes.parquet")
    seeds = set(nodes.loc[nodes["is_seed"], "gid"])
    return {
        "n_nodes": int(len(nodes)),
        "n_edges": int(len(edges)),
        "n_tx": int(len(tx)),
        "n_seed": int(len(seeds)),
        "turnover_kzt": float(edges["sum_kzt"].sum()),
        "period": f"{tx['date'].min().date()}..{tx['date'].max().date()}",
        "isolated_nodes": int(len(set(nodes["gid"]) - in_edges)),
        "seeds_without_out": int(len(seeds - set(edges["src"]))),
    }
