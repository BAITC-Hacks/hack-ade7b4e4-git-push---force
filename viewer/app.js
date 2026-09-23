/* All identifiers remain strings. No fetch, external resources or layout physics. */
"use strict";
(() => {
  const graph = JSON.parse(document.getElementById("graph-data").textContent);
  const $ = id => document.getElementById(id);
  const el = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const number = value => value == null ? "—" : new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 2}).format(value).replace(/[\u00a0\u202f]/g, " ");
  const money = value => `${number(value)} ₸`;
  const roles = new Map(graph.roles.map(r => [r.key, r]));
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const incoming = new Map(graph.nodes.map(n => [n.id, []]));
  const outgoing = new Map(graph.nodes.map(n => [n.id, []]));
  graph.edges.forEach((edge, index) => {
    edge.viewerId = `e${index}`;
    incoming.get(edge.target).push(edge);
    outgoing.get(edge.source).push(edge);
  });
  const clusterIds = [...new Set(graph.nodes.map(n => String(n.cluster_id)))].sort((a,b) => Number(a)-Number(b));
  const clusterColors = new Map(clusterIds.map((id, i) => [id, `hsl(${(i * 137.508 + 20) % 360}, 58%, 48%)`]));
  const roleLabel = key => roles.get(key)?.label || key;
  const baseColor = n => $("color-mode").value === "cluster" ? clusterColors.get(String(n.cluster_id)) : (roles.get(n.role)?.color || "#8899aa");
  let selected = null;
  const nodeData = new vis.DataSet(graph.nodes.map(n => ({id:n.id, x:n.x, y:n.y, label:"", shape:"dot", size:8 + 24 * Math.max(0, Math.min(1,n.priority_score)), borderWidth:n.is_seed ? 3 : 1, color:{background:baseColor(n),border:n.is_seed ? "#23394c" : baseColor(n)}})));
  const edgeData = new vis.DataSet(graph.edges.map(e => ({id:e.viewerId, from:e.source, to:e.target, arrows:"to", width:0.6 + Math.log1p(Math.max(0,e.sum_kzt))/5, color:{color:"#bdcbd7",highlight:"#2563eb",inherit:false}, smooth:{enabled:true,type:"curvedCW",roundness:0.12}})));
  const network = new vis.Network($("network"), {nodes:nodeData,edges:edgeData}, {
    physics:{enabled:false}, layout:{improvedLayout:false,randomSeed:42},
    interaction:{hover:false,dragNodes:false,hideEdgesOnDrag:true},
    nodes:{font:{face:"Consolas",size:12,color:"#24344b"}},
    edges:{selectionWidth:1.5,arrows:{to:{enabled:true,scaleFactor:0.55}}}
  });
  const status = text => { $("status").textContent = text; };
  function gidLink(gid, text) {
    const link = el("a", text || gid, "gid");
    link.href = `#gid=${encodeURIComponent(gid)}`;
    link.addEventListener("click", event => { event.preventDefault(); selectNode(gid); });
    return link;
  }
  function refresh() {
    const cluster = $("cluster").value;
    const visible = new Set(graph.nodes.filter(n => (!$("hide-peripheral").checked || n.role !== "peripheral") && (cluster === "" || String(n.cluster_id) === cluster)).map(n => n.id));
    const neighbors = new Set(selected ? [selected] : []);
    if (selected) [...incoming.get(selected), ...outgoing.get(selected)].forEach(e => {neighbors.add(e.source);neighbors.add(e.target);});
    nodeData.update(graph.nodes.map(n => {
      const faded = selected && !neighbors.has(n.id);
      const color = faded ? "#e1e7ed" : baseColor(n);
      return {id:n.id,hidden:!visible.has(n.id),label:n.id === selected ? n.id : "",color:{background:color,border:n.id === selected ? "#142d45" : n.is_seed && !faded ? "#23394c" : color,highlight:{background:color,border:"#142d45"}},borderWidth:n.id === selected ? 4 : n.is_seed ? 3 : 1};
    }));
    edgeData.update(graph.edges.map(e => ({id:e.viewerId,hidden:!visible.has(e.source)||!visible.has(e.target),color:{color:selected ? e.source === selected ? "#d97706" : e.target === selected ? "#2563eb" : "#e7ecf1" : "#bdcbd7",inherit:false,opacity:selected && e.source !== selected && e.target !== selected ? 0.2 : 0.85}})));
    $("visible-count").textContent = `${number(visible.size)} из ${number(graph.nodes.length)} узлов`;
    const c = graph.clusters.find(c => String(c.cluster_id) === cluster);
    $("cluster-info").textContent = c ? `${c.hypothesis} · Узлов: ${number(c.n_nodes)} · Seed: ${number(c.n_seed)} · Внутренние переводы: ${money(c.sum_kzt_internal)}` : "";
  }
  function showDetails(n) {
    const panel = $("details"); panel.replaceChildren();
    panel.append(el("div", "КАРТОЧКА КЛИЕНТА", "eyebrow"), el("h2", n.id, "node-id gid"), el("span",roleLabel(n.role),"pill"));
    if(n.is_seed) panel.append(el("span","Исходный узел · seed","pill"));
    const metrics = el("dl",undefined,"metrics");
    const counterparties = new Set([...incoming.get(n.id).map(e=>e.source),...outgoing.get(n.id).map(e=>e.target)]).size;
    for(const [label,value] of [["Уверенность роли",number(n.role_score)],["Приоритет",number(n.priority_score)],["Место в топе",n.rank ?? "Вне топа"],["Кластер",n.cluster_id],["Колено",n.depth],["Исходный (seed)",n.is_seed ? "Да" : "Нет"],["Контрагентов",number(counterparties)],["Вход / выход: контрагенты",`${number(n.in_deg)} / ${number(n.out_deg)}`],["Сумма входа",money(n.in_kzt)],["Сумма выхода",money(n.out_kzt)],["Транзакции: вход / выход",`${number(n.in_tx)} / ${number(n.out_tx)}`],["Выход / вход",number(n.pass_through)],["Seed выше по цепочке",number(n.seeds_upstream)]]) {
      const cell = el("div",undefined,"metric"); cell.append(el("dt",label),el("dd",value));metrics.append(cell);
    }
    panel.append(metrics);
    for(const [title,text] of [["Признаки роли",n.evidence],["Почему в приоритете",n.why || "Обоснование приоритета не указано для этого узла."],["Правило роли",roles.get(n.role)?.rule || "Правило не указано"]]) panel.append(el("h3",title),el("p",text,"explanation"));
    panel.append(el("h3","Флаги и ограничения"));
    const flagLabels = {cutoff_depth4:"Граница выгрузки: колено 4",fast_transit:"Признаки быстрого транзита",sync_inflow:"Признаки синхронных поступлений",cycle:"Участие в цикле переводов",isolated_seed:"Изолированный исходный узел"};
    const flags = el("ul",undefined,"flags");
    (n.flags.length ? n.flags : ["Нет отмеченных флагов"]).forEach(f=>flags.append(el("li",flagLabels[f] ? `${flagLabels[f]} (${f})` : f)));
    panel.append(flags);
    for(const [title,edges,field] of [["Входящие переводы",incoming.get(n.id),"source"],["Исходящие переводы",outgoing.get(n.id),"target"]]) {
      panel.append(el("h3",`${title} · ${edges.length}`));
      if(!edges.length) panel.append(el("p","В выборке нет переводов.","muted"));
      [...edges].sort((a,b)=>b.sum_kzt-a.sum_kzt).forEach(e=>{
        const row = el("div",undefined,"transfer");
        const meta = el("div",undefined,"transfer-meta");meta.append(el("span",money(e.sum_kzt)),el("span",`${number(e.n_tx)} транз.`));
        row.append(gidLink(e[field]),meta);panel.append(row);
      });
    }
  }
  function selectNode(gid, writeHash = true) {
    const n = byId.get(gid);
    if(!n) {status(`GID ${gid} не найден.`);return;}
    let reset = false;
    if($("hide-peripheral").checked && n.role === "peripheral") {$("hide-peripheral").checked=false;reset=true;}
    if($("cluster").value !== "" && $("cluster").value !== String(n.cluster_id)) {$("cluster").value="";reset=true;}
    selected=gid; refresh(); showDetails(n);
    network.selectNodes([gid],false);
    network.focus(gid,{scale:1.3,animation:false});
    if(writeHash && location.hash !== `#gid=${encodeURIComponent(gid)}`) location.hash = `gid=${encodeURIComponent(gid)}`;
    status(`Выбран ${gid}.${reset ? " Фильтры сброшены, чтобы показать узел." : ""}`);
  }
  function clearSelection() {
    selected=null;network.unselectAll();
    $("details").replaceChildren(el("h2","Выберите узел"),el("p","Найдите gid или выберите клиента из топа.","muted"));
    refresh();
  }
  function readHash() {
    const gid = new URLSearchParams(location.hash.slice(1)).get("gid");
    if(gid) selectNode(gid,false); else clearSelection();
  }
  function search(submit = false) {
    const query = $("search").value.trim();
    $("search-results").replaceChildren();
    if(!query) {status("Введите gid целиком или первые цифры.");return;}
    if(submit && byId.has(query)) {selectNode(query);return;}
    const matches = graph.nodes.filter(n=>n.id.startsWith(query));
    if(submit && matches.length === 1) {selectNode(matches[0].id);return;}
    status(matches.length ? `Найдено: ${number(matches.length)}. Выберите gid${matches.length > 50 ? "; показаны первые 50 — уточните запрос" : ""}.` : "Совпадений нет.");
    matches.slice(0,50).forEach(n=>$("search-results").append(gidLink(n.id)));
  }
  $("summary").textContent = `${number(graph.meta.n_nodes)} клиентов · ${number(graph.meta.n_edges)} связей · ${money(graph.meta.turnover_kzt)} · ${graph.meta.period}`;
  clusterIds.forEach(id=>{const option=el("option",`Кластер ${id}`);option.value=id;$("cluster").append(option);});
  graph.roles.forEach(role=>{
    const row=el("div",undefined,"legend-item"), label=el("div",undefined,"legend-label"), swatch=el("span",undefined,"swatch");
    swatch.style.backgroundColor=role.color;label.append(swatch,el("span",role.label));row.append(label,el("p",role.rule,"legend-rule"));$("legend").append(row);
  });
  [...graph.top].sort((a,b)=>a.rank-b.rank).slice(0,20).forEach(item=>{
    const row=gidLink(item.gid);row.className="top-row";row.replaceChildren();
    const heading=el("div",undefined,"top-heading");heading.append(el("span",`#${item.rank}`,"rank"),el("span",item.gid,"gid"),el("span",number(item.priority_score),"score"));
    row.append(heading,el("p",roleLabel(item.role)),el("p",item.why));$("top").append(row);
  });
  if(!graph.top.length) $("top").append(el("p","Список приоритетов пуст.","muted"));
  $("search-form").addEventListener("submit",e=>{e.preventDefault();search(true);});
  $("search").addEventListener("input",()=>search());
  $("color-mode").addEventListener("change",refresh);
  for(const id of ["cluster","hide-peripheral"]) $(id).addEventListener("change",()=>{
    if(selected) {
      const n=byId.get(selected);
      if(($("hide-peripheral").checked && n.role === "peripheral") || ($("cluster").value !== "" && $("cluster").value !== String(n.cluster_id))) {clearSelection();location.hash="";}
    }
    refresh();network.fit({animation:false});
  });
  $("reset").addEventListener("click",()=>{$("cluster").value="";$("hide-peripheral").checked=false;clearSelection();location.hash="";network.fit({animation:false});status("Показана вся сеть.");});
  network.on("click",params=>{if(params.nodes.length) selectNode(params.nodes[0]);});
  window.addEventListener("hashchange",readHash);
  refresh();network.fit({animation:false});readHash();
})();
