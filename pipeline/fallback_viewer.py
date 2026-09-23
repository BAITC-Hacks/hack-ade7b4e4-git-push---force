"""Запасной экран: если модуль viewer/ ещё не готов или упал, собираем простой самодостаточный out/viewer.html.

Один HTML-файл: внутри vis-network из viewer/vendor/, данные graph.json и небольшой скрипт. Без сервера и интернета.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "viewer" / "vendor" / "vis-network.min.js"

CSS = """
*{box-sizing:border-box}body{margin:0;font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2933;background:#f5f7fa}
header{display:flex;gap:16px;align-items:center;padding:10px 16px;background:#fff;border-bottom:1px solid #e4e7eb}
header h1{font-size:17px;margin:0}header .meta{color:#616e7c;font-size:13px}
main{display:grid;grid-template-columns:300px 1fr 360px;grid-template-rows:minmax(0,1fr);height:calc(100vh - 52px);overflow:hidden}
aside{overflow:auto;min-height:0;background:#fff;padding:12px;border-right:1px solid #e4e7eb}aside.right{border-right:0;border-left:1px solid #e4e7eb}
#net{width:100%;height:100%;min-height:0;background:#fbfcfd}
input,select,button{font:inherit;padding:6px 8px;border:1px solid #cbd2d9;border-radius:6px;background:#fff}
input{width:100%}label{display:block;margin:8px 0 4px;color:#3e4c59;font-weight:600;font-size:13px}
.legend div{display:flex;gap:6px;align-items:flex-start;margin:4px 0;font-size:12px}.dot{width:12px;height:12px;border-radius:50%;flex:0 0 12px;margin-top:3px}
.top{list-style:none;margin:0;padding:0}.top li{padding:6px;border-radius:6px;cursor:pointer;font-size:12px;display:flex;gap:6px}
.top li:hover{background:#eef2f7}.gid{font-family:ui-monospace,Consolas,monospace;font-size:12px;cursor:pointer;color:#1d4ed8}
.card{white-space:pre-wrap;font-size:12.5px;background:#f5f7fa;border-radius:8px;padding:8px}
table{width:100%;border-collapse:collapse;font-size:12px}td{padding:3px 4px;border-bottom:1px solid #eef2f7}td.r{text-align:right;white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-size:12px}.muted{color:#7b8794;font-size:12px}
h3{margin:14px 0 6px;font-size:14px}
"""

JS = r"""
const G = DATA;
const roleColor = Object.fromEntries(G.roles.map(r => [r.key, r.color]));
const roleLabel = Object.fromEntries(G.roles.map(r => [r.key, r.label]));
const byId = new Map(G.nodes.map(n => [n.id, n]));
const inE = new Map(), outE = new Map();
G.edges.forEach(e => {
  (outE.get(e.source) || outE.set(e.source, []).get(e.source)).push(e);
  (inE.get(e.target) || inE.set(e.target, []).get(e.target)).push(e);
});
const fmt = x => (x == null ? "0" : Math.round(x).toLocaleString("ru-RU").replace(/,/g, " ")) + " ₸";
const palette = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac"];
let mode = "role", hidePeriph = false, clusterOnly = "";
function baseColor(n){ return mode === "role" ? roleColor[n.role] : (n.cluster_id === 0 ? "#cbd2d9" : palette[n.cluster_id % palette.length]); }
function visible(n){ return !(hidePeriph && n.role === "peripheral" && !n.is_seed) && !(clusterOnly !== "" && String(n.cluster_id) !== clusterOnly); }
const nodes = new vis.DataSet(G.nodes.map(n => ({
  id: n.id, x: n.x, y: n.y, size: 4 + 16 * (n.priority_score || 0),
  label: n.rank ? "№" + n.rank : undefined, color: baseColor(n),
  borderWidth: n.is_seed ? 2 : 1, shapeProperties: {borderDashes: false},
  title: `${n.id}\n${roleLabel[n.role]}\nприоритет ${(n.priority_score||0).toFixed(3)}`
})));
const edges = new vis.DataSet(G.edges.map((e, i) => ({
  id: i, from: e.source, to: e.target, arrows: "to",
  width: 0.4 + Math.log10(1 + e.sum_kzt / 5000), color: {color: "#9aa5b1", opacity: 0.45}
})));
const net = new vis.Network(document.getElementById("net"), {nodes, edges}, {
  physics: false, interaction: {hover: true, tooltipDelay: 120, hideEdgesOnDrag: true},
  nodes: {shape: "dot", font: {size: 11, color: "#1f2933"}, borderWidth: 1, color: {border: "#1f2933"}},
  edges: {smooth: false, arrows: {to: {scaleFactor: 0.35}}}
});
function repaint(focus){
  const nb = new Set();
  if (focus){ nb.add(focus); (inE.get(focus)||[]).forEach(e => nb.add(e.source)); (outE.get(focus)||[]).forEach(e => nb.add(e.target)); }
  nodes.update(G.nodes.map(n => ({id: n.id, hidden: !visible(n),
    color: focus && !nb.has(n.id) ? "#e4e7eb" : baseColor(n)})));
  edges.update(G.edges.map((e, i) => ({id: i,
    color: focus ? ((e.source === focus || e.target === focus) ? {color: "#1f2933", opacity: 0.9} : {color: "#e4e7eb", opacity: 0.2})
                 : {color: "#9aa5b1", opacity: 0.45}})));
}
function link(g){ return `<span class="gid" data-gid="${g}">${g}</span>`; }
function show(id){
  const n = byId.get(id); if (!n) return;
  location.hash = "gid=" + id;
  repaint(id); net.selectNodes([id]); net.focus(id, {scale: 1.3, animation: {duration: 400}});
  const ins = (inE.get(id)||[]).slice().sort((a,b) => b.sum_kzt - a.sum_kzt);
  const outs = (outE.get(id)||[]).slice().sort((a,b) => b.sum_kzt - a.sum_kzt);
  const rows = (list, key) => list.map(e => `<tr><td>${link(e[key])}</td><td class="r">${fmt(e.sum_kzt)}</td><td class="r">${e.n_tx} тр.</td></tr>`).join("") || `<tr><td class="muted">нет</td></tr>`;
  document.getElementById("panel").innerHTML = `
    <div class="gid">${n.id}</div>
    <p><span class="badge" style="background:${roleColor[n.role]}">${roleLabel[n.role]}</span>
    ${n.rank ? " <b>№" + n.rank + " в топе</b>" : ""}</p>
    <p class="muted">приоритет ${n.priority_score.toFixed(3)} · уверенность ${n.role_score.toFixed(2)} · кластер ${n.cluster_id} · колено ${n.depth}${n.is_seed ? " · seed" : ""}</p>
    <p>${n.evidence}</p>
    <div class="card">${n.card || ""}</div>
    <h3>Входящие (${ins.length})</h3><table>${rows(ins, "source")}</table>
    <h3>Исходящие (${outs.length})</h3><table>${rows(outs, "target")}</table>`;
}
document.addEventListener("click", ev => { const g = ev.target.dataset && ev.target.dataset.gid; if (g) show(g); });
net.on("click", p => { if (p.nodes.length) show(p.nodes[0]); else { repaint(null); } });
document.getElementById("q").addEventListener("keydown", ev => {
  if (ev.key !== "Enter") return;
  const q = ev.target.value.trim(); if (!q) return;
  const hit = byId.has(q) ? q : (G.nodes.find(n => n.id.startsWith(q)) || {}).id;
  if (hit) show(hit); else document.getElementById("panel").innerHTML = `<p>Узел ${q} не найден</p>`;
});
document.getElementById("mode").addEventListener("change", ev => { mode = ev.target.value; repaint(null); });
document.getElementById("periph").addEventListener("change", ev => { hidePeriph = ev.target.checked; repaint(null); });
const cs = document.getElementById("cluster");
G.clusters.forEach(c => cs.insertAdjacentHTML("beforeend", `<option value="${c.cluster_id}">${c.cluster_id}: ${c.n_nodes} узл., seed ${c.n_seed}</option>`));
cs.addEventListener("change", ev => { clusterOnly = ev.target.value; repaint(null); });
document.getElementById("legend").innerHTML = G.roles.map(r =>
  `<div><span class="dot" style="background:${r.color}"></span><span><b>${r.label}</b> (${r.count})<br><span class="muted">${r.rule}</span></span></div>`).join("");
document.getElementById("top").innerHTML = G.top.slice(0, 20).map(t =>
  `<li data-gid="${t.gid}"><b data-gid="${t.gid}">№${t.rank}</b><span data-gid="${t.gid}">${roleLabel[t.role]}<br><span class="gid" data-gid="${t.gid}">${t.gid}</span></span></li>`).join("");
const m = location.hash.match(/gid=(\d+)/); if (m) setTimeout(() => show(m[1]), 300);
"""

HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Граф денег: схема сети</title><style>{css}</style></head><body>
<header><h1>Граф денег</h1><span class="meta">{meta}</span></header>
<main>
<aside>
  <label for="q">Поиск по gid (Enter)</label><input id="q" placeholder="введите gid целиком или начало">
  <label for="mode">Цвет узлов</label><select id="mode"><option value="role">по роли</option><option value="cluster">по кластеру</option></select>
  <label><input type="checkbox" id="periph" style="width:auto"> скрыть периферию</label>
  <label for="cluster">Кластер</label><select id="cluster"><option value="">все</option></select>
  <h3>Топ-20: кого смотреть первым</h3><ul class="top" id="top"></ul>
  <h3>Роли и правила</h3><div class="legend" id="legend"></div>
</aside>
<div id="net"></div>
<aside class="right" id="panel"><p class="muted">Кликните узел на схеме, строку топа или найдите gid. Стрелки показывают направление денег, размер узла = приоритет, «№» = место в топе.</p></aside>
</main>
<script>{vis}</script>
<script>const DATA = {data};</script>
<script>{js}</script>
</body></html>"""


def build(graph_json: Path, out_html: Path) -> None:
    data = json.loads(Path(graph_json).read_text(encoding="utf-8"))
    m = data["meta"]
    meta = (f"{m['n_nodes']} узлов · {m['n_edges']} рёбер · {m['n_seed']} seed · период {m['period']} · "
            f"выводы являются гипотезами для проверки")
    html = HTML.format(css=CSS, meta=meta, vis=VENDOR.read_text(encoding="utf-8"),
                       data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), js=JS)
    Path(out_html).write_text(html, encoding="utf-8")
