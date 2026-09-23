"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { asking: false, askRequest: 0, activeAsk: null, rulesOnly: false, llmAvailable: false,
    cardRequest: 0, selectedGid: null, top: [], demoPayers: [], demoLoading: true, overviewRequest: 0 };
  const integer = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

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

  async function api(path, options = {}, control = {}) {
    const controller = control.controller || new AbortController();
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, control.timeoutMs || 120000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal });
      const payload = await response.json().catch((error) => {
        if (error.name === "AbortError") throw error;
        return null;
      });
      if (!response.ok) {
        let detail = payload && payload.detail;
        if (Array.isArray(detail)) detail = detail.map((item) => item.msg || "Некорректные данные").join(". ");
        if (detail && typeof detail === "object") detail = detail.message || detail.error;
        throw new Error(typeof detail === "string" ? detail : `Запрос не выполнен (HTTP ${response.status}).`);
      }
      if (!payload || typeof payload !== "object") throw new Error("Сервер вернул ответ в неизвестном формате.");
      return payload;
    } catch (error) {
      if (error.name === "AbortError") {
        const failure = new Error(timedOut ? "Сервер не успел ответить. Попробуйте повторить запрос." : "Ожидание ответа остановлено.");
        failure.code = timedOut ? "request_timeout" : "request_cancelled";
        throw failure;
      }
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

  function renderMode(reason = "") {
    const withoutModel = state.rulesOnly || !state.llmAvailable;
    $("llm-status").textContent = withoutModel ? "Без модели" : "LLM включён";
    const button = $("rules-mode-button");
    button.textContent = state.rulesOnly && state.llmAvailable ? "Включить модель" : "Без модели";
    button.disabled = !state.llmAvailable;
    button.setAttribute("aria-pressed", String(withoutModel));
    button.title = withoutModel ? "Разрешить модель для следующих вопросов" : "Продолжить без ожидания модели";
    notice(withoutModel ? `${reason ? reason + " " : ""}Работает режим без модели: доступны список приоритетов, карточки узлов, черновики записок и поиск общих получателей.` : "");
  }

  function switchToRules(reason) {
    state.rulesOnly = true;
    renderMode(reason);
  }

  function toggleModel() {
    if (!state.llmAvailable) return;
    if (state.rulesOnly) {
      state.rulesOnly = false;
      renderMode();
      return;
    }
    switchToRules("Модель отключена для этого диалога.");
    const pending = state.activeAsk;
    if (pending && pending.useLlm) {
      // Invalidate before aborting: a late response must not overwrite the retry.
      ++state.askRequest;
      pending.controller.abort();
      state.activeAsk = null;
      state.asking = false;
      return sendQuestion(pending.question, pending.message);
    }
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
    target.append(suggestion("Кто в топе приоритетов?", "Кто в топе приоритетов?"));
    if (gids.length) {
      target.append(suggestion("Карточка №1", `Карточка ${gids[0]}`));
      target.append(suggestion("Черновик по №1", `Черновик по ${gids[0]}`));
    }
    if (state.demoPayers.length === 3) {
      const question = `Кто собирает деньги с ${state.demoPayers.join(", ")}?`;
      const button = suggestion("Кто собирает деньги с ...", question);
      button.title = question;
      button.setAttribute("aria-label", question);
      target.append(button);
    }
    if (state.demoLoading) target.append(element("p", "suggestions-note muted", "Подбираем примеры из графа…"));
    else if (!gids.length) target.append(element("p", "suggestions-note muted", "Примеры по узлам появятся, когда список приоритетов будет доступен."));
    else if (!state.demoPayers.length) target.append(element("p", "suggestions-note muted", "Для примера с общим получателем нужны три плательщика одного узла из топа."));
  }

  async function loadDemoPayers(request) {
    const results = await Promise.allSettled(state.top.map(async (node) => {
      const gid = gidOf(node);
      const result = await api(`/api/node/${encodeURIComponent(gid)}?direction=in`);
      const incoming = Array.isArray(result.incoming) ? result.incoming : [];
      // Use distinct incoming sources, never arbitrary high-priority nodes or numeric IDs.
      return uniqueGids(incoming.filter((edge) => edge && edge.target === gid && edge.source !== gid)
        .map((edge) => edge.source)).slice(0, 3);
    }));
    if (request !== state.overviewRequest) return;
    const match = results.find((result) => result.status === "fulfilled" && result.value.length === 3);
    state.demoPayers = match ? match.value : [];
    state.demoLoading = false;
    renderSuggestions();
  }

  function renderTop() {
    const target = $("top-nodes");
    target.replaceChildren();
    state.top.slice(0, 5).forEach((node, index) => {
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
    state.top = [];
    state.demoPayers = [];
    state.demoLoading = true;
    renderSuggestions();
    $("refresh-button").disabled = true;
    graphStatus("Проверяем граф…");
    try {
      const health = await api("/api/health");
      if (request !== state.overviewRequest) return;
      $("node-count").textContent = numberText(health.n_nodes);
      $("edge-count").textContent = numberText(health.n_edges);
      state.llmAvailable = Boolean(health.llm_enabled);
      renderMode();
      if (!health.graph_available) {
        graphStatus("Граф пока не готов", "error");
        notice("Граф переводов пока недоступен. Дождитесь подготовки данных и нажмите «Обновить данные».");
        state.top = [];
        state.demoLoading = false;
        renderTop();
        renderSuggestions();
        return;
      }
      graphStatus("Граф доступен", "ready");
      try {
        const result = await api("/api/top");
        if (request !== state.overviewRequest) return;
        state.top = (Array.isArray(result.nodes) ? result.nodes : []).filter(gidOf).slice(0, 10);
        renderTop();
        renderSuggestions();
        await loadDemoPayers(request);
      } catch (error) {
        if (request !== state.overviewRequest) return;
        state.top = [];
        state.demoPayers = [];
        state.demoLoading = false;
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
      state.demoPayers = [];
      state.demoLoading = false;
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
    $("question").value = "";
    return sendQuestion(question);
  }

  async function sendQuestion(question, previousMessage = null) {
    const request = ++state.askRequest;
    const controller = new AbortController();
    const useLlm = state.llmAvailable && !state.rulesOnly;
    state.asking = true;
    $("send-button").disabled = true;
    if (!previousMessage) addMessage("user", question);
    const message = previousMessage || addMessage("assistant", "Проверяю данные графа", true);
    if (previousMessage) message.body.textContent = "Готовлю ответ без модели";
    state.activeAsk = { question, message, controller, useLlm };
    try {
      const result = await api("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, use_llm: useLlm })
      }, { controller, timeoutMs: 45000 });
      if (request !== state.askRequest) return;
      if (useLlm && result.meta && ["fallback", "offline", "demo"].includes(result.meta.mode)) {
        switchToRules("Ответ подготовлен без модели. Следующие вопросы также выполняются без неё.");
      }
      renderAnswer(message, result);
    } catch (error) {
      if (request !== state.askRequest) return;
      if (useLlm && error.code === "request_timeout") {
        switchToRules("Ответ модели не получен вовремя. Продолжаем без неё.");
        return sendQuestion(question, message);
      }
      message.wrapper.classList.add("error");
      message.body.classList.remove("loading-dots");
      message.body.textContent = error.message;
      const retry = element("button", "text-button", "Вернуть вопрос в поле ввода");
      retry.type = "button";
      retry.addEventListener("click", () => { $("question").value = question; $("question").focus(); });
      message.wrapper.append(retry);
      scrollMessages();
    } finally {
      if (request === state.askRequest) {
        state.activeAsk = null;
        state.asking = false;
        $("send-button").disabled = false;
        $("question").focus();
      }
    }
  }

  function renderCard(card, requestedGid) {
    const target = $("node-card");
    target.replaceChildren();
    const gid = stringGid(card.gid) || requestedGid;
    target.append(element("h3", "card-gid", gid));
    const body = element("div", "stored-card");
    // Saved card text is displayed verbatim; only known graph IDs become links.
    appendLinkedText(body, typeof card.card === "string" ? card.card : "Карточка пока недоступна.", uniqueGids(card.gids));
    target.append(body, viewerLink(gid, "Открыть узел на схеме ↗", "viewer-link"));
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
  $("rules-mode-button").addEventListener("click", toggleModel);
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
