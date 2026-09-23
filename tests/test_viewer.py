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


def test_browser_offline_interactions(tmp_path):
    """Use an existing browser, without a server or extra Python packages."""
    candidates = [shutil.which("chromium"), shutil.which("google-chrome"),
                  str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe")]
    browser = next((p for p in candidates if p and Path(p).is_file()), None)
    if browser is None:
        pytest.skip("No local Chromium browser available")
    target = tmp_path / "viewer.html"
    build_viewer(SAMPLE, target)
    probe = r'''
<script>
window.addEventListener("load", () => {
  const results = [];
  const check = (name, condition) => results.push([name, Boolean(condition)]);
  const $ = id => document.getElementById(id);
  try {
    const g = JSON.parse($("graph-data").textContent);
    check("canvas", $("network").querySelector("canvas"));
    check("deep link", $("details").textContent.includes(g.nodes[0].id));
    $("search").value = g.nodes[0].id.slice(0,-2);
    $("search").dispatchEvent(new Event("input"));
    check("prefix", $("search-results").querySelectorAll("a").length > 1);
    $("cluster").value = "2";
    $("cluster").dispatchEvent(new Event("change"));
    $("hide-peripheral").checked = true;
    $("hide-peripheral").dispatchEvent(new Event("change"));
    $("search").value = g.nodes[0].id;
    $("search-form").dispatchEvent(new Event("submit", {cancelable:true}));
    check("exact gid", $("details").textContent.includes(g.nodes[0].id));
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
  output.textContent = JSON.stringify(results);
  document.body.append(output);
});
</script>'''
    target.write_text(target.read_text(encoding="utf-8").replace("</body>",probe+"</body>"),encoding="utf-8")
    gid = json.loads(SAMPLE.read_text(encoding="utf-8"))["nodes"][0]["id"]
    result = subprocess.run([browser,"--headless","--disable-gpu","--no-first-run","--no-default-browser-check",
                             "--disable-background-networking",f"--user-data-dir={tmp_path / 'profile'}",
                             "--dump-dom","--timeout=10000",target.as_uri()+"#gid="+gid],capture_output=True,encoding="utf-8",timeout=40)
    match = re.search(r'<pre id="browser-results">(.*?)</pre>',result.stdout,re.S)
    assert match, result.stderr[-3000:]
    results = json.loads(html_module.unescape(match[1]))
    assert len(results) >= 9, results
    assert all(passed for _,passed in results), results
