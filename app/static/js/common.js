// Shared between the full admin app (app.js) and the restricted public
// dashboard (public.js). Keeps their read-only rendering identical without
// the public surface ever importing anything that can mutate state.

const state = { meta: null, services: [], statuses: [], tab: "dashboard", activeLayout: null };

// Dashboard tile grid: each track is one unit (px). A card's position/size
// is stored as {x, y, w, h} in 1-based grid-line units and applied as
// `grid-column: x / span w; grid-row: y / span h`. No grid gap - cards get
// their visual spacing from their own margin instead, so a drag delta of
// exactly GRID_UNIT px always means exactly 1 unit, no gap math.
const GRID_UNIT = 20;
const MIN_CARD_W = 16;
const MIN_CARD_H = 10;
const DEFAULT_CARD_W = 16;
const DEFAULT_CARD_H = 10;

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

function statusLabel(s) {
  return { ok: "OK", warn: "Warning", fail: "Failing", unknown: "Unknown", disabled: "Disabled" }[s] || s;
}

function iconUrlFor(type) {
  const icons = state.meta && state.meta.service_type_icons;
  if (!icons) return "";
  return icons[type] || icons.generic || "";
}

function typeIcon(type) {
  const url = iconUrlFor(type);
  if (!url) return el("span", { class: "type-icon-fallback", text: "\u{1F9E9}" }); // puzzle piece
  return el("img", {
    class: "type-icon",
    src: url,
    alt: type,
    loading: "lazy",
    onerror: function () { this.replaceWith(el("span", { class: "type-icon-fallback", text: "\u{1F9E9}" })); },
  });
}

async function loadMeta() {
  state.meta = await api("/api/meta");
}

async function ensureStatuses(force = false) {
  if (force || !state.statuses || state.statuses.length === 0) {
    try {
      state.statuses = await api("/api/status");
    } catch (_) { /* leave whatever we had */ }
  }
  return state.statuses;
}

async function ensureActiveLayout(force = false) {
  if (force || !state.activeLayout) {
    try {
      state.activeLayout = await api("/api/dashboard-layouts/active");
    } catch (_) { /* leave whatever we had, or null - computeCardLayout() falls back to defaults */ }
  }
  return state.activeLayout;
}

// Shelf-packs items left to right, wrapping to a new row of tracks whenever
// the next item would overflow totalCols - used only for cards that don't
// have a saved position yet (new services, or layouts saved before drag-to-
// move existed), starting below `offsetY` so they never land on top of a
// card that *does* have a saved position.
function packShelves(items, totalCols, offsetY) {
  const positions = new Map();
  let cursorX = 1, cursorY = offsetY, shelfH = 0;
  for (const it of items) {
    if (cursorX !== 1 && cursorX + it.w - 1 > totalCols) {
      cursorX = 1;
      cursorY += shelfH;
      shelfH = 0;
    }
    positions.set(it.id, { x: cursorX, y: cursorY });
    cursorX += it.w;
    shelfH = Math.max(shelfH, it.h);
  }
  return positions;
}

// Resolves every visible service's {x, y, w, h} for this render pass: saved
// positions are honored as-is, anything unset is shelf-packed into the
// remaining space. Returns a Map keyed by service id whose entry objects are
// mutated in place by the drag handlers below, so sibling cards always see
// each other's live (not just saved) position during a drag.
function computeCardLayout(statuses) {
  const grid = $("#dashboard-grid");
  const width = (grid && grid.clientWidth) || Math.max(0, window.innerWidth - 48);
  const totalCols = Math.max(MIN_CARD_W, Math.floor(width / GRID_UNIT));
  const sizes = (state.activeLayout && state.activeLayout.sizes) || {};

  const positions = new Map();
  const unset = [];
  let belowSaved = 1;
  for (const s of statuses) {
    const id = s.service.id;
    const saved = sizes[String(id)];
    const w = saved && Number.isFinite(saved.w) ? Math.max(MIN_CARD_W, saved.w) : DEFAULT_CARD_W;
    const h = saved && Number.isFinite(saved.h) ? Math.max(MIN_CARD_H, saved.h) : DEFAULT_CARD_H;
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      const x = Math.max(1, saved.x);
      const y = Math.max(1, saved.y);
      positions.set(id, { x, y, w, h });
      belowSaved = Math.max(belowSaved, y + h);
    } else {
      unset.push({ id, w, h });
    }
  }
  const packed = packShelves(unset, totalCols, positions.size ? belowSaved : 1);
  for (const it of unset) {
    const { x, y } = packed.get(it.id);
    positions.set(it.id, { x, y, w: it.w, h: it.h });
  }
  return positions;
}

function rectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

// ---------- dashboard (shared) ----------

function renderServiceCard(s, opts = {}, pos, positions) {
  const svc = s.service;
  const card = el("div", {
    class: "card",
    style: `grid-column: ${pos.x} / span ${pos.w}; grid-row: ${pos.y} / span ${pos.h};`,
  });
  card.dataset.serviceId = svc.id;

  card.appendChild(
    el("div", { class: `card-header${opts.interactive ? " drag-handle" : ""}` }, [
      el("div", { class: "title" }, [typeIcon(svc.type), el("span", { text: svc.name })]),
      el("span", { class: `badge ${s.overall_status}` }, [
        el("span", { class: `dot ${s.overall_status}` }),
        statusLabel(s.overall_status),
      ]),
    ])
  );
  const addressLabel = [svc.local_url, svc.remote_url].filter(Boolean).join(" / ");
  card.appendChild(
    el("div", { class: "card-sub" }, [
      `${svc.type} · ${addressLabel} · last checked ${relTime(s.last_checked)}`,
      s.active_notification_count > 0 ? el("span", { style: "color:var(--warn)" }, ` · ${s.active_notification_count} notification(s)`) : null,
    ])
  );

  const strip = el("div", { class: "uptime-strip", id: `strip-${svc.id}` });
  card.appendChild(strip);

  const checksBox = el("div", { class: "card-checks" });
  for (const r of s.latest_results) {
    checksBox.appendChild(
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
    checksBox.appendChild(el("div", { class: "check-row" }, [el("span", { class: "text-dim", text: "No results yet" })]));
  }
  card.appendChild(checksBox);

  if (opts.interactive) {
    card.appendChild(
      el("div", { class: "card-actions" }, [
        el("button", { class: "small", onclick: () => opts.onRunNow && opts.onRunNow(svc.id) }, "Run now"),
        el("button", { class: "small", onclick: () => opts.onHistory && opts.onHistory(svc.id) }, "History"),
      ])
    );
    attachResizeHandle(card, svc.id, pos, opts.onLayoutChange);
    attachMoveHandle(card, svc.id, pos, positions, opts.onLayoutChange);
  }

  return card;
}

// `onLayoutChange`, shared by both drag handlers below, always receives an
// *array* of `{id, patch}` updates - a plain resize or move only ever
// produces one, but a move that swaps two cards produces two that must be
// saved together in a single request. Saving them as two separate requests
// would race: both would be built from the same pre-drag `sizes` snapshot,
// and whichever request's PUT lands second would silently wipe out the
// first request's change (the server replaces `sizes` wholesale, it doesn't
// merge), leaving the swap only half-persisted.
function attachResizeHandle(card, serviceId, pos, onLayoutChange) {
  const handle = el("div", { class: "resize-handle", title: "Drag to resize" });
  card.appendChild(handle);

  let start = null;

  function onPointerMove(e) {
    const dx = e.clientX - start.px;
    const dy = e.clientY - start.py;
    pos.w = Math.max(MIN_CARD_W, start.w + Math.round(dx / GRID_UNIT));
    pos.h = Math.max(MIN_CARD_H, start.h + Math.round(dy / GRID_UNIT));
    card.style.gridColumn = `${pos.x} / span ${pos.w}`;
    card.style.gridRow = `${pos.y} / span ${pos.h}`;
  }

  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    if (onLayoutChange && (pos.w !== start.w || pos.h !== start.h)) {
      onLayoutChange([{ id: serviceId, patch: { w: pos.w, h: pos.h } }]);
    }
  }

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    start = { px: e.clientX, py: e.clientY, w: pos.w, h: pos.h };
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });
}

// Drag-to-reposition from the card's title bar, like moving a window. Cards
// snap to the same grid the resize handle uses. If the drop spot overlaps
// exactly one other card, they swap places; overlapping more than one card
// is treated as an invalid drop and the card snaps back.
function attachMoveHandle(card, serviceId, pos, positions, onLayoutChange) {
  const header = card.querySelector(".card-header");
  if (!header) return;

  let start = null;

  function onPointerMove(e) {
    const dx = e.clientX - start.px;
    const dy = e.clientY - start.py;
    pos.x = Math.max(1, start.x + Math.round(dx / GRID_UNIT));
    pos.y = Math.max(1, start.y + Math.round(dy / GRID_UNIT));
    card.style.gridColumn = `${pos.x} / span ${pos.w}`;
    card.style.gridRow = `${pos.y} / span ${pos.h}`;
  }

  function snapBackTo(x, y) {
    pos.x = x;
    pos.y = y;
    card.style.gridColumn = `${pos.x} / span ${pos.w}`;
    card.style.gridRow = `${pos.y} / span ${pos.h}`;
  }

  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    card.classList.remove("dragging");

    if (pos.x === start.x && pos.y === start.y) return;

    const overlapping = [];
    for (const [otherId, otherPos] of positions) {
      if (otherId === serviceId) continue;
      if (rectsOverlap(pos, otherPos)) overlapping.push(otherId);
    }

    if (overlapping.length === 0) {
      onLayoutChange && onLayoutChange([{ id: serviceId, patch: { x: pos.x, y: pos.y } }]);
    } else if (overlapping.length === 1) {
      const otherId = overlapping[0];
      const otherPos = positions.get(otherId);
      const otherCard = $(`.card[data-service-id="${otherId}"]`);
      const originX = start.x, originY = start.y;
      otherPos.x = originX;
      otherPos.y = originY;
      if (otherCard) {
        otherCard.style.gridColumn = `${otherPos.x} / span ${otherPos.w}`;
        otherCard.style.gridRow = `${otherPos.y} / span ${otherPos.h}`;
      }
      onLayoutChange && onLayoutChange([
        { id: serviceId, patch: { x: pos.x, y: pos.y } },
        { id: otherId, patch: { x: otherPos.x, y: otherPos.y } },
      ]);
    } else {
      snapBackTo(start.x, start.y);
    }
  }

  header.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    start = { px: e.clientX, py: e.clientY, x: pos.x, y: pos.y };
    card.classList.add("dragging");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });
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

async function loadDashboard(cardOpts = {}) {
  const statuses = await ensureStatuses(true);
  await ensureActiveLayout();
  const grid = $("#dashboard-grid");
  if (!grid) return;
  grid.innerHTML = "";

  if (statuses.length === 0) {
    grid.appendChild(el("div", { class: "empty-state", text: "No services configured yet." }));
  }

  const counts = { ok: 0, warn: 0, fail: 0, unknown: 0, disabled: 0 };
  statuses.forEach((s) => { counts[s.overall_status] = (counts[s.overall_status] || 0) + 1; });
  const pill = $("#summary-pill");
  if (pill) {
    pill.innerHTML = "";
    ["ok", "warn", "fail"].forEach((k) => {
      pill.appendChild(el("span", {}, [el("span", { class: `dot ${k}` }), `${counts[k] || 0} ${k}`]));
    });
  }
  const refresh = $("#last-refresh");
  if (refresh) refresh.textContent = "Updated " + new Date().toLocaleTimeString();

  const positions = computeCardLayout(statuses);
  for (const s of statuses) {
    grid.appendChild(renderServiceCard(s, cardOpts, positions.get(s.service.id), positions));
  }
  for (const s of statuses) {
    loadUptimeStrip(s.service.id);
  }
}

// ---------- notifications (shared) ----------

async function loadNotifications() {
  const showResolvedBox = $("#show-resolved");
  const activeOnly = showResolvedBox ? !showResolvedBox.checked : true;
  let items;
  try {
    items = await api(`/api/notifications?active_only=${activeOnly}`);
  } catch (e) {
    toast("Failed to load notifications: " + e.message, true);
    return;
  }
  const statuses = await ensureStatuses();
  const svcById = new Map(statuses.map((s) => [s.service.id, s.service]));
  const list = $("#notifications-list");
  if (!list) return;
  list.innerHTML = "";
  if (items.length === 0) {
    list.appendChild(el("div", { class: "empty-state", text: "No notifications \u{1F389}" }));
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

// ---------- history (shared) ----------

async function loadHistoryTab() {
  const select = $("#history-service");
  if (!select) return;
  if (select.options.length === 0) {
    const statuses = await ensureStatuses();
    for (const s of statuses) {
      select.appendChild(el("option", { value: s.service.id, text: s.service.name }));
    }
    if (!select.value && statuses.length) select.value = statuses[0].service.id;
  }
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
