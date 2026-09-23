"""Проверки must have из ТЗ на настоящих данных: схема выгрузок, роли, кластеры, топ, скорость, детерминизм."""
from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import pytest

from pipeline import config as C
from pipeline.run import run

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
pytestmark = pytest.mark.skipif(not (DATA / "edges.parquet").exists(), reason="нет data/*.parquet")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("out")
    t = time.perf_counter()
    summary = run(DATA, d, build_viewer=False, log=lambda *_: None)
    summary["_elapsed"] = time.perf_counter() - t
    return d, summary


def test_three_files_fast(out):
    d, s = out
    for f in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv", "graph.json"):
        assert (d / f).exists(), f
    assert s["_elapsed"] < 300  # ТЗ: полный пересчёт до 5 минут


def test_nodes_roles_schema(out):
    d, _ = out
    n = pd.read_csv(d / "nodes_roles.csv")
    nodes = pd.read_parquet(DATA / "nodes.parquet")
    assert len(n) == len(nodes) == 2248
    assert set(n["gid"]) == set(nodes["gid"])
    for col in ("gid", "role", "role_score", "cluster_id", "priority_score", "evidence"):
        assert col in n.columns and n[col].notna().all(), col
    assert set(n["role"]) <= set(C.ROLES)
    assert n["role_score"].between(0, 1).all() and n["priority_score"].between(0, 1).all()
    ev = n["evidence"].astype(str)
    assert (ev.str.len() > 0).all() and (ev.str.len() <= 200).all()
    assert ev.str.contains(r"\d").all()  # в обосновании есть числа


def test_cutoff_nodes_are_not_terminal(out):
    d, _ = out
    n = pd.read_csv(d / "nodes_roles.csv")
    cut = n[(n["depth"] == 4) & (n["out_deg"] == 0)]
    assert len(cut) == 444
    assert not (cut["role"] == "terminal").any()


def test_clusters(out):
    d, _ = out
    n = pd.read_csv(d / "nodes_roles.csv")
    c = pd.read_csv(d / "clusters.csv")
    for col in ("cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"):
        assert col in c.columns and c[col].notna().all(), col
    assert set(n["cluster_id"]) == set(c["cluster_id"])
    assert c["n_nodes"].sum() == len(n)
    assert c["n_seed"].sum() == 81


def test_top_nodes(out):
    d, _ = out
    t = pd.read_csv(d / "top_nodes.csv")
    assert len(t) >= 20
    assert list(t["rank"]) == list(range(1, len(t) + 1))
    assert t["priority_score"].is_monotonic_decreasing
    assert t["why"].astype(str).str.len().gt(20).all()


def test_no_hardcoded_gids():
    for p in (ROOT / "pipeline").glob("*.py"):
        assert not re.search(r"\d{15,}", p.read_text(encoding="utf-8")), f"похоже на зашитый gid: {p.name}"


def test_deterministic(out, tmp_path):
    d, _ = out
    run(DATA, tmp_path, build_viewer=False, log=lambda *_: None)
    a = pd.read_csv(d / "nodes_roles.csv").sort_values("gid").reset_index(drop=True)
    b = pd.read_csv(tmp_path / "nodes_roles.csv").sort_values("gid").reset_index(drop=True)
    assert a[["gid", "role", "cluster_id"]].equals(b[["gid", "role", "cluster_id"]])


def test_report(out):
    d, _ = out
    html = (d / "report.html").read_text(encoding="utf-8")
    top1 = str(pd.read_csv(d / "top_nodes.csv")["gid"].iloc[0])
    assert top1 in html and "гипотез" in html.lower()
    assert "http://" not in html and "https://" not in html  # справка работает без интернета
