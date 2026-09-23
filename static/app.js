"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { asking: false, cardRequest: 0, selectedGid: null, top: [], overviewRequest: 0 };
  const integer = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const roleLabels = {
    consolidator: "Точка консолидации", transit: "Транзитный узел", transit_hub: "Транзитный узел",
    distributor: "Распределитель", source: "Источник", sink: "Конечный получатель",
    terminal: "Конечный получатель", coordinator: "Координирующий узел",
    bridge: "Мост между кластерами", peripheral: "Периферийный узел", unknown: "Роль не определена"
  };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function stringGid(value) {
    return typeof value === "string" && value.trim() ? value : null;
  }

  function gidOf(node) {
    return node && (stringGid(node.id) || stringGid(node.gid));
  }

  function uniqueGids(values) {
    return Array.isArray(values) ? [...new Set(values.filter(stringGid))] : [];
  }

  function numberText(value, format = integer) {
    return typeof value === "number" && Number.isFinite(value) ? format.format(value) : "—";
  }

  function viewerLink(gid, label = gid, className) {
    const link = element("a", className, label);
    link.href = `/viewer#gid=${encodeURIComponent(gid)}`;
    link.target = "_blank";
    link.rel = "noopener";
    link.title = `Открыть узел ${gid} на схеме`;
    return link;
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        let detail = payload && payload.detail;
        if (Array.isArray(detail)) detail = detail.map((item) => item.msg || "Некорректные данные").join(". ");
        if (detail && typeof detail === "object") detail = detail.message || detail.error;
        throw new Error(typeof detail === "string" ? detail : `Запрос не выполнен (HTTP ${response.status}).`);
      }
      if (!payload || typeof payload !== "object") throw new Error("Сервер вернул ответ в неизвестном формате.");
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Сервер не успел ответить. Попробуйте повторить запрос.");
      if (error instanceof TypeError) throw new Error("Нет связи с сервером. Проверьте подключение и повторите запрос.");
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function notice(message, error = false) {
    $("notice").hidden = !message;
    $("notice").textContent = message;
    $("notice").className = error ? "notice error" : "notice";
  }

  function graphStatus(text, kind) {
    const holder = $("graph-status");
    holder.className = `status ${kind || ""}`;
    holder.replaceChildren(element("span", "status-dot"), element("span", "", text));
  }

  function suggestion(label, question) {
    const button = element("button", "suggestion");
    button.type = "button";
    button.append(element("span", "", label), element("span", "suggestion-arrow", "↗"));
    button.addEventListener("click", () => {
      $("question").value = question;
      $("question").focus();
    });
    return button;
  }

  function renderSuggestions() {
    const target = $("suggestions");
    if (!target) return;
    target.replaceChildren();
    const gids = state.top.map(gidOf).filter(Boolean);
    if (gids.length) target.append(suggestion("Показать карточку первого узла", `карточка ${gids[0]}`));
    if (gids.length > 1) target.append(suggestion("Найти общих получателей двух узлов", `кто собирает деньги с ${gids[0]}, ${gids[1]}`));
    if (!gids.length) target.append(element("p", "small muted", "Введите gid узла, когда граф будет доступен."));
  }

  function renderTop() {
    const target = $("top-nodes");
    target.replaceChildren();
    state.top.forEach((node, index) => {
      const gid = gidOf(node);
      if (!gid) return;
      const button = element("button", `top-node${state.selectedGid === gid ? " selected" : ""}`);
      button.type = "button";
      button.setAttribute("aria-label", `Карточка узла ${gid}`);
      button.setAttribute("aria-pressed", String(state.selectedGid === gid));
      const copy = element("span", "top-copy");
      copy.append(element("span", "top-gid", gid));
      const reason = typeof node.why === "string" ? node.why : (typeof node.evidence === "string" ? node.evidence : "");
      if (reason) copy.append(element("span", "top-reason", reason));
      button.append(element("span", "top-rank", node.rank || index + 1), copy);
      button.addEventListener("click", () => openCard(gid, true));
      target.append(button);
    });
    if (!target.childElementCount) target.append(element("p", "muted small", "Список приоритетов пока пуст."));
  }

  async function loadOverview() {
    const request = ++state.overviewRequest;
    $("refresh-button").disabled = true;
    graphStatus("Проверяем граф…");
    try {
      const health = await api("/api/health");
      if (request !== state.overviewRequest) return;
      $("node-count").textContent = numberText(health.n_nodes);
      $("edge-count").textContent = numberText(health.n_edges);
      $("llm-status").textContent = health.llm_enabled ? "LLM включён" : "Режим правил";
      if (!health.graph_available) {
        graphStatus("Граф пока не готов", "error");
        notice("Граф переводов пока недоступен. Дождитесь подготовки данных и нажмите «Обновить данные».");
        state.top = [];
        renderTop();
        renderSuggestions();
        return;
      }
      graphStatus("Граф доступен", "ready");
      notice(health.llm_enabled ? "" : "Работает режим правил: доступны карточки узлов и поиск общих получателей. Для остальных вопросов нужен LLM.");
      try {
        const result = await api("/api/top");
        if (request !== state.overviewRequest) return;
        state.top = (Array.isArray(result.nodes) ? result.nodes : []).filter(gidOf).slice(0, 5);
        renderTop();
        renderSuggestions();
      } catch (error) {
        state.top = [];
        $("top-nodes").replaceChildren(element("p", "small muted", "Не удалось загрузить список узлов. Поиск по gid доступен."));
        renderSuggestions();
      }
    } catch (error) {
      if (request !== state.overviewRequest) return;
      graphStatus("Нет связи с сервером", "error");
      $("node-count").textContent = "—";
      $("edge-count").textContent = "—";
      $("llm-status").textContent = "Нет связи";
      notice(error.message, true);
      state.top = [];
      renderTop();
      renderSuggestions();
    } finally {
      if (request === state.overviewRequest) $("refresh-button").disabled = false;
    }
  }

  // Model text is never interpreted as HTML or Markdown. Only API-verified gids become links.
  function appendLinkedText(target, text, gids) {
    const candidates = gids.filter(Boolean).sort((a, b) => b.length - a.length);
    let position = 0;
    while (position < text.length) {
      let nextIndex = -1;
      let nextGid = null;
      for (const gid of candidates) {
        let index = text.indexOf(gid, position);
        while (index !== -1) {
          const before = index ? text[index - 1] : "";
          const after = text[index + gid.length] || "";
          // Do not turn a substring of a different identifier into a verified reference.
          if (!/[\p{L}\p{N}_]/u.test(before) && !/[\p{L}\p{N}_]/u.test(after)) break;
          index = text.indexOf(gid, index + gid.length);
        }
        if (index !== -1 && (nextIndex === -1 || index < nextIndex)) {
          nextIndex = index;
          nextGid = gid;
        }
      }
      if (nextIndex === -1) {
        target.append(document.createTextNode(text.slice(position)));
        break;
      }
      target.append(document.createTextNode(text.slice(position, nextIndex)), viewerLink(nextGid));
      position = nextIndex + nextGid.length;
    }
  }

  function addMessage(kind, text, loading = false) {
    const welcome = $("welcome");
    if (welcome) welcome.remove();
    const wrapper = element("article", `message ${kind}`);
    wrapper.append(element("div", "message-label", kind === "user" ? "Вы" : "✦ Ассистент"));
    const body = element("div", `message-body${loading ? " loading-dots" : ""}`, text);
    wrapper.append(body);
    $("messages").append(wrapper);
    scrollMessages();
    return { wrapper, body };
  }

  function scrollMessages() {
    $("messages").scrollTop = $("messages").scrollHeight;
  }

  function renderAnswer(message, result) {
    const gids = uniqueGids(result.gids);
    message.body.classList.remove("loading-dots");
    message.body.replaceChildren();
    appendLinkedText(message.body, typeof result.answer === "string" ? result.answer : "Ответ не содержит текста.", gids);
    if (gids.length) {
      const links = element("div", "gid-links");
      gids.forEach((gid) => {
        const chip = element("span", "gid-chip");
        const cardButton = element("button", "", "Карточка");
        cardButton.type = "button";
        cardButton.setAttribute("aria-label", `Открыть карточку узла ${gid}`);
        cardButton.addEventListener("click", () => openCard(gid, true));
        chip.append(viewerLink(gid), cardButton);
        links.append(chip);
      });
      message.wrapper.append(links);
    }
    const metadata = [];
    if (typeof result.confidence === "number" && Number.isFinite(result.confidence)) metadata.push(`Уверенность ответа: ${Math.round(Math.max(0, Math.min(1, result.confidence)) * 100)}%`);
    if (Array.isArray(result.tools) && result.tools.length) metadata.push("Источник: граф переводов");
    if (metadata.length) message.wrapper.append(element("div", "message-meta", metadata.join(" · ")));
    scrollMessages();
  }

  async function ask(event) {
    event.preventDefault();
    if (state.asking) return;
    const question = $("question").value.trim();
    if (!question) return;
    state.asking = true;
    $("send-button").disabled = true;
    $("question").value = "";
    addMessage("user", question);
    const message = addMessage("assistant", "Проверяю данные графа", true);
    try {
      const result = await api("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question })
      });
      renderAnswer(message, result);
    } catch (error) {
      message.wrapper.classList.add("error");
      message.body.classList.remove("loading-dots");
      message.body.textContent = error.message;
      const retry = element("button", "text-button", "Вернуть вопрос в поле ввода");
      retry.type = "button";
      retry.addEventListener("click", () => { $("question").value = question; $("question").focus(); });
      message.wrapper.append(retry);
      scrollMessages();
    } finally {
      state.asking = false;
      $("send-button").disabled = false;
      $("question").focus();
    }
  }

  function flowMetric(label, value, detail) {
    const metric = element("div");
    metric.append(element("div", "flow-label", label), element("div", "flow-value", value), element("div", "flow-detail", detail));
    return metric;
  }

  function renderCard(card, requestedGid) {
    const target = $("node-card");
    target.replaceChildren();
    const gid = stringGid(card.gid) || requestedGid;
    const role = card.role && typeof card.role === "object" ? card.role : { key: card.role };
    const label = role.label || roleLabels[role.key] || role.key || "Роль не определена";
    target.append(element("h3", "card-gid", gid), element("div", "role-badge", label));
    if (role.evidence) target.append(element("p", "card-evidence", role.evidence));
    const flows = card.flows || {};
    const connections = card.connections || {};
    const flowGrid = element("div", "flow-grid");
    flowGrid.append(
      flowMetric("↓ Входящие, ₸", numberText(flows.in_kzt, money), `${numberText(flows.in_tx)} переводов`),
      flowMetric("↑ Исходящие, ₸", numberText(flows.out_kzt, money), `${numberText(flows.out_tx)} переводов`),
      flowMetric("Отправители", numberText(connections.in_deg), "входящие связи"),
      flowMetric("Получатели", numberText(connections.out_deg), "исходящие связи")
    );
    target.append(flowGrid);
    const attention = Array.isArray(card.attention) ? card.attention.filter((item) => typeof item === "string") : [];
    const attentionSection = element("section", "card-section");
    attentionSection.append(element("h3", "", "На что обратить внимание"));
    if (attention.length) {
      const list = element("ul", "attention-list");
      attention.forEach((item) => list.append(element("li", "", item)));
      attentionSection.append(list);
    } else attentionSection.append(element("p", "small muted", "Дополнительные признаки в данных не указаны."));
    target.append(attentionSection);
    const incoming = Array.isArray(connections.incoming) ? connections.incoming : [];
    const outgoing = Array.isArray(connections.outgoing) ? connections.outgoing : [];
    const edges = [
      ...incoming.map((edge) => ({ edge, direction: "in", neighbor: stringGid(edge.source) })),
      ...outgoing.map((edge) => ({ edge, direction: "out", neighbor: stringGid(edge.target) }))
    ].filter((entry) => entry.neighbor).sort((a, b) => (b.edge.sum_kzt || 0) - (a.edge.sum_kzt || 0));
    if (edges.length) {
      const section = element("section", "card-section");
      section.append(element("h3", "", "Крупнейшие связи"));
      const list = element("div", "connection-list");
      edges.slice(0, 6).forEach(({ edge, direction, neighbor }) => {
        const row = element("div", "connection-row");
        const marker = element("span", "connection-direction", direction === "in" ? "↓" : "↑");
        marker.title = direction === "in" ? "Входящий перевод" : "Исходящий перевод";
        row.append(marker, viewerLink(neighbor), element("span", "connection-amount", `${numberText(edge.sum_kzt, money)} ₸`));
        list.append(row);
      });
      section.append(list);
      if (edges.length > 6) section.append(element("p", "small muted", "Все связи доступны на схеме графа."));
      target.append(section);
    }
    target.append(viewerLink(gid, "Открыть узел на схеме ↗", "viewer-link"));
  }

  async function openCard(gid, scroll = false) {
    if (!stringGid(gid)) return;
    state.selectedGid = gid;
    const request = ++state.cardRequest;
    $("node-gid").value = gid;
    renderTop();
    $("node-card").replaceChildren(element("p", "small muted loading-dots", "Загружаю карточку"));
    $("node-card").setAttribute("aria-busy", "true");
    if (scroll && window.matchMedia("(max-width: 980px)").matches) $("card-title").scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const card = await api(`/api/card/${encodeURIComponent(gid)}`);
      if (request === state.cardRequest) renderCard(card, gid);
    } catch (error) {
      if (request === state.cardRequest) $("node-card").replaceChildren(element("p", "error-text", error.message));
    } finally {
      if (request === state.cardRequest) $("node-card").setAttribute("aria-busy", "false");
    }
  }

  $("ask-form").addEventListener("submit", ask);
  $("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!state.asking) $("ask-form").requestSubmit();
    }
  });
  $("node-form").addEventListener("submit", (event) => {
    event.preventDefault();
    openCard($("node-gid").value.trim());
  });
  $("refresh-button").addEventListener("click", loadOverview);
  loadOverview();
})();
