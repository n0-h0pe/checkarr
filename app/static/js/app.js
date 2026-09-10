const state = {
  meta: null,
  services: [],
  tab: "dashboard",
  historyServiceId: null,
};

// ---------- helpers ----------

function $(sel, root = document) { return root.querySelector(sel); }
function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

function toast(message, isError = false) {
  const t = el("div", { class: "toast" + (isError ? " error" : ""), text: message });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function relTime(iso) {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z"))) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmtTime(iso) {
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  return d.toLocaleString();
}

const TYPE_ICON = { radarr: "🎬", sonarr: "📺", prowlarr: "🔎", plex: "▶️", jellyfin: "🪼", generic: "🧩" };

function statusLabel(s) {
  return { ok: "OK", warn: "Warning", fail: "Failing", unknown: "Unknown", disabled: "Disabled" }[s] || s;
}

// ---------- tabs ----------

function initTabs() {
  $all(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

function switchTab(tab) {
  state.tab = tab;
  $all(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $all(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "dashboard") loadDashboard();
  if (tab === "notifications") loadNotifications();
  if (tab === "history") loadHistoryTab();
  if (tab === "settings") loadSettings();
}

// ---------- dashboard ----------

async function loadDashboard() {
  let statuses;
  try {
    statuses = await api("/api/status");
  } catch (e) {
    toast("Failed to load status: " + e.message, true);
    return;
  }

  const grid = $("#dashboard-grid");
  grid.innerHTML = "";

  if (statuses.length === 0) {
    grid.appendChild(el("div", { class: "empty-state", text: "No services configured yet. Add one in Settings." }));
  }

  const counts = { ok: 0, warn: 0, fail: 0, unknown: 0, disabled: 0 };
  statuses.forEach((s) => { counts[s.overall_status] = (counts[s.overall_status] || 0) + 1; });
  $("#summary-pill").innerHTML = "";
  ["ok", "warn", "fail"].forEach((k) => {
    $("#summary-pill").appendChild(
      el("span", {}, [el("span", { class: `dot ${k}` }), `${counts[k] || 0} ${k}`])
    );
  });
  $("#last-refresh").textContent = "Updated " + new Date().toLocaleTimeString();

  for (const s of statuses) {
    grid.appendChild(renderServiceCard(s));
  }

  // Uptime strips, loaded after initial paint.
  for (const s of statuses) {
    loadUptimeStrip(s.service.id);
  }
}

function renderServiceCard(s) {
  const svc = s.service;
  const card = el("div", { class: "card" });

  card.appendChild(
    el("div", { class: "card-header" }, [
      el("div", { class: "title" }, [
        el("span", { class: "type-icon", text: TYPE_ICON[svc.type] || "🧩" }),
        el("span", { text: svc.name }),
      ]),
      el("span", { class: `badge ${s.overall_status}` }, [
        el("span", { class: `dot ${s.overall_status}` }),
        statusLabel(s.overall_status),
      ]),
    ])
  );
  card.appendChild(
    el("div", { class: "card-sub" }, [
      `${svc.type} · ${svc.base_url} · last checked ${relTime(s.last_checked)}`,
      s.active_notification_count > 0 ? el("span", { style: "color:var(--warn)" }, ` · ${s.active_notification_count} notification(s)`) : null,
    ])
  );

  const strip = el("div", { class: "uptime-strip", id: `strip-${svc.id}` });
  card.appendChild(strip);

  for (const r of s.latest_results) {
    card.appendChild(
      el("div", { class: "check-row" }, [
        el("div", { class: "name" }, [
          el("span", { class: `dot ${r.status}` }),
          el("span", { class: "label", text: r.check_name }),
        ]),
        el("div", { class: "msg", title: r.message, text: r.message }),
      ])
    );
  }
  if (s.latest_results.length === 0) {
    card.appendChild(el("div", { class: "check-row" }, [el("span", { class: "text-dim", text: "No results yet" })]));
  }

  card.appendChild(
    el("div", { class: "card-actions" }, [
      el("button", { class: "small", onclick: () => runNow(svc.id) }, "Run now"),
      el("button", { class: "small", onclick: () => { switchTab("history"); $("#history-service").value = svc.id; loadHistoryTab(); } }, "History"),
    ])
  );

  return card;
}

async function loadUptimeStrip(serviceId) {
  let rows;
  try {
    rows = await api(`/api/history?service_id=${serviceId}&hours=24&limit=300`);
  } catch (_) {
    return;
  }
  const strip = $(`#strip-${serviceId}`);
  if (!strip) return;

  const byTs = new Map();
  for (const r of rows) {
    const key = r.timestamp;
    const worst = byTs.get(key);
    const order = { ok: 0, warn: 1, fail: 2 };
    if (!worst || order[r.status] > order[worst]) byTs.set(key, r.status);
  }
  const timestamps = Array.from(byTs.keys()).sort();
  const last = timestamps.slice(-20);

  strip.innerHTML = "";
  if (last.length === 0) {
    strip.style.display = "none";
    return;
  }
  for (const ts of last) {
    strip.appendChild(el("div", { class: `bar ${byTs.get(ts)}`, title: fmtTime(ts) }));
  }
}

async function runNow(serviceId) {
  try {
    await api(`/api/services/${serviceId}/run-now`, { method: "POST" });
    toast("Checks run");
  } catch (e) {
    toast("Run failed: " + e.message, true);
  }
  if (state.tab === "dashboard") loadDashboard();
  if (state.tab === "settings") loadSettings();
}

// ---------- notifications ----------

async function loadNotifications() {
  const activeOnly = !$("#show-resolved").checked;
  let items;
  try {
    items = await api(`/api/notifications?active_only=${activeOnly}`);
  } catch (e) {
    toast("Failed to load notifications: " + e.message, true);
    return;
  }
  const svcById = new Map(state.services.map((s) => [s.id, s]));
  const list = $("#notifications-list");
  list.innerHTML = "";
  if (items.length === 0) {
    list.appendChild(el("div", { class: "empty-state", text: "No notifications 🎉" }));
    return;
  }
  for (const n of items) {
    const svc = svcById.get(n.service_id);
    const row = el("div", { class: "notif-row" }, [
      el("div", { class: "top" }, [
        el("span", { class: `badge ${n.severity}`, text: n.severity }),
        el("span", { class: "service-name", text: svc ? svc.name : `Service #${n.service_id}` }),
        n.resolved ? el("span", { class: "badge ok", text: "resolved" }) : null,
      ]),
      el("div", { class: "msg", text: n.message }),
      el("div", { class: "meta" }, [
        `first seen ${fmtTime(n.first_seen)} · last seen ${fmtTime(n.last_seen)}`,
        n.wiki_url ? el("span", {}, [" · ", el("a", { href: n.wiki_url, target: "_blank", rel: "noopener", text: "more info" })]) : null,
      ]),
    ]);
    list.appendChild(row);
  }
}

// ---------- history ----------

async function loadHistoryTab() {
  const select = $("#history-service");
  if (select.options.length === 0) {
    for (const s of state.services) {
      select.appendChild(el("option", { value: s.id, text: s.name }));
    }
  }
  if (!select.value && state.services.length) select.value = state.services[0].id;
  const serviceId = select.value;
  const hours = $("#history-hours").value;
  const body = $("#history-body");
  body.innerHTML = "";
  if (!serviceId) return;

  let rows;
  try {
    rows = await api(`/api/history?service_id=${serviceId}&hours=${hours}&limit=500`);
  } catch (e) {
    toast("Failed to load history: " + e.message, true);
    return;
  }
  for (const r of rows) {
    body.appendChild(
      el("tr", {}, [
        el("td", { text: fmtTime(r.timestamp) }),
        el("td", { text: r.check_name }),
        el("td", {}, el("span", { class: `badge ${r.status}`, text: r.status })),
        el("td", { text: r.response_time_ms ? `${Math.round(r.response_time_ms)} ms` : "-" }),
        el("td", { text: r.message }),
      ])
    );
  }
  if (rows.length === 0) {
    body.appendChild(el("tr", {}, el("td", { colspan: "5", class: "empty-state", text: "No data in this window" })));
  }
}

// ---------- settings: services ----------

async function loadSettings() {
  try {
    state.services = await api("/api/services");
  } catch (e) {
    toast("Failed to load services: " + e.message, true);
    return;
  }
  const body = $("#services-body");
  body.innerHTML = "";
  for (const svc of state.services) {
    body.appendChild(renderServiceRow(svc));
  }
}

function renderServiceRow(svc) {
  const tr = el("tr", { class: "service-row" });
  const expandBtn = el("button", { class: "small" }, "▸");
  tr.appendChild(el("td", {}, expandBtn));
  tr.appendChild(el("td", { text: svc.name }));
  tr.appendChild(el("td", {}, [TYPE_ICON[svc.type] || "", " " + svc.type]));
  tr.appendChild(el("td", { text: svc.base_url }));
  tr.appendChild(el("td", { text: svc.poll_interval_seconds ? `${svc.poll_interval_seconds}s` : "default" }));
  tr.appendChild(el("td", {}, el("span", { class: `badge ${svc.enabled ? "ok" : "disabled"}`, text: svc.enabled ? "enabled" : "disabled" })));

  const actions = el("div", { style: "display:flex; gap:6px;" }, [
    el("button", { class: "small", onclick: (e) => { e.stopPropagation(); openServiceModal(svc); } }, "Edit"),
    el("button", { class: "small danger", onclick: (e) => { e.stopPropagation(); deleteService(svc); } }, "Delete"),
  ]);
  tr.appendChild(el("td", {}, actions));

  const detailRow = el("tr", {}, el("td", { colspan: "7" }, renderChecksPanel(svc)));
  detailRow.style.display = "none";

  const toggle = () => {
    const open = detailRow.style.display !== "none";
    detailRow.style.display = open ? "none" : "table-row";
    expandBtn.textContent = open ? "▸" : "▾";
  };
  tr.addEventListener("click", toggle);

  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(tr);
  wrapper.appendChild(detailRow);
  return wrapper;
}

function renderChecksPanel(svc) {
  const panel = el("div", { class: "checks-subpanel" });
  panel.appendChild(
    el("div", { style: "display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;" }, [
      el("strong", { text: "Checks" }),
      el("button", { class: "small primary", onclick: () => openCheckModal(svc) }, "+ Add check"),
    ])
  );
  if (svc.checks.length === 0) {
    panel.appendChild(el("div", { class: "text-dim", text: "No checks configured" }));
  }
  for (const c of svc.checks) {
    panel.appendChild(
      el("div", { class: "check-item" }, [
        el("span", {}, [
          el("span", { class: `badge ${c.enabled ? "ok" : "disabled"}`, text: c.type }),
          " " + c.name,
        ]),
        el("div", { style: "display:flex; gap:6px;" }, [
          el("button", { class: "small", onclick: () => openCheckModal(svc, c) }, "Edit"),
          c.is_builtin ? null : el("button", { class: "small danger", onclick: () => deleteCheck(svc, c) }, "Delete"),
        ]),
      ])
    );
  }
  return panel;
}

async function deleteService(svc) {
  if (!confirm(`Delete service "${svc.name}"? This removes its history and notifications too.`)) return;
  try {
    await api(`/api/services/${svc.id}`, { method: "DELETE" });
    toast("Service deleted");
    loadSettings();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

async function deleteCheck(svc, check) {
  if (!confirm(`Delete check "${check.name}"?`)) return;
  try {
    await api(`/api/services/${svc.id}/checks/${check.id}`, { method: "DELETE" });
    toast("Check deleted");
    loadSettings();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

// ---------- service modal ----------

function openServiceModal(svc = null) {
  $("#service-modal-title").textContent = svc ? "Edit service" : "Add service";
  $("#svc-id").value = svc ? svc.id : "";
  $("#svc-name").value = svc ? svc.name : "";
  $("#svc-url").value = svc ? svc.base_url : "";
  $("#svc-key").value = "";
  $("#svc-key-hint").textContent = svc && svc.has_api_key ? "(key already set - leave blank to keep)" : "";
  $("#svc-interval").value = svc && svc.poll_interval_seconds ? svc.poll_interval_seconds : "";
  $("#svc-verify-ssl").checked = svc ? svc.verify_ssl : true;
  $("#svc-enabled").checked = svc ? svc.enabled : true;
  $("#svc-notes").value = svc && svc.notes ? svc.notes : "";

  const typeSelect = $("#svc-type");
  typeSelect.innerHTML = "";
  for (const t of state.meta.service_types) {
    typeSelect.appendChild(el("option", { value: t, text: t }));
  }
  typeSelect.disabled = !!svc;
  if (svc) typeSelect.value = svc.type;

  $("#service-modal").classList.remove("hidden");
}

function closeServiceModal() {
  $("#service-modal").classList.add("hidden");
}

async function submitServiceForm(ev) {
  ev.preventDefault();
  const id = $("#svc-id").value;
  const payload = {
    name: $("#svc-name").value.trim(),
    base_url: $("#svc-url").value.trim(),
    verify_ssl: $("#svc-verify-ssl").checked,
    enabled: $("#svc-enabled").checked,
    poll_interval_seconds: $("#svc-interval").value ? parseInt($("#svc-interval").value, 10) : null,
    notes: $("#svc-notes").value.trim() || null,
  };
  const key = $("#svc-key").value;
  if (key) payload.api_key = key;

  try {
    if (id) {
      await api(`/api/services/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      payload.type = $("#svc-type").value;
      await api("/api/services", { method: "POST", body: JSON.stringify(payload) });
    }
    toast("Service saved");
    closeServiceModal();
    loadSettings();
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

// ---------- check modal ----------

function checkTypesFor(serviceType) {
  return state.meta.check_types.filter((ct) => ct.applies_to.includes(serviceType));
}

function openCheckModal(svc, check = null) {
  $("#check-modal-title").textContent = check ? "Edit check" : "Add check";
  $("#chk-service-id").value = svc.id;
  $("#chk-id").value = check ? check.id : "";
  $("#chk-name").value = check ? check.name : "";
  $("#chk-enabled").checked = check ? check.enabled : true;

  const typeSelect = $("#chk-type");
  typeSelect.innerHTML = "";
  for (const ct of checkTypesFor(svc.type)) {
    typeSelect.appendChild(el("option", { value: ct.type, text: ct.label }));
  }
  typeSelect.value = check ? check.type : typeSelect.options[0]?.value;
  typeSelect.onchange = () => renderDynamicFields(svc, typeSelect.value, check && check.type === typeSelect.value ? check.config : {});
  renderDynamicFields(svc, typeSelect.value, check ? check.config : {});

  $("#check-modal").classList.remove("hidden");
}

function closeCheckModal() {
  $("#check-modal").classList.add("hidden");
}

function renderDynamicFields(svc, checkType, existingConfig = {}) {
  const container = $("#chk-dynamic-fields");
  container.innerHTML = "";
  const meta = state.meta.check_types.find((ct) => ct.type === checkType);
  if (!meta) return;

  for (const f of meta.fields) {
    let value = existingConfig[f.key];
    if (f.key === "expected_status_codes" && Array.isArray(value)) value = value.join(",");
    if (value === undefined || value === null) value = f.default ?? "";

    const fieldWrap = el("div", { class: "field" }, [el("label", { text: f.label })]);
    let input;
    if (f.kind === "select") {
      input = el("select", { id: `chk-field-${f.key}` });
      for (const opt of f.options) input.appendChild(el("option", { value: opt, text: opt }));
      input.value = value;
    } else if (f.kind === "number") {
      input = el("input", { type: "number", id: `chk-field-${f.key}`, value: value });
    } else {
      input = el("input", { type: "text", id: `chk-field-${f.key}`, value: value });
    }
    fieldWrap.appendChild(input);
    container.appendChild(fieldWrap);
  }

  if (checkType === "filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Note: this container must have the same host path bind-mounted for this check to see it. Prefer the *arr Root Folder check when available - it needs no extra mounts." })
    );
  }
}

async function submitCheckForm(ev) {
  ev.preventDefault();
  const serviceId = $("#chk-service-id").value;
  const checkId = $("#chk-id").value;
  const checkType = $("#chk-type").value;
  const meta = state.meta.check_types.find((ct) => ct.type === checkType);

  const config = {};
  for (const f of meta.fields) {
    const input = $(`#chk-field-${f.key}`);
    if (!input) continue;
    let val = input.value;
    if (f.key === "expected_status_codes") {
      config[f.key] = val.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n));
    } else if (f.kind === "number") {
      config[f.key] = val === "" ? null : Number(val);
    } else {
      config[f.key] = val;
    }
  }

  const payload = {
    name: $("#chk-name").value.trim(),
    type: checkType,
    config,
    enabled: $("#chk-enabled").checked,
  };

  try {
    if (checkId) {
      await api(`/api/services/${serviceId}/checks/${checkId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api(`/api/services/${serviceId}/checks`, { method: "POST", body: JSON.stringify(payload) });
    }
    toast("Check saved");
    closeCheckModal();
    loadSettings();
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

// ---------- init ----------

async function init() {
  initTabs();
  state.meta = await api("/api/meta");
  state.services = await api("/api/services");

  $("#add-service-btn").addEventListener("click", () => openServiceModal());
  $("#service-cancel").addEventListener("click", closeServiceModal);
  $("#service-form").addEventListener("submit", submitServiceForm);
  $("#check-cancel").addEventListener("click", closeCheckModal);
  $("#check-form").addEventListener("submit", submitCheckForm);
  $("#show-resolved").addEventListener("change", loadNotifications);
  $("#history-service").addEventListener("change", loadHistoryTab);
  $("#history-hours").addEventListener("change", loadHistoryTab);

  loadDashboard();
  setInterval(() => { if (state.tab === "dashboard") loadDashboard(); }, 30000);
  setInterval(() => { if (state.tab === "notifications") loadNotifications(); }, 30000);
}

document.addEventListener("DOMContentLoaded", init);
