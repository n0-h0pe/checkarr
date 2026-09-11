// Shared between the full admin app (app.js) and the restricted public
// dashboard (public.js). Keeps their read-only rendering identical without
// the public surface ever importing anything that can mutate state.

const state = { meta: null, services: [], statuses: [], channels: [], groups: [], schedules: [], tab: "dashboard", activeLayout: null, lastGridColumns: null };

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

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name, value, days) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

// The dashboard's uptime strip: a fixed number of bars spanning a
// user-picked range (the dropdown in the top bar), each bar the worst
// status seen in its slice of that range - grey ("no-data", the strip's own
// default bar color) if nothing was polled in that slice at all. "Just the
// last poll" is a special single-bar case using the live status already in
// hand rather than a history fetch.
const UPTIME_RANGES = [
  { value: "last", minutes: 0, label: "Just the last poll" },
  { value: "1", minutes: 1, label: "Last 1 minute" },
  { value: "3", minutes: 3, label: "Last 3 minutes" },
  { value: "5", minutes: 5, label: "Last 5 minutes" },
  { value: "10", minutes: 10, label: "Last 10 minutes" },
  { value: "15", minutes: 15, label: "Last 15 minutes" },
  { value: "30", minutes: 30, label: "Last 30 minutes" },
  { value: "60", minutes: 60, label: "Last 1 hour" },
  { value: "120", minutes: 120, label: "Last 2 hours" },
  { value: "300", minutes: 300, label: "Last 5 hours" },
  { value: "480", minutes: 480, label: "Last 8 hours" },
  { value: "720", minutes: 720, label: "Last 12 hours" },
  { value: "1440", minutes: 1440, label: "Last 24 hours" },
  { value: "2880", minutes: 2880, label: "Last 48 hours" },
  { value: "10080", minutes: 10080, label: "Last 1 week" },
];
const DEFAULT_UPTIME_RANGE = "2880";
const UPTIME_BAR_COUNT = 20;

function loadUptimeRange() {
  const saved = getCookie("hc_uptime_range");
  return UPTIME_RANGES.some((r) => r.value === saved) ? saved : DEFAULT_UPTIME_RANGE;
}

function saveUptimeRange(value) {
  setCookie("hc_uptime_range", value, 365);
}

state.uptimeRange = loadUptimeRange();

// The /api/history `hours` query param the current uptime range maps to -
// shared by the dashboard's uptime strip and the History tab, which both
// read off the one top-bar dropdown now (see initUptimeRangeSelect below).
// Backend requires >=1 (`ge=1`), so "just the last poll" (0 minutes) still
// has to ask for *something* - 1 hour is the smallest meaningful window.
function uptimeRangeHours() {
  const range = UPTIME_RANGES.find((r) => r.value === state.uptimeRange) || UPTIME_RANGES.find((r) => r.value === DEFAULT_UPTIME_RANGE);
  return Math.min(720, Math.max(1, Math.ceil(range.minutes / 60)));
}

// Shared by both the admin header and the public dashboard's equivalent bar
// - same markup (#uptime-range-select), same behavior either side. Also
// drives the History tab/page's range now (no separate dropdown there
// anymore) - loadHistoryTab no-ops itself when its own elements aren't on
// the page, so calling it unconditionally here is harmless.
function initUptimeRangeSelect() {
  const select = $("#uptime-range-select");
  if (!select) return;
  select.innerHTML = "";
  for (const r of UPTIME_RANGES) {
    select.appendChild(el("option", { value: r.value, text: r.label, selected: r.value === state.uptimeRange ? "selected" : null }));
  }
  select.addEventListener("change", () => {
    state.uptimeRange = select.value;
    saveUptimeRange(select.value);
    for (const s of state.statuses) loadUptimeStrip(s.service.id);
    loadHistoryTab();
  });
}

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

// A short (a handful of characters) stand-in for a check's full message, for
// screens too narrow to show both a check's name and its full message on
// one line (see .msg-short/.msg-full in style.css) - a quick pattern match
// against common message shapes rather than a real per-check-type summary,
// so it degrades to just the plain status word for anything it doesn't
// recognize instead of guessing wrong.
function shortCheckSummary(checkType, status, message) {
  const label = { ok: "OK", warn: "Warn", fail: "Fail", unknown: "?", disabled: "Off" }[status] || status;
  const msg = message || "";

  const httpMatch = msg.match(/HTTP (\d{3})/);
  if (httpMatch) return `${httpMatch[1]} ${label}`;

  if (/disk_space/.test(checkType)) {
    const pctMatch = msg.match(/([\d.]+)%\s+(?:free|of)/);
    if (pctMatch) return `${pctMatch[1]}% free`;
  }
  if (/filesystem|root_folder|ftp_path/.test(checkType)) return `Files ${label}`;
  if (/login/.test(checkType)) return `Login ${label}`;
  if (/rpc_status/.test(checkType)) return `RPC ${label}`;
  if (/tmdb_status/.test(checkType)) return `TMDB ${label}`;
  if (/remote_access/.test(checkType)) return `Remote ${label}`;
  if (/health/.test(checkType)) return `Health ${label}`;
  return label;
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

function rectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

// A layout remembers, in `columns`, how many grid columns wide the browser
// window was the last time it was edited (see persistCardLayout in app.js).
// If the window viewing it now is narrower than that - cards would run off
// the edge or get clipped - every card is re-wrapped into the narrower
// width, keeping their saved top-to-bottom/left-to-right order. This is
// purely a rendering-time fallback: nothing here is written back, so widening
// the window back out (or just reopening it later at its usual size) shows
// the exact saved arrangement again, untouched. Editing while reflowed is
// still allowed - saving from there simply adopts the narrower width as the
// layout's new reference width, same as editing at any other width would.
function computeCardLayout(statuses) {
  const grid = $("#dashboard-grid");
  const width = (grid && grid.clientWidth) || Math.max(0, window.innerWidth - 48);
  const totalCols = Math.max(MIN_CARD_W, Math.floor(width / GRID_UNIT));
  state.lastGridColumns = totalCols;

  const layout = state.activeLayout;
  const sizes = (layout && layout.sizes) || {};
  const savedCols = layout && Number.isFinite(layout.columns) ? layout.columns : null;
  const reflow = savedCols !== null && totalCols < savedCols;

  const entries = statuses.map((s) => {
    const id = s.service.id;
    const saved = sizes[String(id)];
    // Clamped to totalCols (never below MIN_CARD_W, since totalCols itself
    // never is) so a card widened on a big desktop window can't render
    // wider than the actual screen on a narrow one - display-only, like the
    // reflow above, so the saved width still comes back on a wide-enough
    // screen untouched.
    const savedW = saved && Number.isFinite(saved.w) ? Math.max(MIN_CARD_W, saved.w) : DEFAULT_CARD_W;
    // On mobile every card is a full-width single-column list, always -
    // clamping a saved/default width down to totalCols (as below) still
    // leaves a gap for anything narrower than totalCols (a brand new
    // service with no saved size, or a card saved narrower on desktop), so
    // mobile forces w to totalCols outright rather than just capping it.
    const w = isMobileViewport() ? totalCols : Math.min(savedW, totalCols);
    const h = saved && Number.isFinite(saved.h) ? Math.max(MIN_CARD_H, saved.h) : DEFAULT_CARD_H;
    const hasPos = saved && Number.isFinite(saved.x) && Number.isFinite(saved.y);
    return {
      id, w, h,
      x: hasPos ? Math.max(1, saved.x) : null,
      y: hasPos ? Math.max(1, saved.y) : null,
    };
  });

  const positions = new Map();
  if (reflow) {
    const ordered = entries.slice().sort((a, b) => {
      const ay = a.y === null ? Infinity : a.y, by = b.y === null ? Infinity : b.y;
      if (ay !== by) return ay - by;
      const ax = a.x === null ? Infinity : a.x, bx = b.x === null ? Infinity : b.x;
      return ax - bx;
    });
    const packed = packShelves(ordered, totalCols, 1);
    for (const it of ordered) {
      const { x, y } = packed.get(it.id);
      positions.set(it.id, { x, y, w: it.w, h: it.h });
    }
  } else {
    const unset = [];
    let belowSaved = 1;
    for (const it of entries) {
      if (it.x !== null) {
        positions.set(it.id, { x: it.x, y: it.y, w: it.w, h: it.h });
        belowSaved = Math.max(belowSaved, it.y + it.h);
      } else {
        unset.push(it);
      }
    }
    const packed = packShelves(unset, totalCols, positions.size ? belowSaved : 1);
    for (const it of unset) {
      const { x, y } = packed.get(it.id);
      positions.set(it.id, { x, y, w: it.w, h: it.h });
    }
  }
  return positions;
}

// Cascades a dropped card's new position through the rest of the grid: any
// card it now overlaps gets pushed straight down below it, and anything
// *that* push newly overlaps gets pushed too, breadth-first, until nothing
// overlaps. Cards only ever move down, never sideways or up - simple and
// predictable, and it means "drop anywhere" always succeeds instead of
// bailing out when more than one card is in the way. Returns the set of
// service ids whose position object was actually changed, so the caller
// knows what needs restyling and saving.
function resolveCollisions(draggedId, positions) {
  const changed = new Set([draggedId]);
  const queue = [draggedId];
  let guard = 0;
  while (queue.length && guard++ < 2000) {
    const anchor = positions.get(queue.shift());
    for (const [id, p] of positions) {
      if (p === anchor) continue;
      if (!rectsOverlap(anchor, p)) continue;
      const pushedY = anchor.y + anchor.h;
      if (p.y < pushedY) {
        p.y = pushedY;
        changed.add(id);
        queue.push(id);
      }
    }
  }
  return changed;
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
    el("div", { class: "card-header" }, [
      el("div", { class: "title" }, [typeIcon(svc.type), el("span", { text: svc.name })]),
      el("span", { class: `badge ${s.overall_status}` }, [
        el("span", { class: `dot ${s.overall_status}` }),
        statusLabel(s.overall_status),
      ]),
    ])
  );
  // Everything between the header and the action buttons lives in its own
  // wrapper - it's what the mobile reorder overlay below covers/blurs, and
  // keeping it separate from card-actions means Run now/History stay
  // usable even while that overlay is up.
  const body = el("div", { class: "card-body" });
  const addressLabel = [svc.local_url, svc.remote_url].filter(Boolean).join(" / ");
  body.appendChild(
    el("div", { class: "card-sub" }, [
      `${svc.type} · ${addressLabel} · last checked ${relTime(s.last_checked)}`,
      s.active_notification_count > 0 ? el("span", { style: "color:var(--warn)" }, ` · ${s.active_notification_count} notification(s)`) : null,
    ])
  );

  const strip = el("div", { class: "uptime-strip", id: `strip-${svc.id}` });
  body.appendChild(strip);

  const checksBox = el("div", { class: "card-checks" });
  for (const r of s.latest_results) {
    checksBox.appendChild(
      el("div", { class: "check-row" }, [
        el("div", { class: "name" }, [
          el("span", { class: `dot ${r.status}` }),
          el("span", { class: "label", text: r.check_name }),
        ]),
        el("div", { class: "msg", title: r.message }, [
          el("span", { class: "msg-full", text: r.message }),
          el("span", { class: "msg-short", text: shortCheckSummary(r.check_type, r.status, r.message) }),
        ]),
      ])
    );
  }
  if (s.latest_results.length === 0) {
    checksBox.appendChild(el("div", { class: "check-row" }, [el("span", { class: "text-dim", text: "No results yet" })]));
  }
  body.appendChild(checksBox);
  card.appendChild(body);

  if (opts.interactive) {
    card.appendChild(
      el("div", { class: "card-actions" }, [
        el("button", { class: "small", onclick: () => opts.onRunNow && opts.onRunNow(svc.id) }, "Run now"),
        el("button", { class: "small", onclick: () => opts.onHistory && opts.onHistory(svc.id) }, "History"),
      ])
    );
  }
  if (opts.editable) {
    card.classList.add("card-editable");
    if (isMobileViewport()) {
      attachMobileReorderControls(body, svc.id, positions, opts.onLayoutChange);
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange, positions);
    } else {
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange);
      attachMoveHandle(card, svc.id, pos, positions, opts.onLayoutChange);
    }
  }

  return card;
}

// Below ~700px (same breakpoint as the CSS), there's only ever one card per
// row anyway - free-form drag-to-move/resize stops being a meaningful
// interaction (there's nowhere else on the row to drag to) and is fiddly on
// a touchscreen besides, so edit mode switches to plain list reordering
// instead. Matches the `main { max-width: 700px }`-ish breakpoint in
// style.css, not a coincidence - keep them in sync if either changes.
function isMobileViewport() {
  return window.matchMedia("(max-width: 700px)").matches;
}

const REORDER_ICONS = {
  top: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="5" x2="20" y2="5"/><polyline points="6,13 12,8 18,13"/><polyline points="6,19 12,14 18,19"/></svg>',
  up: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,15 12,9 18,15"/></svg>',
  down: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,9 12,15 18,9"/></svg>',
  bottom: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="19" x2="20" y2="19"/><polyline points="6,11 12,16 18,11"/><polyline points="6,5 12,10 18,5"/></svg>',
};

function attachMobileReorderControls(cardBody, serviceId, positions, onLayoutChange) {
  const overlay = el("div", { class: "card-reorder-overlay" });
  const buttons = [
    ["top", "Move to top"],
    ["up", "Move up"],
    ["down", "Move down"],
    ["bottom", "Move to bottom"],
  ];
  for (const [action, title] of buttons) {
    const btn = el("button", { type: "button", class: "reorder-btn", title });
    btn.innerHTML = REORDER_ICONS[action];
    btn.addEventListener("click", () => reorderCardMobile(serviceId, action, positions, onLayoutChange));
    overlay.appendChild(btn);
  }
  cardBody.appendChild(overlay);
}

// Treats the dashboard as a plain top-to-bottom list (true on mobile, where
// every card is already full-width): given the ids in their intended order,
// stacks each on the previous one's bottom edge and forces every card to
// the same full width - "a list", not a freeform grid. Used both after an
// explicit reorder and after a height resize (which can't change the order,
// but still needs everything below the resized card to shift to match).
// Returns just the updates for cards that actually changed, for the same
// onLayoutChange/persistCardLayout path a desktop drag uses - which also
// stamps `columns` to the current (mobile) width, same as any other edit,
// see computeCardLayout's big comment for why.
function renumberMobileList(orderedIds, positions, totalCols) {
  const updates = [];
  let y = 1;
  for (const id of orderedIds) {
    const p = positions.get(id);
    const changed = p.x !== 1 || p.y !== y || p.w !== totalCols;
    p.x = 1;
    p.y = y;
    p.w = totalCols;
    if (changed) updates.push({ id, patch: { x: p.x, y: p.y, w: p.w } });
    y += p.h;

    const cardEl = $(`.card[data-service-id="${id}"]`);
    if (cardEl) {
      cardEl.style.gridColumn = `${p.x} / span ${p.w}`;
      cardEl.style.gridRow = `${p.y} / span ${p.h}`;
    }
  }
  return updates;
}

function mobileTotalCols() {
  return Number.isFinite(state.lastGridColumns) ? state.lastGridColumns : MIN_CARD_W;
}

function reorderCardMobile(serviceId, action, positions, onLayoutChange) {
  const orderedIds = Array.from(positions.entries())
    .sort((a, b) => a[1].y - b[1].y)
    .map(([id]) => id);

  const idx = orderedIds.indexOf(serviceId);
  let newIdx = idx;
  if (action === "top") newIdx = 0;
  else if (action === "up") newIdx = Math.max(0, idx - 1);
  else if (action === "down") newIdx = Math.min(orderedIds.length - 1, idx + 1);
  else if (action === "bottom") newIdx = orderedIds.length - 1;
  if (newIdx === idx) return;

  orderedIds.splice(idx, 1);
  orderedIds.splice(newIdx, 0, serviceId);

  const updates = renumberMobileList(orderedIds, positions, mobileTotalCols());
  onLayoutChange && onLayoutChange(updates);
}

// `onLayoutChange`, shared by both drag handlers below, always receives an
// *array* of `{id, patch}` updates - a plain resize or move only ever
// produces one, but a move that swaps two cards produces two that must be
// saved together in a single request. Saving them as two separate requests
// would race: both would be built from the same pre-drag `sizes` snapshot,
// and whichever request's PUT lands second would silently wipe out the
// first request's change (the server replaces `sizes` wholesale, it doesn't
// merge), leaving the swap only half-persisted.
//
// `mobilePositions`, passed only for mobile edit mode's height-only resize,
// switches to that behavior: horizontal drag is ignored entirely (mobile
// cards are always full list-width), and on drop every other card's Y is
// renumbered to match the resized card's new bottom edge - a freeform
// desktop grid just leaves a taller card overlapping whatever's below until
// that's separately dragged out of the way, but mobile's single-column
// "list" has no such freeform slack for that to be sorted out later.
function attachResizeHandle(card, serviceId, pos, onLayoutChange, mobilePositions = null) {
  const heightOnly = !!mobilePositions;
  const handle = el("div", { class: "resize-handle", title: heightOnly ? "Drag to change height" : "Drag to resize" });
  card.appendChild(handle);

  let start = null;

  function onPointerMove(e) {
    const dy = e.clientY - start.py;
    if (!heightOnly) {
      const dx = e.clientX - start.px;
      pos.w = Math.max(MIN_CARD_W, start.w + Math.round(dx / GRID_UNIT));
    }
    pos.h = Math.max(MIN_CARD_H, start.h + Math.round(dy / GRID_UNIT));
    card.style.gridColumn = `${pos.x} / span ${pos.w}`;
    card.style.gridRow = `${pos.y} / span ${pos.h}`;
  }

  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    if (!onLayoutChange || (pos.h === start.h && pos.w === start.w)) return;

    if (heightOnly) {
      const orderedIds = Array.from(mobilePositions.entries())
        .sort((a, b) => a[1].y - b[1].y)
        .map(([id]) => id);
      // renumberMobileList only patches {x,y,w} for whatever it had to move
      // to avoid an overlap - the resized card's own new height has to be
      // included separately, since a card is never "moved" by its own
      // resize, only everything after it.
      const heightPatch = { id: serviceId, patch: { h: pos.h } };
      onLayoutChange([heightPatch, ...renumberMobileList(orderedIds, mobilePositions, mobileTotalCols())]);
    } else {
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

// Drag-to-reposition, from anywhere on the card except the resize handle
// and its buttons - a small hitbox is fiddly to grab, and the whole card is
// otherwise inert while editing anyway. Cards snap to the same grid the
// resize handle uses, and can be dropped anywhere - whatever ends up in the
// way gets pushed out of the way (resolveCollisions above), it never just
// bounces back.
function attachMoveHandle(card, serviceId, pos, positions, onLayoutChange) {
  let start = null;

  function onPointerMove(e) {
    const dx = e.clientX - start.px;
    const dy = e.clientY - start.py;
    pos.x = Math.max(1, start.x + Math.round(dx / GRID_UNIT));
    pos.y = Math.max(1, start.y + Math.round(dy / GRID_UNIT));
    card.style.gridColumn = `${pos.x} / span ${pos.w}`;
    card.style.gridRow = `${pos.y} / span ${pos.h}`;
  }

  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    card.classList.remove("dragging");

    if (pos.x === start.x && pos.y === start.y) return;

    const changed = resolveCollisions(serviceId, positions);
    const updates = [];
    for (const id of changed) {
      const p = positions.get(id);
      const el = id === serviceId ? card : $(`.card[data-service-id="${id}"]`);
      if (el) {
        el.style.gridColumn = `${p.x} / span ${p.w}`;
        el.style.gridRow = `${p.y} / span ${p.h}`;
      }
      updates.push({ id, patch: { x: p.x, y: p.y } });
    }
    onLayoutChange && onLayoutChange(updates);
  }

  card.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".resize-handle, button")) return;
    e.preventDefault();
    start = { px: e.clientX, py: e.clientY, x: pos.x, y: pos.y };
    card.classList.add("dragging");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });
}

function parseTs(iso) {
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime();
}

async function loadUptimeStrip(serviceId) {
  const strip = $(`#strip-${serviceId}`);
  if (!strip) return;
  strip.innerHTML = "";
  strip.style.display = "flex";

  const range = UPTIME_RANGES.find((r) => r.value === state.uptimeRange) || UPTIME_RANGES.find((r) => r.value === DEFAULT_UPTIME_RANGE);

  if (range.value === "last") {
    const svcStatus = state.statuses.find((s) => s.service.id === serviceId);
    if (!svcStatus || !svcStatus.last_checked) {
      strip.appendChild(el("div", { class: "bar", title: "No data yet" }));
      return;
    }
    strip.appendChild(
      el("div", { class: `bar ${svcStatus.overall_status}`, title: `Last poll: ${fmtTime(svcStatus.last_checked)}` })
    );
    return;
  }

  let rows;
  try {
    rows = await api(`/api/history?service_id=${serviceId}&hours=${uptimeRangeHours()}&limit=2000`);
  } catch (_) {
    return;
  }
  // loadUptimeStrip runs once per card per render pass, all in parallel -
  // the strip element (and the range picked) can be stale by the time this
  // particular fetch resolves if the user changed the dropdown mid-flight.
  if (state.uptimeRange !== range.value || !document.body.contains(strip)) return;

  const order = { ok: 0, warn: 1, fail: 2 };
  const byTs = new Map();
  for (const r of rows) {
    const worst = byTs.get(r.timestamp);
    if (!worst || order[r.status] > order[worst]) byTs.set(r.timestamp, r.status);
  }

  const now = Date.now();
  const rangeMs = range.minutes * 60000;
  const rangeStart = now - rangeMs;
  const bucketMs = rangeMs / UPTIME_BAR_COUNT;
  const buckets = new Array(UPTIME_BAR_COUNT).fill(null);

  for (const [ts, status] of byTs) {
    const t = parseTs(ts);
    if (t < rangeStart || t > now) continue;
    const idx = Math.min(UPTIME_BAR_COUNT - 1, Math.floor((t - rangeStart) / bucketMs));
    if (buckets[idx] === null || order[status] > order[buckets[idx]]) buckets[idx] = status;
  }

  for (let i = 0; i < UPTIME_BAR_COUNT; i++) {
    const bucketStart = new Date(rangeStart + i * bucketMs);
    const status = buckets[i];
    strip.appendChild(
      el("div", {
        class: status ? `bar ${status}` : "bar",
        title: status ? `${bucketStart.toLocaleString()} - ${statusLabel(status)}` : `${bucketStart.toLocaleString()} - no data`,
      })
    );
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

  // Only a name that's actually being clipped gets the fade treatment (see
  // .label-fade in style.css) - has to happen after the cards are in the
  // document, since an element's scrollWidth/clientWidth aren't meaningful
  // until it has a real layout box.
  for (const label of grid.querySelectorAll(".check-row .name .label")) {
    label.classList.toggle("label-fade", label.scrollWidth > label.clientWidth);
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
  const body = $("#history-body");
  body.innerHTML = "";
  if (!serviceId) return;

  let rows;
  try {
    rows = await api(`/api/history?service_id=${serviceId}&hours=${uptimeRangeHours()}&limit=500`);
  } catch (e) {
    toast("Failed to load history: " + e.message, true);
    return;
  }
  for (const r of rows) {
    body.appendChild(
      el("tr", {}, [
        el("td", { "data-label": "Time", text: fmtTime(r.timestamp) }),
        el("td", { "data-label": "Check", text: r.check_name }),
        el("td", { "data-label": "Status" }, el("span", { class: `badge ${r.status}`, text: r.status })),
        el("td", { "data-label": "Response", text: r.response_time_ms ? `${Math.round(r.response_time_ms)} ms` : "-" }),
        el("td", { "data-label": "Message", text: r.message }),
      ])
    );
  }
  if (rows.length === 0) {
    body.appendChild(el("tr", {}, el("td", { colspan: "5", class: "empty-state", text: "No data in this window" })));
  }
}
