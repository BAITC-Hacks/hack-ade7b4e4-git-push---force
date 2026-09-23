// UI shell. Talks to /api/meta, /api/clients, /api/ask. No frameworks, no build step.
const $ = (id) => document.getElementById(id);
const state = { usdKzt: 0, answers: [], busy: false };
const RULES = {
  confidence_clamped: "уверенность приведена к диапазону 0..1",
  high_risk_no_auto_approve: "высокий риск: автоодобрение запрещено",
  low_confidence_review: "низкая уверенность: отправлено на проверку",
  risky_decision_needs_human: "рискованное решение: нужен сотрудник",
};
const LABEL = {
  approve: "Одобрить", review: "На проверку", decline: "Отказать", info: "Информация",
  none: "Риск: нет", low: "Риск: низкий", medium: "Риск: средний", high: "Риск: высокий",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function toast(text) {
  const t = $("toast"); t.textContent = text; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 4000);
}
function money(usd) {
  if (usd === null || usd === undefined) return "н/д";
  const u = usd < 0.01 ? `$${usd.toFixed(5)}` : `$${usd.toFixed(3)}`;
  return state.usdKzt ? `${u} (${(usd * state.usdKzt).toFixed(2)} ₸)` : u;
}

async function init() {
  try {
    const meta = await (await fetch("/api/meta")).json();
    state.usdKzt = meta.usd_kzt || 0;
    $("title").textContent = meta.title; document.title = meta.title;
    const m = $("mode");
    m.textContent = meta.mode === "live" ? "LIVE" : "DEMO";
    m.className = `badge ${meta.mode === "live" ? "live" : "demo"}`;
    m.title = meta.mode === "live" ? "Запросы идут в модель" : "Ответы из сохранённого кэша";
    $("models").textContent = `быстрая: ${meta.models.fast} · сильная: ${meta.models.smart}`;
    for (const p of meta.demo_prompts || []) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = p.title;
      b.addEventListener("click", () => send(p.message, p.client_id || ""));
      $("prompts").appendChild(b);
    }
  } catch (e) { toast("Не удалось загрузить настройки: " + e.message); }
  try {
    const clients = await (await fetch("/api/clients")).json();
    for (const c of clients) {
      const o = document.createElement("option");
      o.value = c.client_id; o.textContent = `${c.client_id} · ${c.name}`;
      $("client").appendChild(o);
    }
  } catch (e) { /* optional */ }
}

function addMsg(role, html) {
  const log = $("log");
  const empty = log.querySelector(".empty"); if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`; div.innerHTML = html;
  log.appendChild(div); log.scrollTop = log.scrollHeight;
  return div;
}

async function send(message, clientId) {
  if (state.busy || !message.trim()) return;
  state.busy = true; $("send").disabled = true;
  if (clientId !== undefined) $("client").value = clientId;
  addMsg("user", esc(message));
  const wait = addMsg("bot", "Думаю…");
  try {
    const res = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, client_id: $("client").value || null }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    const idx = state.answers.push(data) - 1;
    const m = data.meta;
    const tier = m.escalated ? "быстрая → сильная" : m.tier === "smart" ? "сильная модель" : "быстрая модель";
    const tag = m.cache === "stub" ? "демо-заглушка"
      : m.cache === "demo" ? `сохранённый ответ · ${tier}${m.model ? " · " + m.model : ""}`
      : `${tier} · ${m.latency_ms} мс · ${money(m.cost_usd)}`;
    wait.innerHTML = `${esc(data.answer.answer)}<span class="tag">${esc(tag)}</span>`;
    wait.addEventListener("click", () => show(idx, wait));
    show(idx, wait);
    updateSession();
  } catch (e) {
    wait.textContent = "Ошибка: " + e.message; toast("Запрос не прошёл: " + e.message);
  } finally {
    state.busy = false; $("send").disabled = false; $("msg").value = "";
  }
}

function show(idx, el) {
  document.querySelectorAll(".msg.bot.active").forEach((n) => n.classList.remove("active"));
  if (el) el.classList.add("active");
  const { answer: a, meta: m } = state.answers[idx];
  const conf = Math.max(0, Math.min(1, Number(a.confidence) || 0));
  $("decision").className = "";
  $("decision").innerHTML = `
    <div class="decision-head">
      <span class="pill ${esc(a.decision)}">${esc(LABEL[a.decision] || a.decision)}</span>
      <span class="pill ${esc(a.risk_level)}">${esc(LABEL[a.risk_level] || a.risk_level)}</span>
    </div>
    ${a.needs_human ? '<div class="human">Нужна проверка сотрудником перед действием</div>' : ""}
    <div class="small muted">Уверенность ${(conf * 100).toFixed(0)}%</div>
    <div class="bar"><i style="width:${conf * 100}%"></i></div>
    <ul class="reasons">${(a.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    ${(m.guardrails || []).length ? `<div class="rules">Правила в коде поправили ответ: ${m.guardrails
      .map((g) => esc(RULES[g] || g)).join("; ")}</div>` : ""}`;

  const tools = m.tools_called || [];
  const cached = m.cache === "demo" ? "да, сохранённый ответ" : m.cache === "memory" ? "да, повтор запроса" : m.cache === "stub" ? "заглушка" : "нет";
  const live = m.cached_meta && m.cache === "demo"
    ? `<dt>При живом вызове</dt><dd>${esc(m.cached_meta.model || "")} · ${money(m.cached_meta.cost_usd)} · ${m.cached_meta.latency_ms ?? "?"} мс</dd>` : "";
  $("how").className = "";
  $("how").innerHTML = `
    <dl class="kv">
      <dt>Режим</dt><dd>${esc(m.mode)}${m.error ? " · " + esc(m.error) : ""}</dd>
      <dt>Модель</dt><dd>${esc(m.model || "без модели")}</dd>
      <dt>Маршрут</dt><dd>${esc(m.escalated ? "быстрая → сильная" : m.tier)}: ${esc(m.route_reason)}</dd>
      <dt>Токены</dt><dd>${m.input_tokens} вход (${m.cached_tokens} из кэша) · ${m.output_tokens} выход</dd>
      <dt>Стоимость</dt><dd>${money(m.cost_usd)}</dd>
      <dt>Задержка</dt><dd>${m.latency_ms} мс</dd>
      <dt>Кэш</dt><dd>${cached}</dd>
      <dt>Маскировано</dt><dd>${m.pii_masked && m.pii_masked.length ? esc(m.pii_masked.join(", ")) : "нечего"}</dd>
      ${live}
    </dl>
    ${tools.length ? `<div class="small muted" style="margin-top:10px">Инструменты:</div><ul class="tools">${tools
      .map((t) => `<li><b>${esc(t.name)}</b> ${esc(JSON.stringify(t.arguments))}</li>`).join("")}</ul>` : ""}`;
  $("sent").hidden = false;
  $("sent-text").textContent = m.sent_to_model || "";
}

function updateSession() {
  const n = state.answers.length;
  const fast = state.answers.filter((d) => d.meta.tier === "fast" && !d.meta.escalated).length;
  const cost = state.answers.reduce((s, d) => s + (d.meta.cost_usd || 0), 0);
  const lat = state.answers.reduce((s, d) => s + d.meta.latency_ms, 0) / (n || 1);
  $("s-req").textContent = n;
  $("s-fast").textContent = n ? `${Math.round((100 * fast) / n)}%` : "-";
  $("s-cost").textContent = money(cost);
  $("s-lat").textContent = n ? `${Math.round(lat)} мс` : "-";
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("msg").value); });
$("msg").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send($("msg").value); }
});
init();
