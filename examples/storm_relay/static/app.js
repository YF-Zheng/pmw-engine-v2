(() => {
  "use strict";

  const endpoint = "/api/state";
  const elements = Object.fromEntries([
    "connection", "notice", "hero", "scene-title", "scene-description", "status-strip",
    "terminal", "weather-chip", "areas", "stocks", "discoveries", "actions", "action-count",
    "action-hint", "inventory", "recipes", "registry", "loadout", "combat", "events", "restart",
  ].map((id) => [id, document.getElementById(id)]));
  let pending = false;

  const text = (value, fallback = "--") => {
    if (value === undefined || value === null || value === "") return fallback;
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };
  const num = (value) => typeof value === "number" ? Number(value.toFixed(3)).toString() : text(value);
  const array = (value) => Array.isArray(value) ? value : [];
  const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const escape = (value) => text(value, "").replace(/[&<>'\"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[char]));

  function setConnection(state, message) {
    elements.connection.className = `connection is-${state}`;
    elements.connection.textContent = message;
  }
  function showNotice(message, isError = false) {
    elements.notice.textContent = message;
    elements.notice.className = `notice${isError ? " is-error" : ""}`;
  }
  function clearNotice() { elements.notice.className = "notice is-hidden"; elements.notice.textContent = ""; }
  function empty(label) { return `<p class="empty">${escape(label)}</p>`; }
  function sectionRows(container, rows, renderer, emptyLabel) {
    container.innerHTML = rows.length ? rows.map(renderer).join("") : empty(emptyLabel);
  }
  function valuePairs(data) {
    if (Array.isArray(data)) return data.map((entry) => [entry.name || entry.id || entry.type, entry.value ?? entry.amount ?? entry.count ?? entry]);
    return Object.entries(object(data));
  }
  function formatPairs(data) {
    return valuePairs(data).map(([key, value]) => `<span class="field">${escape(key)}: ${escape(num(value))}</span>`).join("");
  }
  function labelFor(action) {
    return action.label || action.name || action.title || action.action || action.id || "执行";
  }
  function describe(action) {
    return action.description || action.detail || action.reason || "";
  }
  function normalizeGame(payload) {
    return object(payload.game || payload.state || payload);
  }
  function playerOf(game) { return object(game.player || game.actor || game.player_state); }
  function areaOf(game) { return object(game.current_area); }

  function renderStatus(game) {
    const player = playerOf(game);
    const clock = object(game.clock || game.time || game.budget);
    const attributes = object(player.attributes || game.attributes);
    const stats = [
      ["区域", game.current_area_name || game.area_name || game.location || areaOf(game).name || areaOf(game).id],
      ["世界刻", clock.world_tick ?? clock.tick ?? game.world_tick ?? game.time?.tick],
      ["剩余时间", clock.remaining ?? clock.remaining_ticks ?? game.remaining_time ?? game.time?.remaining_ticks],
      ["生命", player.hp !== undefined ? `${num(player.hp)}/${num(player.max_hp)}` : undefined],
      ["法力", player.mana !== undefined ? `${num(player.mana)}/${num(player.max_mana)}` : undefined],
      ["力量", attributes.power ?? player.power],
      ["控制", attributes.control ?? player.control],
      ["韧性", attributes.resilience ?? player.resilience],
      ["敏捷", attributes.agility ?? player.agility],
    ].filter(([, value]) => value !== undefined && value !== null);
    elements["status-strip"].innerHTML = stats.map(([label, value]) => `<div class="stat"><span class="stat-label">${escape(label)}</span><span class="stat-value">${escape(num(value))}</span></div>`).join("") || empty("等待世界状态");
  }
  function renderHero(game) {
    const currentArea = areaOf(game);
    const area = game.current_area_name || game.area_name || game.location_name || currentArea.name || currentArea.id || "风暴湿地";
    elements["scene-title"].textContent = text(game.title || area);
    elements["scene-description"].textContent = text(game.description || game.area_description || currentArea.description || "在继电塔与潮汐湿地之间安排每一次行动。");
    const weather = game.weather || currentArea.weather || object(game.world).weather;
    elements["weather-chip"].textContent = weather ? `天气：${text(typeof weather === "object" ? weather.state || weather.name : weather)}` : "天气：--";
  }
  function renderAreas(game) {
    const areas = array(game.areas || object(game.world).areas);
    sectionRows(elements.areas, areas, (area) => {
      const fields = area.fields || area.dynamics || area.field_values || {};
      const weather = area.weather || area.weather_state;
      return `<article class="area-row"><div class="row-title"><span>${escape(area.name || area.id || "区域")}</span><span>${escape(weather || "")}</span></div><div class="row-detail"><div class="field-list">${formatPairs(fields) || "<span class=\"field\">无公开场量</span>"}</div></div></article>`;
    }, "暂无可见区域。");
    sectionRows(elements.stocks, valuePairs(game.stocks || game.resources || areaOf(game).stock || areaOf(game).resources), ([key, value]) => `<span class="token">${escape(key)}: ${escape(num(value))}</span>`, "暂无环境库存。");
    const discoveries = array(game.discoveries || game.known_discoveries);
    sectionRows(elements.discoveries, discoveries, (entry) => `<span class="token">${escape(typeof entry === "object" ? entry.name || entry.id : entry)}</span>`, "尚未发现特殊线索。");
  }
  function renderInventory(game) {
    const inventory = game.inventory || playerOf(game).inventory || [];
    const rows = Array.isArray(inventory) ? inventory : valuePairs(inventory).map(([id, amount]) => ({ id, amount }));
    sectionRows(elements.inventory, rows, (item) => `<article class="item-row"><div class="row-title"><span>${escape(item.name || item.label || item.id || item.type || "物品")}</span><span>${escape(num(item.amount ?? item.count ?? item.quantity ?? ""))}</span></div>${item.description ? `<div class="row-detail">${escape(item.description)}</div>` : ""}</article>`, "背包为空。");
    sectionRows(elements.recipes, array(game.recipes || game.available_recipes), (recipe) => `<article class="recipe-row"><div class="row-title"><span>${escape(recipe.name || recipe.id || "配方")}</span><span>${escape(recipe.time_cost ?? recipe.cost ?? "")}</span></div><div class="row-detail">${escape(recipe.description || recipe.requirements || "等待材料与发现条件")}</div></article>`, "当前没有可见配方。");
  }
  function renderBuild(game) {
    const registry = array(game.registry || game.registered_skills || game.mechanisms);
    sectionRows(elements.registry, registry, (entry) => `<article class="registry-row"><div class="row-title"><span>${escape(entry.name || entry.label || entry.skill_id || entry.id || "机制")}</span><span>${escape(entry.version || entry.kind || "")}</span></div><div class="row-detail">${escape(entry.description || entry.hash || entry.status || "已验证")}</div></article>`, "尚未注册机制。");
    const loadout = game.loadout || game.equipped_skills || playerOf(game).loadout || {};
    const slots = Array.isArray(loadout) ? loadout : Object.entries(object(loadout)).map(([slot, value]) => ({ slot, value }));
    sectionRows(elements.loadout, slots, (entry, index) => {
      const value = entry.value ?? entry.skill ?? entry;
      const skill = typeof value === "object" ? value.name || value.label || value.id || value.skill_id : value;
      return `<article class="slot-row"><div class="row-title"><span>${escape(entry.slot || entry.kind || `槽位 ${index + 1}`)}</span><span>${escape(skill || "空")}</span></div></article>`;
    }, "暂无装备信息。");
  }
  function renderCombat(game) {
    const combat = object(game.combat || game.encounter);
    const actors = array(combat.actors || game.combatants || combat.enemies);
    sectionRows(elements.combat, actors, (actor) => {
      const hp = actor.hp !== undefined ? `${num(actor.hp)}/${num(actor.max_hp)}` : actor.health;
      const shields = actor.shields || actor.shield_layers || [];
      return `<article class="actor-row"><div class="row-title"><span>${escape(actor.name || actor.id || "战斗单位")}</span><span>${escape(hp || "")}</span></div><div class="row-detail">${escape(actor.status || actor.controller || "")}${Array.isArray(shields) && shields.length ? ` · 护盾：${escape(shields.map((s) => s.amount ?? s.value ?? s.name).join("、"))}` : ""}</div></article>`;
    }, combat.active === false ? "当前不在战斗中。" : "当前没有可见战斗单位。");
  }
  function actionPayload(action) {
    const actionId = action.action || action.id || action.command || action.name;
    const payload = { action: actionId };
    if (action.target !== undefined) payload.target = action.target;
    if (action.slot !== undefined) payload.slot = action.slot;
    return payload;
  }
  function renderActions(legalActions) {
    elements["action-count"].textContent = text(legalActions.length, "0");
    elements["action-hint"].textContent = legalActions.length ? "选择一项行动；结果将由服务器重新读取。" : "当前没有合法行动。";
    sectionRows(elements.actions, legalActions, (action, index) => {
      const payload = escape(JSON.stringify(actionPayload(action)));
      const danger = /attack|close|start|combat/i.test(String(action.action || action.id || "")) ? " is-danger" : "";
      return `<article class="action-row"><div class="action-copy"><div class="row-title"><span>${escape(labelFor(action))}</span></div>${describe(action) ? `<div class="row-detail">${escape(describe(action))}</div>` : ""}</div><button class="action-button${danger}" type="button" data-action="${payload}" aria-label="${escape(labelFor(action))}">${escape(action.button_label || "执行")}</button></article>`;
    }, "等待服务端提供合法行动。");
  }
  function renderEvents(events) {
    const newestFirst = array(events).slice().reverse();
    sectionRows(elements.events, newestFirst, (event) => {
      const source = event.source || event.kind || event.type || "世界";
      const body = event.message || event.summary || event.description || event.detail || (typeof event === "string" ? event : JSON.stringify(event));
      return `<li><span class="event-source">${escape(source)}</span> ${escape(body)}</li>`;
    }, "尚无世界事件。");
  }
  function renderTerminal(game) {
    const terminal = game.terminal || game.outcome || game.result;
    const status = typeof terminal === "string" ? terminal : terminal?.status;
    if (!terminal || terminal.active === false || ["active", "ongoing", "in_progress", "playing"].includes(status)) { elements.terminal.className = "terminal is-hidden"; return; }
    const success = terminal.success ?? terminal.won ?? status === "victory";
    const message = typeof terminal === "string" ? terminal : terminal.message || terminal.reason || status || "本局已结束";
    elements.terminal.className = `terminal${success ? "" : " is-loss"}`;
    elements.terminal.textContent = success ? `继电塔已稳定：${message}` : `本局结束：${message}`;
  }
  function render(payload) {
    const game = normalizeGame(payload);
    renderHero(game); renderStatus(game); renderAreas(game); renderInventory(game); renderBuild(game); renderCombat(game);
    renderActions(array(payload.legal_actions || game.legal_actions));
    renderEvents(array(payload.events || game.events || game.recent_events)); renderTerminal(game);
  }
  async function request(url, options) {
    const response = await fetch(url, { headers: { "Accept": "application/json", ...(options?.body ? { "Content-Type": "application/json" } : {}) }, ...options });
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(`服务器返回了非 JSON 响应（HTTP ${response.status}）。`); }
    if (!response.ok || data.error) throw new Error(data.error?.message || data.error || `请求失败（HTTP ${response.status}）。`);
    return data;
  }
  async function refresh() {
    setConnection("loading", "正在连接");
    const payload = await request(endpoint);
    render(payload); clearNotice(); setConnection("ready", "已连接");
  }
  function setPending(value) {
    pending = value;
    document.querySelectorAll(".action-button, #restart").forEach((button) => { button.disabled = value; });
  }
  async function submitAction(payload) {
    if (pending) return;
    setPending(true);
    try { const result = await request("/api/action", { method: "POST", body: JSON.stringify(payload) }); render(result); clearNotice(); setConnection("ready", "已连接"); }
    catch (error) { showNotice(text(error.message, "行动未能提交。"), true); setConnection("error", "连接错误"); }
    finally { setPending(false); }
  }
  elements.actions.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    try { submitAction(JSON.parse(button.dataset.action)); }
    catch (_) { showNotice("行动数据无效。", true); }
  });
  elements.restart.addEventListener("click", async () => {
    if (pending) return;
    setPending(true);
    try { const result = await request("/api/new-game", { method: "POST" }); render(result); clearNotice(); setConnection("ready", "新游戏已开始"); }
    catch (error) { showNotice(text(error.message, "无法开始新游戏。"), true); setConnection("error", "连接错误"); }
    finally { setPending(false); }
  });
  refresh().catch((error) => { setConnection("error", "连接错误"); showNotice(`无法连接本地 PMW 服务：${text(error.message)}`, true); });
})();
