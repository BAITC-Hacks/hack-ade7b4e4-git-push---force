"""Offline build, contract preservation and untrusted text regression tests."""

import json
import html as html_module
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys

import pytest

from viewer.build import build_viewer


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "viewer" / "sample_graph.json"


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts = []
        self.resources = []
        self.data = ""
        self.in_data = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_data = attrs.get("id") == "graph-data"
        if "src" in attrs or tag == "link":
            self.resources.append(attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False

    def handle_data(self, data):
        if self.in_data:
            self.data += data


def test_build_is_self_contained_and_preserves_data(tmp_path):
    target = tmp_path / "nested" / "viewer.html"
    build_viewer(SAMPLE, target)
    html = target.read_text(encoding="utf-8")
    doc = Document(html)
    expected = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert json.loads(doc.data) == expected
    assert len(doc.scripts) == 3
    assert not doc.resources
    assert "vis-network" in html and "new vis.Network" in html
    assert "connect-src 'none'" in html
    assert "@@GRAPH@@" not in html
    assert 'id="blocking-panel"' in html
    assert 'id="blocking-reset"' in html
    assert all(f'data-block-top="{n}"' in html for n in (5, 10, 20))
    assert 'href="report.html"' in html
    assert all(isinstance(n["id"], str) for n in expected["nodes"])
    assert expected["nodes"][0]["id"] != expected["nodes"][1]["id"]
    assert int(expected["nodes"][0]["id"]) > 2**53
    second = tmp_path / "second.html"
    build_viewer(SAMPLE, second)
    assert second.read_bytes() == target.read_bytes()


def test_cli(tmp_path):
    target = tmp_path / "viewer.html"
    result = subprocess.run([sys.executable, "-m", "viewer.build", "--graph", str(SAMPLE), "--out", str(target)],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert target.is_file()


def test_data_cannot_escape_script(tmp_path):
    graph = json.loads(SAMPLE.read_text(encoding="utf-8"))
    payload = '</script><script src="https://invalid.example/evil.js"></script>@@APP@@ & <b>'
    graph["nodes"][0]["evidence"] = payload
    source = tmp_path / "graph.json"
    source.write_text(json.dumps(graph),encoding="utf-8")
    target = tmp_path / "viewer.html"
    build_viewer(source,target)
    doc = Document(target.read_text(encoding="utf-8"))
    assert len(doc.scripts) == 3
    assert not doc.resources
    assert json.loads(doc.data)["nodes"][0]["evidence"] == payload


@pytest.mark.parametrize("mutation", ["numeric_gid", "duplicate_gid", "unknown_edge", "numeric_top", "numeric_cluster_gid"])
def test_reject_broken_identifiers(tmp_path,mutation):
    graph = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if mutation == "numeric_gid": graph["nodes"][0]["id"] = int(graph["nodes"][0]["id"])
    if mutation == "duplicate_gid": graph["nodes"][1]["id"] = graph["nodes"][0]["id"]
    if mutation == "unknown_edge": graph["edges"][0]["target"] = "missing"
    if mutation == "numeric_top": graph["top"][0]["gid"] = int(graph["top"][0]["gid"])
    if mutation == "numeric_cluster_gid": graph["clusters"][0]["top_gids"][0] = 123
    source = tmp_path / "graph.json"
    source.write_text(json.dumps(graph),encoding="utf-8")
    with pytest.raises(ValueError): build_viewer(source,tmp_path / "viewer.html")


def test_sample_metrics_match_edges():
    graph = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert 10 <= len(graph["nodes"]) <= 15
    assert graph["meta"]["n_nodes"] == len(graph["nodes"])
    assert graph["meta"]["n_edges"] == len(graph["edges"])
    assert graph["meta"]["turnover_kzt"] == sum(e["sum_kzt"] for e in graph["edges"])
    for n in graph["nodes"]:
        inc = [e for e in graph["edges"] if e["target"] == n["id"]]
        out = [e for e in graph["edges"] if e["source"] == n["id"]]
        assert n["in_deg"] == len(inc)
        assert n["out_deg"] == len(out)
        assert n["in_kzt"] == sum(e["sum_kzt"] for e in inc)
        assert n["out_kzt"] == sum(e["sum_kzt"] for e in out)


@pytest.mark.parametrize("dataset", ["sample", "real"])
def test_browser_offline_interactions(tmp_path, dataset):
    """Use an existing browser, without a server or extra Python packages."""
    candidates = [shutil.which("chromium"), shutil.which("google-chrome"),
                  str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe")]
    browser = next((p for p in candidates if p and Path(p).is_file()), None)
    if browser is None:
        pytest.skip("No local Chromium browser available")
    source = SAMPLE if dataset == "sample" else ROOT / "out" / "graph.json"
    if not source.is_file():
        pytest.skip("Real graph is not available locally")
    graph = json.loads(source.read_text(encoding="utf-8"))
    if dataset == "sample":
        graph["nodes"][0]["card"] = 'Первая строка\nВторая строка\n<img src="invalid" onerror="alert(1)">'
        graph["clusters"][0]["stability"] = 0.87
        source = tmp_path / "graph.json"
        source.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    else:
        assert len(graph["nodes"]) == 2248
        assert all(isinstance(n.get("card"), str) for n in graph["nodes"])
        assert all("stability" in c for c in graph["clusters"])
    target = tmp_path / "viewer.html"
    build_viewer(source, target)
    probe = r'''
<script>
window.addEventListener("load", () => {
  const timings = {open_ms: performance.now()};
  const results = [];
  const scenarios = {};
  const check = (name, condition) => results.push([name, Boolean(condition)]);
  const $ = id => document.getElementById(id);
  try {
    const g = JSON.parse($("graph-data").textContent);
    const snapshot = name => {
      scenarios[name] = Object.fromEntries([...$("blocking-results").querySelectorAll("[data-metric]")].map(row => [row.dataset.metric, Number(row.dataset.after)]));
    };
    snapshot("baseline");
    const stats = [...$("headline-stats").querySelectorAll("strong")].map(n => Number(n.textContent.replace(/\s/g,"")));
    check("summary", stats[0] === g.meta.n_seed && stats[1] === g.meta.n_nodes && stats[2] === g.top.length);
    check("role counts", g.roles.every((role,i) => stats[i+3] === (role.count ?? g.nodes.filter(n => n.role === role.key).length)));
    check("report link", document.querySelector('a[href="report.html"]'));
    check("canvas", $("network").querySelector("canvas"));
    check("deep link", $("details").textContent.includes(g.nodes[0].id));
    const card = $("details").querySelector(".node-card");
    check("card text", card && card.textContent === g.nodes[0].card);
    check("card newlines", card && getComputedStyle(card).whiteSpace === "pre-wrap");
    check("card not HTML", card && !card.querySelector("img"));
    const cluster = g.clusters.find(c => c.cluster_id === g.nodes[0].cluster_id);
    const clusterMetric = [...$("details").querySelectorAll(".metric")].find(m => m.querySelector("dt").textContent === "Кластер");
    const stability = new Intl.NumberFormat("ru-RU", {maximumFractionDigits:2}).format(cluster.stability);
    check("node cluster stability", clusterMetric.textContent.includes(`стабильность: ${stability}`));
    const blockingStart = performance.now();
    for(const count of [5,10,20]) {
      document.querySelector(`[data-block-top="${count}"]`).click(); snapshot(`top${count}`);
    }
    timings.blocking_ms = performance.now() - blockingStart;
    $("blocking-reset").click(); snapshot("reset");
    $("details").querySelector(".block-node").click(); snapshot("single");
    check("block button disabled", $("details").querySelector(".block-node").disabled);
    $("cluster").value = String(cluster.cluster_id);
    $("cluster").dispatchEvent(new Event("change"));
    check("filter cluster stability", $("cluster-info").textContent.includes(`стабильность: ${stability}`));
    snapshot("single_filtered");
    $("blocking-reset").click();
    $("search").value = g.nodes[0].id.slice(0,1);
    $("search").dispatchEvent(new Event("input"));
    check("prefix", $("search-results").querySelectorAll("a").length > 1);
    const target = g.nodes.find(n => n.role === "peripheral" && g.edges.some(e => e.source === n.id || e.target === n.id));
    $("cluster").value = String(g.clusters.find(c => c.cluster_id !== target.cluster_id).cluster_id);
    $("cluster").dispatchEvent(new Event("change"));
    $("hide-peripheral").checked = true;
    $("hide-peripheral").dispatchEvent(new Event("change"));
    $("search").value = target.id;
    const searchStart = performance.now();
    $("search-form").dispatchEvent(new Event("submit", {cancelable:true}));
    timings.search_ms = performance.now() - searchStart;
    check("exact gid", $("details").querySelector("h2").textContent === target.id);
    check("reveal hidden", $("cluster").value === "" && !$("hide-peripheral").checked);
    const neighbor = $("details").querySelector("a");
    const neighborId = neighbor.textContent;
    neighbor.click();
    check("counterparty click", $("details").querySelector("h2").textContent === neighborId);
    $("top").querySelector("a").click();
    check("top click", $("details").querySelector("h2").textContent === g.top[0].gid);
    $("color-mode").value = "cluster";
    $("color-mode").dispatchEvent(new Event("change"));
    $("reset").click();
    check("reset", $("details").textContent.includes("Выберите узел"));
    $("search").value = "missing";
    $("search-form").dispatchEvent(new Event("submit", {cancelable:true}));
    check("missing gid", $("status").textContent.includes("Совпадений нет"));
  } catch(error) { results.push([String(error),false]); }
  const output = document.createElement("pre");
  output.id = "browser-results";
  output.textContent = JSON.stringify({results, timings, scenarios});
  document.body.append(output);
});
</script>'''
    target.write_text(target.read_text(encoding="utf-8").replace("</body>",probe+"</body>"),encoding="utf-8")
    gid = graph["nodes"][0]["id"]
    result = subprocess.run([browser,"--headless","--disable-gpu","--no-first-run","--no-default-browser-check",
                             "--disable-background-networking",f"--user-data-dir={tmp_path / 'profile'}",
                             "--dump-dom","--timeout=10000",target.as_uri()+"#gid="+gid],capture_output=True,encoding="utf-8",timeout=40)
    match = re.search(r'<pre id="browser-results">(.*?)</pre>',result.stdout,re.S)
    assert match, result.stderr[-3000:]
    report = json.loads(html_module.unescape(match[1]))
    results = report["results"]
    print(f"{dataset}: {len(graph['nodes'])} nodes; {report['timings']}")
    assert report["timings"]["open_ms"] < 5000, report
    assert report["timings"]["search_ms"] < 1000, report
    assert len(results) >= 9, results
    assert all(passed for _,passed in results), results
    ordered = sorted(graph["top"], key=lambda n: n["rank"])
    for scenario, gids in {
        "baseline": set(), "reset": set(),
        "single": {gid}, "single_filtered": {gid},
        **{f"top{count}": {n["gid"] for n in ordered[:count]} for count in (5, 10, 20)},
    }.items():
        expected = reference_blocking(graph, gids)
        assert report["scenarios"][scenario] == pytest.approx(expected), (scenario, report)


def reference_blocking(graph, blocked):
    """Independent union-find oracle for browser traversal results."""
    parent = {n["id"]: n["id"] for n in graph["nodes"] if n["id"] not in blocked}
    def root(gid):
        while parent[gid] != gid:
            gid = parent[gid]
        return gid
    total = affected = 0
    for edge in graph["edges"]:
        total += edge["sum_kzt"]
        if edge["source"] in blocked or edge["target"] in blocked:
            affected += edge["sum_kzt"]
        else:
            parent[root(edge["source"])] = root(edge["target"])
    sizes = {}
    for gid in parent:
        component = root(gid)
        sizes[component] = sizes.get(component, 0) + 1
    return {"largest": max(sizes.values(), default=0), "fragments": len(sizes),
            "turnover": affected / total * 100 if total else 0}


def test_blocking_edge_cases():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    # Converging arrows, reciprocal edge, self-loop, isolated vertex, zero turnover.
    graph = {"nodes": [{"id": gid} for gid in ("a", "b", "c", "isolated")], "edges": [
        {"source": "a", "target": "b", "sum_kzt": 10},
        {"source": "c", "target": "b", "sum_kzt": 20},
        {"source": "b", "target": "a", "sum_kzt": 30},
        {"source": "a", "target": "a", "sum_kzt": 40},
    ]}
    cases = [(graph, []), (graph, ["b"]), (graph, ["a", "b"]),
             (graph, ["a", "b", "c", "isolated"]), (graph, ["isolated"]),
             ({"nodes": graph["nodes"], "edges": []}, ["a"]), ({"nodes": [], "edges": []}, [])]
    script = "const {measureBlocking}=require('./viewer/what_if.js'); const fs=require('fs'); const cases=JSON.parse(fs.readFileSync(0,'utf8')); console.log(JSON.stringify(cases.map(([g,ids])=>measureBlocking(g,new Set(ids)))));"
    result = subprocess.run([node, "-e", script], input=json.dumps(cases), cwd=ROOT, capture_output=True, text=True, check=True)
    for actual, (data, ids) in zip(json.loads(result.stdout), cases):
        expected = reference_blocking(data, set(ids))
        assert actual == pytest.approx({"largest": expected["largest"], "fragments": expected["fragments"], "affectedPercent": expected["turnover"]})
