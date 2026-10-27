(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = Object.fromEntries([
    "connection", "notice", "feedback", "time-readout", "scene-kicker", "scene-title", "scene-description", "area-tags",
    "status-strip", "ending", "map-summary", "map", "action-count", "action-hint", "controls", "interactions", "level-chip",
    "player", "inventory", "recipes", "skills", "combat-state", "combat", "events", "save", "load", "restart",
  ].map((id) => [id, $(id)]));
  let busy = false;
  let feedbackTimer;

  const asObject = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const asArray = (value) => Array.isArray(value) ? value : [];
  const text = (value, fallback = "--") => value === undefined || value === null || value === "" ? fallback : String(value);
  const esc = (value) => text(value, "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[c]));
  const num = (value) => typeof value === "number" ? String(Number(value.toFixed(2))) : text(value);
  const entries = (value) => Array.isArray(value) ? value.map((row) => [row.name || row.label || row.id || row.type, row.value ?? row.amount ?? row.count ?? row]) : Object.entries(asObject(value));
  const empty = (message) => `<p class="empty">${esc(message)}</p>`;
  const rows = (node, values, render, nothing) => { node.innerHTML = values.length ? values.map(render).join("") : empty(nothing); };
  const nameOf = (item, fallback = "未命名") => typeof item === "string" ? item : item.name || item.label || item.title || item.id || fallback;
  const descriptionOf = (item) => typeof item === "object" ? item.description || item.detail || item.effect || item.summary || "" : "";

  function gameFrom(payload) { return asObject(payload.state || payload.game || payload); }
  function controlsFrom(payload, game) { return asArray(payload.controls || game.controls || payload.legal_actions || game.legal_actions); }
  function setConnection(kind, label) { el.connection.className = `connection is-${kind}`; el.connection.textContent = label; }
  function notice(message, error = false) { el.notice.textContent = message; el.notice.className = `notice${error ? " is-error" : ""}`; }
  function clearNotice() { el.notice.textContent = ""; el.notice.className = "notice is-hidden"; }
  function toast(messages) {
    const list = asArray(messages).flatMap((m) => typeof m === "string" ? [m] : [m?.message || m?.summary || m?.description]).filter(Boolean);
    if (!list.length) return;
    el.feedback.innerHTML = list.map((m) => `<p>${esc(m)}</p>`).join("");
    el.feedback.className = "feedback";
    window.clearTimeout(feedbackTimer);
    feedbackTimer = window.setTimeout(() => { el.feedback.className = "feedback is-hidden"; }, 7000);
  }

  function fieldPairs(fields) {
    return entries(fields).map(([name, value]) => `<span class="field"><b>${esc(name)}</b> ${esc(num(typeof value === "object" ? value.value ?? value.amount ?? "?" : value))}</span>`).join("");
  }
  function renderScene(game) {
    const area = asObject(game.area);
    el["scene-kicker"].textContent = text(area.region || area.kind || game.chapter || "第七夜之前");
    el["scene-title"].textContent = text(area.name || area.title || game.title || "边境");
    el["scene-description"].textContent = text(area.description || game.description || "规则藏在雾、矿脉和仍未抵达的观测站里。", "");
    const tags = [area.weather, area.condition, area.threat, ...(asArray(area.tags))].filter(Boolean);
    el["area-tags"].innerHTML = tags.map((tag) => `<span class="chip">${esc(typeof tag === "object" ? nameOf(tag) : tag)}</span>`).join("");
    const time = game.time ?? game.world_tick ?? game.tick;
    const remaining = game.remaining_time ?? game.ticks_remaining ?? asObject(game.clock).remaining;
    el["time-readout"].textContent = remaining !== undefined ? `余 ${num(remaining)} 刻` : time !== undefined ? `世界刻 ${num(time)}` : "第七夜之前";
  }
  function renderStatus(game) {
    const player = asObject(game.player);
    const attributes = asObject(player.attributes || player.stats);
    const pairs = [
      ["生命", player.hp !== undefined ? `${num(player.hp)}/${num(player.max_hp)}` : undefined],
      ["法力", player.mana !== undefined ? `${num(player.mana)}/${num(player.max_mana)}` : undefined],
      ["护盾", player.shield], ["经验", player.xp ?? player.experience], ["世界刻", game.time ?? game.world_tick ?? game.tick],
      ["力量", attributes.power ?? player.power], ["控制", attributes.control ?? player.control], ["韧性", attributes.resilience ?? player.resilience], ["敏捷", attributes.agility ?? player.agility],
    ].filter(([, value]) => value !== undefined && value !== null);
    el["status-strip"].innerHTML = pairs.map(([name, value]) => `<div class="stat"><span>${esc(name)}</span><strong>${esc(num(value))}</strong></div>`).join("") || empty("状态尚未就绪。");
    el["level-chip"].textContent = `Lv. ${text(player.level ?? game.level, "--")}`;
    const statuses = asArray(player.statuses || player.effects);
    el.player.innerHTML = `<div class="player-name">${esc(player.name || "调查员")}</div><p>${esc(player.description || "在有限的夜晚里摸索活着的世界。")}</p>${statuses.length ? `<div class="tag-row">${statuses.map((status) => `<span class="chip">${esc(nameOf(status))}</span>`).join("")}</div>` : ""}`;
    rows(el.inventory, entries(player.inventory || game.inventory || player.materials).map(([name, amount]) => ({ name, amount })), (item) => `<span class="token">${esc(item.name)} <b>${esc(num(item.amount))}</b></span>`, "尚未持有材料。");
  }
  function mapAreas(game) { const map = game.map; return asArray(map?.areas || map?.nodes || map || game.areas); }
  function renderMap(game) {
    const area = asObject(game.area); const areas = mapAreas(game); const current = area.id || game.area_id || game.current_area;
    el["map-summary"].textContent = `${areas.filter((a) => a.discovered !== false).length}/${areas.length || 5} 已知`;
    rows(el.map, areas, (node) => {
      const id = node.id || node.key || nameOf(node); const currentNode = id === current || node.current;
      const locked = node.locked || node.available === false; const known = node.discovered !== false && !node.hidden;
      const state = currentNode ? "is-current" : locked ? "is-locked" : known ? "is-known" : "is-hidden";
      const detail = locked ? node.lock_reason || "路径尚未形成" : node.description || node.hint || "未知的边境";
      return `<article class="map-node ${state}"><div class="node-cap"><span>${esc(known ? nameOf(node) : "未探明区域")}</span><span>${currentNode ? "当前位置" : locked ? "封闭" : ""}</span></div><p>${esc(detail)}</p>${fieldPairs(node.fields || node.dynamics || {})}</article>`;
    }, "地图仍被迷雾遮蔽。");
  }
  function controlPayload(control) {
    const source = asObject(control); const payload = { ...(asObject(source.payload || source.params || source.arguments)) };
    const action = source.action || source.command || source.id || source.key;
    if (action !== undefined && payload.action === undefined && payload.command === undefined) payload.action = action;
    return payload;
  }
  function actionLabel(control) { return control.label || control.name || control.title || control.action || control.id || "执行"; }
  function renderControls(controls) {
    el["action-count"].textContent = String(controls.length); el["action-hint"].textContent = controls.length ? "选择一次行动。世界会在服务器中结算。" : "当前没有可执行行动。";
    rows(el.controls, controls, (control) => {
      const payload = esc(JSON.stringify(controlPayload(control))); const kind = String(control.kind || control.action || control.id || "").toLowerCase();
      const danger = /attack|fight|close|force/.test(kind) ? " is-danger" : "";
      return `<article class="control"><div><h3>${esc(actionLabel(control))}</h3><p>${esc(descriptionOf(control) || control.hint || "")}</p>${control.cost ? `<small>${esc(typeof control.cost === "string" ? control.cost : JSON.stringify(control.cost))}</small>` : ""}</div><button class="action-button${danger}" type="button" data-action="${payload}">${esc(control.button_label || "行动")}</button></article>`;
    }, "没有合法行动。");
  }
  function renderInteractions(game) {
    const interactions = asArray(game.interactions || asObject(game.area).interactions || game.discoveries);
    rows(el.interactions, interactions, (item) => `<article class="interaction"><div class="interaction-icon">${esc(item.icon || "◇")}</div><div><h3>${esc(nameOf(item))}</h3><p>${esc(descriptionOf(item) || item.hint || "尚未完全理解。")}</p>${item.state ? `<small>${esc(item.state)}</small>` : ""}</div></article>`, "此处暂时没有可深入调查的对象。");
  }
  function renderRecipes(game) {
    const recipes = asArray(game.recipes);
    rows(el.recipes, recipes, (recipe) => {
      const materials = entries(recipe.materials || recipe.requirements).map(([name, value]) => `${name} ${typeof value === "object" ? value.available ?? "?" : value}`).join(" · ");
      const state = recipe.crafted ? "已制作" : recipe.craftable ? "材料足够" : recipe.locked ? "尚未发现" : recipe.missing ? `缺少 ${asArray(recipe.missing).join("、")}` : "待尝试";
      return `<article class="recipe ${recipe.craftable ? "is-ready" : ""}"><div class="row-title"><strong>${esc(nameOf(recipe))}</strong><span>${esc(state)}</span></div><p>${esc(descriptionOf(recipe))}</p><small>${esc(materials || recipe.cost || "探索以找到材料")}</small></article>`;
    }, "尚未掌握任何配方。仔细调查刻文、生态与残骸。");
  }
  function renderSkills(game) {
    const skills = asArray(game.skills || asObject(game.player).skills || game.registered_skills);
    rows(el.skills, skills, (skill) => `<article class="skill"><div class="row-title"><strong>${esc(nameOf(skill))}</strong><span>${esc(skill.equipped ? "已装备" : skill.kind || skill.type || "机制")}</span></div><p>${esc(descriptionOf(skill) || "可在合适的时机改变环境或战斗。")}</p>${skill.cost ? `<small>消耗：${esc(typeof skill.cost === "string" ? skill.cost : JSON.stringify(skill.cost))}</small>` : ""}</article>`, "技能会在制作、注册或发现后出现在这里。");
  }
  function renderCombat(game) {
    const combat = asObject(game.combat); const enemy = asObject(combat.enemy || combat.target || asArray(combat.enemies)[0]); const active = combat.active ?? Boolean(Object.keys(enemy).length);
    el["combat-state"].textContent = active ? "战斗中" : "平静";
    if (!active) { el.combat.innerHTML = empty("暂时没有敌意。环境与准备仍会改变之后的遭遇。"); return; }
    const intent = combat.intent || enemy.intent || combat.enemy_intent;
    const statuses = asArray(enemy.statuses || enemy.effects);
    el.combat.innerHTML = `<div class="combatant"><div class="combat-mark">!</div><div><div class="row-title"><strong>${esc(nameOf(enemy, "未知敌人"))}</strong><span>${esc(enemy.hp !== undefined ? `${num(enemy.hp)}/${num(enemy.max_hp)}` : "")}</span></div><p>${esc(enemy.description || enemy.state || "它正在观察你的选择。")}</p>${intent ? `<div class="intent">意图：${esc(typeof intent === "object" ? nameOf(intent) : intent)}</div>` : ""}${statuses.length ? `<div class="tag-row">${statuses.map((s) => `<span class="chip">${esc(nameOf(s))}</span>`).join("")}</div>` : ""}</div></div>`;
  }
  function renderEvents(payload, game) {
    const events = asArray(payload.events || game.events || game.recent_events);
    rows(el.events, events.slice().reverse(), (entry) => { const event = typeof entry === "string" ? { message: entry } : entry; return `<li><b>${esc(event.source || event.kind || event.type || "世界")}</b><span>${esc(event.message || event.summary || event.description || event.detail || "世界发生了变化。")}</span></li>`; }, "世界尚无回响。");
  }
  function renderEnding(game) {
    const ending = game.ending || game.outcome; const data = typeof ending === "string" ? { message: ending } : asObject(ending);
    const active = data.active ?? Boolean(Object.keys(data).length && !["active", "ongoing", "playing"].includes(data.status));
    if (!active) { el.ending.className = "ending is-hidden"; return; }
    el.ending.className = `ending${data.success === false || data.status === "failure" ? " is-loss" : ""}`;
    el.ending.innerHTML = `<small>${esc(data.kind || data.status || "终局")}</small><strong>${esc(data.title || "这一夜有了答案")}</strong><p>${esc(data.message || data.description || "世界记住了你的选择。")}</p>`;
  }
  function render(payload) {
    const game = gameFrom(payload); renderScene(game); renderStatus(game); renderMap(game); renderControls(controlsFrom(payload, game)); renderInteractions(game); renderRecipes(game); renderSkills(game); renderCombat(game); renderEvents(payload, game); renderEnding(game); toast(game.feedback || payload.feedback);
  }
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    let body; try { body = await response.json(); } catch { throw new Error(`服务器返回了无效响应（HTTP ${response.status}）。`); }
    if (!response.ok || body.error) throw new Error(body.error?.message || body.error || `请求失败（HTTP ${response.status}）。`);
    return body;
  }
  function lock(value) { busy = value; document.querySelectorAll("button").forEach((button) => { button.disabled = value; }); }
  async function state() { setConnection("loading", "正在读取"); const payload = await request("/api/state"); render(payload); clearNotice(); setConnection("ready", "世界在线"); }
  async function submit(payload) { if (busy) return; lock(true); try { render(await request("/api/action", { method: "POST", body: JSON.stringify(payload) })); clearNotice(); setConnection("ready", "世界在线"); } catch (error) { notice(error.message || "行动未能执行。", true); setConnection("error", "连接中断"); } finally { lock(false); } }
  async function utility(url, success) { if (busy) return; lock(true); try { render(await request(url, { method: "POST", body: JSON.stringify({}) })); clearNotice(); setConnection("ready", success); } catch (error) { notice(error.message || "请求未完成。", true); setConnection("error", "连接中断"); } finally { lock(false); } }
  el.controls.addEventListener("click", (event) => { const button = event.target.closest("button[data-action]"); if (!button) return; try { submit(JSON.parse(button.dataset.action)); } catch { notice("行动数据无效。", true); } });
  el.restart.addEventListener("click", () => utility("/api/new-game", "新一局已开始"));
  el.save.addEventListener("click", () => utility("/api/save", "进度已保存"));
  el.load.addEventListener("click", () => utility("/api/load", "进度已载入"));
  state().catch((error) => { setConnection("error", "无法连接"); notice(`无法连接本地 PMW 服务：${error.message}`, true); });
})();
