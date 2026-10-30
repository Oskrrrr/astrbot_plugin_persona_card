const bridge = window.AstrBotPluginPage;

const state = {
  cards: [],
  sessions: [],
  options: { personas: [], tts: [], chat: [], kbs: [], packs: [] },
  editing: null,
  selectedId: "",
  deleteArmed: false,
};

let toastTimer = null;
let deleteTimer = null;

const $ = (id) => document.getElementById(id);

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );

function unwrap(result) {
  if (result && typeof result === "object") {
    if (result.ok === false) {
      throw new Error(result.error?.message || result.message || "请求失败");
    }
    if (Object.prototype.hasOwnProperty.call(result, "data")) {
      return result.data;
    }
  }
  return result ?? {};
}

async function apiGet(endpoint) {
  if (!bridge) throw new Error("没有检测到 AstrBot 页面桥接");
  return unwrap(await bridge.apiGet(endpoint, {}));
}

async function apiPost(endpoint, body) {
  if (!bridge) throw new Error("没有检测到 AstrBot 页面桥接");
  return unwrap(await bridge.apiPost(endpoint, body || {}));
}

function toast(message, isError = false) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  box.classList.toggle("err", Boolean(isError));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, isError ? 4200 : 2800);
}

function fmtTime(ts) {
  const n = Number(ts || 0);
  if (!n) return "—";
  const d = new Date(n * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (v) => String(v).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function providerLabel(item) {
  const model = String(item.model || "");
  return model && model !== item.id ? `${item.id} · ${model}` : item.id;
}

function personaName(id) {
  if (!id) return "跟随会话";
  const found = state.options.personas.find((p) => p.id === id);
  return found ? found.name : id;
}

function ttsName(id) {
  if (!id) return "全局默认";
  const found = state.options.tts.find((p) => p.id === id);
  return found ? found.id : id;
}

// ------------------------------------------------------------------ 渲染

function blankCard() {
  return {
    id: "",
    name: "",
    emoji: "🐟",
    persona_id: "",
    tts_provider_id: "",
    chat_provider_id: "",
    kb_ids: [],
    meme_pack_ids: [],
    prompt_append: "",
    qzone: {
      post_prompt: "",
      image_style: "",
      image_requirements: "",
      image_negative: "",
    },
    notes: "",
  };
}

function cloneCard(id) {
  const found = state.cards.find((c) => c.id === id);
  return found ? JSON.parse(JSON.stringify(found)) : null;
}

function renderCards() {
  const list = $("cardList");
  $("cardCount").textContent = `${state.cards.length} 张`;
  if (!state.cards.length) {
    list.innerHTML = `<li class="empty">还没有角色卡<br />点右上角「新建角色卡」</li>`;
    return;
  }
  list.innerHTML = state.cards
    .map(
      (card) => `
      <li class="card-item ${card.id === state.selectedId ? "active" : ""}" data-id="${esc(card.id)}">
        <span class="card-emoji">${esc(card.emoji || "🎴")}</span>
        <span class="card-body">
          <strong>${esc(card.name || "未命名")}</strong>
          <span class="card-meta">${esc(personaName(card.persona_id))} · ${esc(ttsName(card.tts_provider_id))}</span>
        </span>
      </li>`
    )
    .join("");
}

function fillPersonaSelect(value) {
  const rows = ['<option value="">跟随会话默认</option>'];
  state.options.personas.forEach((p) => {
    rows.push(`<option value="${esc(p.id)}">${esc(p.name)}</option>`);
  });
  $("fPersona").innerHTML = rows.join("");
  $("fPersona").value = value || "";
}

function fillTtsSelect(value) {
  const rows = ['<option value="">全局默认</option>'];
  state.options.tts.forEach((p) => {
    rows.push(`<option value="${esc(p.id)}">${esc(providerLabel(p))}</option>`);
  });
  $("fTts").innerHTML = rows.join("");
  $("fTts").value = value || "";
}

function fillChatSelect(value) {
  const rows = ['<option value="">全局默认</option>'];
  state.options.chat.forEach((p) => {
    rows.push(`<option value="${esc(p.id)}">${esc(providerLabel(p))}</option>`);
  });
  $("fChat").innerHTML = rows.join("");
  $("fChat").value = value || "";
}

function packOptions(value) {
  const rows = ['<option value="">不改变（默认规则）</option>'];
  state.options.packs.forEach((p) => {
    const suffix = p.enabled ? "" : "（未启用）";
    const selected = p.id === value ? " selected" : "";
    rows.push(`<option value="${esc(p.id)}"${selected}>${esc(p.name + suffix)}</option>`);
  });
  return rows.join("");
}

function renderPacks(selected) {
  const ids = (selected || []).filter(Boolean);
  const box = $("fPacks");
  if (!ids.length) {
    box.innerHTML = `<div class="pack-empty">未选择：使用表情包管理的默认规则</div>`;
    return;
  }
  box.innerHTML = ids
    .map(
      (id) => `<div class="pack-row">
        <select class="pack-select">${packOptions(id)}</select>
        <button type="button" class="ghost danger pack-del" title="移除这个表情包">×</button>
      </div>`
    )
    .join("");
}

function renderKbs(selected) {
  const chosen = new Set(selected || []);
  const box = $("fKbs");
  if (!state.options.kbs.length) {
    box.innerHTML = `<span class="muted">还没有知识库</span>`;
    return;
  }
  box.innerHTML = state.options.kbs
    .map(
      (kb) => `
      <button type="button" class="chip ${chosen.has(kb.id) ? "on" : ""}" data-kb="${esc(kb.id)}">
        ${esc(kb.name)}<span class="chip-doc">${esc(kb.docs ?? 0)}</span>
      </button>`
    )
    .join("");
}

function renderEditor() {
  const card = state.editing || blankCard();
  $("editorTitle").textContent = card.id ? "编辑角色卡" : "新建角色卡";
  $("editorState").textContent = card.id ? `ID ${card.id}` : "尚未保存";
  $("fEmoji").value = card.emoji || "";
  $("fName").value = card.name || "";
  fillPersonaSelect(card.persona_id);
  $("fPrompt").value = card.prompt_append || "";
  const qzone = card.qzone || {};
  $("fQzonePost").value = qzone.post_prompt || "";
  $("fQzoneStyle").value = qzone.image_style || "";
  $("fQzoneReq").value = qzone.image_requirements || "";
  $("fQzoneNeg").value = qzone.image_negative || "";
  fillTtsSelect(card.tts_provider_id);
  fillChatSelect(card.chat_provider_id);
  const packIds = Array.isArray(card.meme_pack_ids)
    ? card.meme_pack_ids
    : card.meme_pack_id
      ? [card.meme_pack_id]
      : [];
  renderPacks(packIds);
  $("fNotes").value = card.notes || "";
  renderKbs(card.kb_ids || []);
  $("btnDelete").disabled = !card.id;
  resetDeleteButton();
  $("formMsg").textContent = "";
  $("formMsg").classList.remove("err");
}

function renderSessions() {
  const box = $("sessionList");
  $("sessionCount").textContent = `${state.sessions.length} 个`;
  if (!state.sessions.length) {
    box.innerHTML = `<div class="empty">还没记录到会话。<br />让机器人在群里收到一条消息，这里就会出现；也可以在下面手填会话标识。</div>`;
    return;
  }
  box.innerHTML = state.sessions
    .map((session) => {
      const options = ['<option value="">不绑定</option>']
        .concat(
          state.cards.map(
            (card) =>
              `<option value="${esc(card.id)}" ${card.id === session.card_id ? "selected" : ""}>${esc(card.name || "未命名")}</option>`
          )
        )
        .join("");
      const tag = session.card_name
        ? `<span class="tag ok">${esc(session.card_name)}</span>`
        : `<span class="tag">未绑定</span>`;
      const preview = session.last_text ? ` · ${esc(session.last_text)}` : "";
      return `
        <div class="session" data-umo="${esc(session.umo)}">
          <div class="session-head">
            <span class="session-label">${esc(session.label)}</span>
            ${tag}
          </div>
          <div class="session-umo" title="${esc(session.umo)}">${esc(session.umo)}<span class="dot">·</span>${esc(fmtTime(session.last_seen))}${preview}</div>
          <div class="session-actions">
            <select data-role="card">${options}</select>
            <div class="session-buttons">
              <button type="button" class="primary sm" data-act="apply">应用</button>
              <button type="button" class="ghost sm" data-act="draft">存为卡</button>
              <button type="button" class="ghost sm" data-act="unbind">解绑</button>
            </div>
          </div>
        </div>`;
    })
    .join("");
}

function renderManual() {
  const select = $("manualCard");
  const keep = select.value;
  const rows = ['<option value="">选一张卡</option>'].concat(
    state.cards.map((card) => `<option value="${esc(card.id)}">${esc(card.name || "未命名")}</option>`)
  );
  select.innerHTML = rows.join("");
  if (keep && state.cards.some((c) => c.id === keep)) {
    select.value = keep;
  } else if (state.selectedId) {
    select.value = state.selectedId;
  }
}

function renderAll() {
  renderCards();
  renderEditor();
  renderSessions();
  renderManual();
}

// ------------------------------------------------------------------ 数据

async function load() {
  const data = await apiGet("state");
  state.cards = Array.isArray(data.cards) ? data.cards : [];
  state.sessions = Array.isArray(data.sessions) ? data.sessions : [];
  const options = data.options || {};
  state.options = {
    personas: Array.isArray(options.personas) ? options.personas : [],
    tts: Array.isArray(options.tts) ? options.tts : [],
    chat: Array.isArray(options.chat) ? options.chat : [],
    kbs: Array.isArray(options.kbs) ? options.kbs : [],
    packs: Array.isArray(options.packs) ? options.packs : [],
  };

  if (state.selectedId && !state.cards.some((c) => c.id === state.selectedId)) {
    state.selectedId = "";
    state.editing = null;
  }
  if (!state.editing && !state.selectedId && state.cards.length) {
    state.selectedId = state.cards[0].id;
    state.editing = cloneCard(state.selectedId);
  }
  renderAll();
}

function selectCard(id) {
  state.selectedId = id;
  state.editing = cloneCard(id) || blankCard();
  renderAll();
}

function collect() {
  const kbIds = Array.from(document.querySelectorAll("#fKbs .chip.on")).map((el) => el.dataset.kb);
  return {
    id: state.editing?.id || "",
    name: $("fName").value.trim(),
    emoji: $("fEmoji").value.trim(),
    persona_id: $("fPersona").value,
    tts_provider_id: $("fTts").value,
    chat_provider_id: $("fChat").value,
    meme_pack_ids: Array.from(document.querySelectorAll("#fPacks .pack-select"))
      .map((el) => el.value)
      .filter(Boolean)
      .filter((id, index, arr) => arr.indexOf(id) === index),
    kb_ids: kbIds,
    prompt_append: $("fPrompt").value,
    qzone: {
      post_prompt: $("fQzonePost").value,
      image_style: $("fQzoneStyle").value,
      image_requirements: $("fQzoneReq").value,
      image_negative: $("fQzoneNeg").value,
    },
    notes: $("fNotes").value.trim(),
  };
}

// ------------------------------------------------------------------ 交互

function showFormMsg(message, isError) {
  const box = $("formMsg");
  box.textContent = message;
  box.classList.toggle("err", Boolean(isError));
}

function resetDeleteButton() {
  state.deleteArmed = false;
  const btn = $("btnDelete");
  btn.textContent = "删除";
  btn.classList.add("ghost");
}

function armDelete() {
  state.deleteArmed = true;
  const btn = $("btnDelete");
  btn.textContent = "再点一次确认删除";
  clearTimeout(deleteTimer);
  deleteTimer = setTimeout(resetDeleteButton, 3000);
}

async function saveCard(event) {
  event.preventDefault();
  const payload = collect();
  if (!payload.name) {
    showFormMsg("先给角色卡起个名字", true);
    $("fName").focus();
    return;
  }
  const btn = $("btnSave");
  btn.disabled = true;
  try {
    const result = await apiPost("save", { card: payload });
    state.editing = result.card;
    state.selectedId = result.card.id;
    await load();
    toast(`已保存「${result.card.name}」`);
  } catch (error) {
    showFormMsg(error.message, true);
    toast(error.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function deleteCard() {
  const card = state.editing;
  if (!card || !card.id) return;
  if (!state.deleteArmed) {
    armDelete();
    return;
  }
  clearTimeout(deleteTimer);
  try {
    await apiPost("delete", { id: card.id });
    state.editing = null;
    state.selectedId = "";
    await load();
    toast("已删除");
  } catch (error) {
    toast(error.message, true);
  } finally {
    resetDeleteButton();
  }
}

async function applyCard(umo, cardId) {
  if (!cardId) {
    toast("先选一张角色卡", true);
    return;
  }
  try {
    const result = await apiPost("apply", { umo, card_id: cardId });
    const eff = result.effective || {};
    const name = result.card?.name || "角色卡";
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    const packs = Array.isArray(eff.meme_pack_ids) ? eff.meme_pack_ids : [];
    const summary = `人格 ${eff.persona_id || "默认"}｜音色 ${eff.tts_provider_id || "默认"}｜表情包 ${packs.join("、") || "默认"}`;
    if (warnings.length) {
      toast(`已应用「${name}」，但有跳过项：${warnings.join("；")}`, true);
    } else {
      toast(`已应用「${name}」：${summary}`);
    }
    await load();
  } catch (error) {
    toast(error.message, true);
  }
}

async function unbindSession(umo) {
  try {
    await apiPost("unbind", { umo });
    toast("已解除绑定，该会话回到默认设置");
    await load();
  } catch (error) {
    toast(error.message, true);
  }
}

async function draftFromSession(umo) {
  try {
    const result = await apiPost("draft", { umo });
    state.editing = result.card;
    state.selectedId = "";
    renderAll();
    toast("已把该会话当前设置载入表单，改个名字再保存");
  } catch (error) {
    toast(error.message, true);
  }
}

function bindEvents() {
  $("btnNew").addEventListener("click", () => {
    state.editing = blankCard();
    state.selectedId = "";
    renderAll();
    $("fName").focus();
  });

  $("btnReload").addEventListener("click", async () => {
    try {
      await load();
      toast("已刷新");
    } catch (error) {
      toast(error.message, true);
    }
  });

  $("btnAddPack").addEventListener("click", () => {
    const box = $("fPacks");
    if (box.querySelector(".pack-empty")) box.innerHTML = "";
    box.insertAdjacentHTML(
      "beforeend",
      `<div class="pack-row">
        <select class="pack-select">${packOptions("")}</select>
        <button type="button" class="ghost danger pack-del" title="移除这个表情包">×</button>
      </div>`
    );
  });

  $("fPacks").addEventListener("click", (event) => {
    const btn = event.target.closest(".pack-del");
    if (!btn) return;
    btn.closest(".pack-row")?.remove();
    if (!$("fPacks").querySelector(".pack-row")) {
      $("fPacks").innerHTML = `<div class="pack-empty">未选择：使用表情包管理的默认规则</div>`;
    }
  });

  $("cardForm").addEventListener("submit", saveCard);
  $("btnDelete").addEventListener("click", deleteCard);

  $("cardList").addEventListener("click", (event) => {
    const item = event.target.closest(".card-item");
    if (item?.dataset.id) selectCard(item.dataset.id);
  });

  $("fKbs").addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (chip) chip.classList.toggle("on");
  });

  $("sessionList").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-act]");
    if (!button) return;
    const row = button.closest(".session");
    const umo = row?.dataset.umo || "";
    const action = button.dataset.act;
    if (action === "apply") {
      const cardId = row.querySelector('select[data-role="card"]')?.value || "";
      applyCard(umo, cardId);
    } else if (action === "unbind") {
      unbindSession(umo);
    } else if (action === "draft") {
      draftFromSession(umo);
    }
  });

  $("manualForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const umo = $("manualUmo").value.trim();
    if (!umo.includes(":")) {
      toast("会话标识要形如 default:GroupMessage:397714239", true);
      return;
    }
    applyCard(umo, $("manualCard").value);
  });
}

async function init() {
  if (!bridge) {
    document.body.innerHTML =
      '<div class="empty">没有检测到 AstrBot 页面桥接，请从 WebUI 的插件页面进入。</div>';
    return;
  }
  try {
    await bridge.ready();
  } catch (error) {
    toast(error.message || "页面桥接初始化失败", true);
    return;
  }
  bindEvents();
  try {
    await load();
  } catch (error) {
    toast(error.message || "读取数据失败", true);
  }
}

init();
