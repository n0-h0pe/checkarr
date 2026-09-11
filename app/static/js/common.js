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
// Compact cards (icon, title, and status badge on one line, then just the
// uptime strip on a second - no address/last-checked line, no check list)
// need far less room than a full card, so they get their own, much smaller
// floor and starting size.
const MIN_CARD_W_COMPACT = 8;
const MIN_CARD_H_COMPACT = 4;
const DEFAULT_CARD_W_COMPACT = 10;
const DEFAULT_CARD_H_COMPACT = 5;

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

// The /api/history `minutes` query param the current uptime range maps to -
// shared by the dashboard's uptime strip and the History tab, which both
// read off the one top-bar dropdown now (see initUptimeRangeSelect below).
// Carries the picker's own minutes straight through - no more rounding up
// to whole hours, which used to collapse every sub-hour option (last poll,
// 1/3/5/10/15/30 min, 1 hour) into one identical "last hour" request.
// "Just the last poll" (0 minutes) never reaches this - the uptime strip
// special-cases it before ever calling this (see loadUptimeStrip above),
// and it's the History tab's own minimum service to floor it if needed.
function uptimeRangeMinutes() {
  const range = UPTIME_RANGES.find((r) => r.value === state.uptimeRange) || UPTIME_RANGES.find((r) => r.value === DEFAULT_UPTIME_RANGE);
  return Math.max(1, range.minutes);
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

// ---------- secret fields (env var toggle) ----------
//
// Every password/API-key field can either hold the secret directly
// (encrypted at rest) or a plain environment variable NAME to read it from
// at runtime instead - the "Use environment variable" checkbox next to the
// field. Switching to env-var mode clears whatever's stored server-side
// (see security.apply_secret_field); switching back to literal mode clears
// the env var name and needs a fresh value, since there's nothing stored
// left to fall back to once cleaned up. Shared by the service modal's API
// key/Jellyfin admin password fields (app.js) and the notification channel
// modal's dynamic secret field (also app.js).

function syncSecretFieldAppearance(input, checkbox) {
  const useEnv = checkbox.checked;
  input.type = useEnv ? "text" : "password";
  input.autocomplete = useEnv ? "off" : "new-password";
  input.placeholder = useEnv
    ? "Environment variable name, e.g. RADARR_API_KEY"
    : input.dataset.literalPlaceholder || "";
}

// Wires the checkbox once (idempotent to call again - addEventListener
// on the same function reference is a no-op the second time). Switching
// modes always starts the field blank rather than carrying over whatever
// was typed for the other mode.
function initSecretField(input, checkbox) {
  input.dataset.literalPlaceholder = input.dataset.literalPlaceholder ?? input.placeholder;
  checkbox.addEventListener("change", () => {
    input.value = "";
    syncSecretFieldAppearance(input, checkbox);
  });
  syncSecretFieldAppearance(input, checkbox);
}

// existingEnvVar: the currently-saved env var name, or falsy if this
// secret is (or would be) stored literally instead. Env var NAMES aren't
// secret, so - unlike a literal value, never echoed back - the current one
// is shown directly in the field, editable in place.
function setSecretFieldState(input, checkbox, existingEnvVar) {
  checkbox.checked = !!existingEnvVar;
  input.value = existingEnvVar || "";
  syncSecretFieldAppearance(input, checkbox);
}

function readSecretField(input, checkbox) {
  if (checkbox.checked) {
    return { useEnv: true, envVar: input.value.trim(), literal: null };
  }
  return { useEnv: false, envVar: null, literal: input.value || null };
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
function computeCardLayout(statuses, compact = false) {
  const minW = compact ? MIN_CARD_W_COMPACT : MIN_CARD_W;
  const minH = compact ? MIN_CARD_H_COMPACT : MIN_CARD_H;
  const defaultW = compact ? DEFAULT_CARD_W_COMPACT : DEFAULT_CARD_W;
  const defaultH = compact ? DEFAULT_CARD_H_COMPACT : DEFAULT_CARD_H;
  const grid = $("#dashboard-grid");
  const width = (grid && grid.clientWidth) || Math.max(0, window.innerWidth - 48);
  const totalCols = Math.max(minW, Math.floor(width / GRID_UNIT));
  state.lastGridColumns = totalCols;

  const layout = state.activeLayout;
  const sizes = (layout && layout.sizes) || {};
  const savedCols = layout && Number.isFinite(layout.columns) ? layout.columns : null;
  const reflow = savedCols !== null && totalCols < savedCols;

  const entries = statuses.map((s) => {
    const id = s.service.id;
    const saved = sizes[String(id)];
    // Clamped to totalCols (never below minW, since totalCols itself never
    // is) so a card widened on a big desktop window can't render wider than
    // the actual screen on a narrow one - display-only, like the reflow
    // above, so the saved width still comes back on a wide-enough screen
    // untouched.
    const savedW = saved && Number.isFinite(saved.w) ? Math.max(minW, saved.w) : defaultW;
    // On mobile every card is a full-width single-column list, always -
    // clamping a saved/default width down to totalCols (as below) still
    // leaves a gap for anything narrower than totalCols (a brand new
    // service with no saved size, or a card saved narrower on desktop), so
    // mobile forces w to totalCols outright rather than just capping it.
    const w = isMobileViewport() ? totalCols : Math.min(savedW, totalCols);
    const h = saved && Number.isFinite(saved.h) ? Math.max(minH, saved.h) : defaultH;
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

  const headerRight = el("div", { class: "card-header-right" });
  // Compact cards drop Run now/History entirely (not just visually smaller)
  // so the status badge sits right at the card's top-right corner with
  // nothing else competing for that row's space.
  if (opts.interactive && !opts.compact) {
    headerRight.appendChild(
      el("div", { class: "card-header-actions" }, [
        el("button", { class: "small", onclick: () => opts.onRunNow && opts.onRunNow(svc.id) }, "Run now"),
        el("button", { class: "small", onclick: () => opts.onHistory && opts.onHistory(svc.id) }, "History"),
      ])
    );
  }
  if (opts.editable && opts.onRemoveCard) {
    headerRight.appendChild(
      el("button", {
        class: "small danger card-remove-btn",
        title: "Remove from this layout",
        onclick: (e) => { e.stopPropagation(); opts.onRemoveCard(svc.id); },
        text: "✕",
      })
    );
  }
  headerRight.appendChild(
    el("span", { class: `badge ${s.overall_status}` }, [
      el("span", { class: `dot ${s.overall_status}` }),
      statusLabel(s.overall_status),
    ])
  );
  card.appendChild(
    el("div", { class: "card-header" }, [
      el("div", { class: "title" }, [typeIcon(svc.type), el("span", { text: svc.name })]),
      headerRight,
    ])
  );
  // Everything between the header and the check list lives in its own
  // wrapper - it's what the mobile reorder overlay below covers/blurs;
  // Run now/History/remove live in the header instead, so they stay usable
  // even while that overlay is up.
  const body = el("div", { class: "card-body" });
  // Compact cards skip the type/address/last-checked line entirely - just
  // icon, title, and status badge on the header row, then the uptime strip
  // below it, nothing else (see also the check list, skipped further down).
  if (!opts.compact) {
    const addressLabel = [svc.local_url, svc.remote_url].filter(Boolean).join(" / ");
    body.appendChild(
      el("div", { class: "card-sub" }, [
        `${svc.type} · ${addressLabel} · last checked ${relTime(s.last_checked)}`,
        s.active_notification_count > 0 ? el("span", { style: "color:var(--warn)" }, ` · ${s.active_notification_count} notification(s)`) : null,
      ])
    );
  }

  const strip = el("div", { class: "uptime-strip", id: `strip-${svc.id}` });
  body.appendChild(strip);

  if (!opts.compact) {
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
  }
  card.appendChild(body);

  if (opts.editable) {
    card.classList.add("card-editable");
    if (isMobileViewport()) {
      attachMobileReorderControls(body, svc.id, positions, opts.onLayoutChange);
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange, positions, opts.compact);
    } else {
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange, null, opts.compact);
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

// Drag handle for the checks-grid (app.js) and the History columns list
// below - an inline SVG rather than a Unicode/Braille character (glyphs
// like "⠿" render inconsistently across fonts and can look lopsided rather
// than a clean grip).
const DRAG_HANDLE_ICON =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><circle cx="9" cy="6" r="1.7"/><circle cx="15" cy="6" r="1.7"/><circle cx="9" cy="12" r="1.7"/><circle cx="15" cy="12" r="1.7"/><circle cx="9" cy="18" r="1.7"/><circle cx="15" cy="18" r="1.7"/></svg>';

// Generic single-element drag-to-reorder, for a plain vertical list of
// sibling elements (unlike attachCheckDragHandle in app.js, which moves a
// *group* of 6 cells per row - here each row already is one element, so
// there's nothing to group). `getSiblings()` is called fresh on every move
// so it always reflects the list's current DOM order.
function attachSimpleDragHandle(handle, row, getSiblings, onDrop) {
  function onPointerMove(e) {
    const siblings = getSiblings().filter((s) => s !== row);
    let target = null;
    let insertAfter = false;
    for (const s of siblings) {
      const rect = s.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      target = s;
      insertAfter = e.clientY >= mid;
      if (!insertAfter) break;
    }
    if (!target) return;
    target.parentNode.insertBefore(row, insertAfter ? target.nextSibling : target);
  }
  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    row.classList.remove("dragging");
    onDrop && onDrop();
  }
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    row.classList.add("dragging");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });
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
function attachResizeHandle(card, serviceId, pos, onLayoutChange, mobilePositions = null, compact = false) {
  const heightOnly = !!mobilePositions;
  const minW = compact ? MIN_CARD_W_COMPACT : MIN_CARD_W;
  const minH = compact ? MIN_CARD_H_COMPACT : MIN_CARD_H;
  const handle = el("div", { class: "resize-handle", title: heightOnly ? "Drag to change height" : "Drag to resize" });
  card.appendChild(handle);

  let start = null;

  function onPointerMove(e) {
    const dy = e.clientY - start.py;
    if (!heightOnly) {
      const dx = e.clientX - start.px;
      pos.w = Math.max(minW, start.w + Math.round(dx / GRID_UNIT));
    }
    pos.h = Math.max(minH, start.h + Math.round(dy / GRID_UNIT));
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
    rows = await api(`/api/history?service_ids=${serviceId}&minutes=${uptimeRangeMinutes()}&limit=2000`);
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

// The is_default "All Services" layout always shows every service,
// regardless of what's stored in card_service_ids (never trimmed - see
// DashboardLayout's docstring); any other layout shows only the services
// explicitly in its card_service_ids. Falls back to "show everything" when
// there's no layout data at all yet (a transient fetch failure shouldn't
// blank the dashboard).
function layoutVisibleStatuses(statuses, layout) {
  if (!layout || layout.is_default) return statuses;
  const visible = new Set(layout.card_service_ids || []);
  return statuses.filter((s) => visible.has(s.service.id));
}

async function loadDashboard(cardOpts = {}) {
  const statuses = await ensureStatuses(true);
  const layout = await ensureActiveLayout();
  const grid = $("#dashboard-grid");
  if (!grid) return;
  grid.innerHTML = "";

  // Compact is a property of the layout itself (DashboardLayout.is_compact,
  // toggled from the "Compact view" button in the top bar), not a
  // per-viewer display option - so admin and public both render a compact
  // layout the same way, wherever it's shown.
  const opts = { ...cardOpts, compact: !!(layout && layout.is_compact) };

  const visible = layoutVisibleStatuses(statuses, layout);

  if (visible.length === 0) {
    grid.appendChild(
      el("div", {
        class: "empty-state",
        text: statuses.length === 0 ? "No services configured yet." : "No cards on this layout yet.",
      })
    );
  }

  const counts = { ok: 0, warn: 0, fail: 0, unknown: 0, disabled: 0 };
  visible.forEach((s) => { counts[s.overall_status] = (counts[s.overall_status] || 0) + 1; });
  const pill = $("#summary-pill");
  if (pill) {
    pill.innerHTML = "";
    ["ok", "warn", "fail"].forEach((k) => {
      pill.appendChild(el("span", {}, [el("span", { class: `dot ${k}` }), `${counts[k] || 0} ${k}`]));
    });
  }
  const refresh = $("#last-refresh");
  if (refresh) refresh.textContent = "Updated " + new Date().toLocaleTimeString();

  const positions = computeCardLayout(visible, opts.compact);
  for (const s of visible) {
    grid.appendChild(renderServiceCard(s, opts, positions.get(s.service.id), positions));
  }
  for (const s of visible) {
    loadUptimeStrip(s.service.id);
  }

  // Only a name that's actually being clipped gets the fade treatment (see
  // .label-fade in style.css) - has to happen after the cards are in the
  // document, since an element's scrollWidth/clientWidth aren't meaningful
  // until it has a real layout box. Same treatment for a card's own title
  // (.title-fade) - a compact card in particular has the status badge
  // sitting right up against it with no buttons in between to give a long
  // name room, so it needs to fade out rather than run into/under the badge.
  for (const label of grid.querySelectorAll(".check-row .name .label")) {
    label.classList.toggle("label-fade", label.scrollWidth > label.clientWidth);
  }
  for (const title of grid.querySelectorAll(".card-header .title span:last-child")) {
    title.classList.toggle("title-fade", title.scrollWidth > title.clientWidth);
  }
}

// ---------- notifications (shared) ----------

// "Notifications" here means "checks currently in warn/fail" (see
// queries.get_active_issues) - not models.Notification, which is a
// separate, narrower feed the arr_health check type populates from each
// arr's own health API for its own alert dispatch. A whole service being
// unreachable shows up here (its checks fail) even though it can never
// produce an arr_health notification of its own.
async function loadNotifications() {
  let items;
  try {
    items = await api("/api/notifications");
  } catch (e) {
    toast("Failed to load notifications: " + e.message, true);
    return;
  }
  const list = $("#notifications-list");
  if (!list) return;
  list.innerHTML = "";
  if (items.length === 0) {
    list.appendChild(el("div", { class: "empty-state", text: "Nothing in warn or fail right now \u{1F389}" }));
    return;
  }
  for (const n of items) {
    const row = el("div", { class: "notif-row" }, [
      el("div", { class: "top" }, [
        typeIcon(n.service_type),
        el("span", { class: `badge ${n.status}`, text: n.status }),
        el("span", { class: "service-name", text: n.service_name }),
        el("span", { class: "text-dim", text: n.check_name }),
      ]),
      el("div", { class: "msg", text: n.message }),
      el("div", { class: "meta", text: `last checked ${relTime(n.timestamp)}` }),
    ]);
    list.appendChild(row);
  }
}

// ---------- history (shared) ----------

// Every column the History table can show - "type" isn't in the default
// set (kept lean out of the box) but is one toggle away. `value` is the
// plain-text form used both for the table cell fallback and CSV export;
// `renderCell`, where present, overrides just the table's DOM rendering
// (a colored badge for Status) without affecting the CSV value. `nowrap`
// exempts a column from the ellipsis-truncation every other column gets -
// only Time uses it, so it's never forced onto two lines (see
// renderHistoryHeader/historyRowElement and the .col-nowrap CSS rule).
const HISTORY_COLUMNS = {
  time: { label: "Time", value: (r) => fmtTime(r.timestamp), nowrap: true },
  service: { label: "Service", value: (r) => serviceNameById(r.service_id) },
  check: { label: "Check", value: (r) => r.check_name },
  type: { label: "Type", value: (r) => r.check_type },
  status: {
    label: "Status",
    value: (r) => r.status,
    renderCell: (r) => el("span", { class: `badge ${r.status}`, text: r.status }),
  },
  response: { label: "Response", value: (r) => (r.response_time_ms ? `${Math.round(r.response_time_ms)} ms` : "-") },
  message: { label: "Message", value: (r) => r.message },
};
const DEFAULT_HISTORY_COLUMNS = ["time", "service", "check", "status", "response", "message"];
const HISTORY_PAGE_SIZE = 100;

// CheckResultOut only ever carries a service_id, not a name - the History
// tab already has every service's name in hand from ensureStatuses (it's
// what the services filter modal itself is built from), so there's no need
// for the backend to repeat it on every single row.
function serviceNameById(serviceId) {
  const s = state.statuses.find((s) => s.service.id === serviceId);
  return s ? s.service.name : `Service #${serviceId}`;
}

function loadHistoryColumns() {
  const raw = getCookie("hc_history_columns");
  const keys = raw ? raw.split(",").filter((k) => HISTORY_COLUMNS[k]) : [];
  return keys.length ? keys : DEFAULT_HISTORY_COLUMNS.slice();
}
function saveHistoryColumns() {
  setCookie("hc_history_columns", state.historyColumns.join(","), 365);
}
state.historyColumns = loadHistoryColumns();

function loadHistoryColumnWidths() {
  const raw = getCookie("hc_history_column_widths");
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) {
    return {};
  }
}
function saveHistoryColumnWidths() {
  setCookie("hc_history_column_widths", JSON.stringify(state.historyColumnWidths), 365);
}
state.historyColumnWidths = loadHistoryColumnWidths();

// Which services' history currently shows - defaults to none every load
// (not persisted), so the table stays empty (and fast - nothing is
// fetched) until the user actually picks at least one.
state.historySelectedServiceIds = [];

function historyTable() {
  const body = $("#history-body");
  return body ? body.closest("table") : null;
}

// A <colgroup> gives each column an actual bounded width to truncate
// against (table-layout:fixed alone isn't enough without one) and is what
// column resizing below actually adjusts.
function renderHistoryColgroup() {
  const table = historyTable();
  if (!table) return;
  let colgroup = table.querySelector("colgroup");
  if (!colgroup) {
    colgroup = el("colgroup");
    table.insertBefore(colgroup, table.firstChild);
  }
  colgroup.innerHTML = "";
  for (const key of state.historyColumns) {
    const width = state.historyColumnWidths[key];
    colgroup.appendChild(el("col", width ? { style: `width:${width}px` } : {}));
  }
}

function renderHistoryHeader() {
  const table = historyTable();
  const thead = table && table.querySelector("thead");
  if (!thead) return;
  renderHistoryColgroup();
  thead.innerHTML = "";
  thead.appendChild(
    el(
      "tr",
      {},
      state.historyColumns.map((key, i) => {
        const col = HISTORY_COLUMNS[key];
        const th = el("th", { class: col.nowrap ? "col-nowrap" : "" }, col.label);
        // No handle after the last column - nothing to its right to resize against.
        if (i < state.historyColumns.length - 1) {
          const handle = el("div", { class: "col-resize-handle" });
          attachColumnResizeHandle(handle, key);
          th.appendChild(handle);
        }
        return th;
      })
    )
  );
}

function attachColumnResizeHandle(handle, key) {
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const th = handle.parentElement;
    const startWidth = th.getBoundingClientRect().width;
    const startX = e.clientX;
    const onMove = (ev) => {
      state.historyColumnWidths[key] = Math.max(50, Math.round(startWidth + (ev.clientX - startX)));
      renderHistoryColgroup();
    };
    const onUp = () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      saveHistoryColumnWidths();
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
}

function historyRowElement(r) {
  return el(
    "tr",
    {},
    state.historyColumns.map((key) => {
      const col = HISTORY_COLUMNS[key];
      return el(
        "td",
        { "data-label": col.label, class: col.nowrap ? "col-nowrap" : "" },
        col.renderCell ? col.renderCell(r) : col.value(r)
      );
    })
  );
}

let historyObserver = null;

function ensureHistoryObserver() {
  if (historyObserver) return;
  historyObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) loadMoreHistoryRows();
    },
    { rootMargin: "300px" }
  );
}

function historyServiceIdsQuery() {
  return state.historySelectedServiceIds.map((id) => `service_ids=${id}`).join("&");
}

// Resets to page 1 - called on service-selection/range change and whenever
// the column set changes (simplest way to keep already-rendered rows in
// sync with a new column list, and cheap enough at this page size to just
// do).
async function loadHistoryTab() {
  await ensureStatuses();
  renderHistoryServicePills();
  renderHistoryHeader();
  state.historyBeforeId = null;
  state.historyExhausted = false;
  state.historyLoading = false;
  const body = $("#history-body");
  if (!body) return;
  body.innerHTML = "";
  if (state.historySelectedServiceIds.length === 0) {
    body.appendChild(
      el("tr", {}, el("td", { colspan: String(Math.max(1, state.historyColumns.length)), class: "empty-state", text: "Pick at least one service above" }))
    );
    return;
  }
  await loadMoreHistoryRows();
}

// Fetches and appends the next page, cursor-paginated on id (see
// queries.get_history's docstring for why id rather than an offset - a
// service's rows keep growing while the user scrolls, and an offset would
// shift under those new inserts, an id cursor can't). Wired to an
// IntersectionObserver on a sentinel row kept at the table's end, so
// scrolling near the bottom - of the page or of an inner scroll container,
// doesn't matter which - loads more automatically.
async function loadMoreHistoryRows() {
  if (state.historyLoading || state.historyExhausted) return;
  if (state.historySelectedServiceIds.length === 0) return;
  state.historyLoading = true;

  let rows;
  try {
    const cursor = state.historyBeforeId != null ? `&before_id=${state.historyBeforeId}` : "";
    rows = await api(
      `/api/history?${historyServiceIdsQuery()}&minutes=${uptimeRangeMinutes()}&limit=${HISTORY_PAGE_SIZE}${cursor}`
    );
  } catch (e) {
    toast("Failed to load history: " + e.message, true);
    state.historyLoading = false;
    return;
  }

  const body = $("#history-body");
  const oldSentinel = $("#history-sentinel");
  if (oldSentinel) {
    if (historyObserver) historyObserver.unobserve(oldSentinel);
    oldSentinel.remove();
  }

  for (const r of rows) body.appendChild(historyRowElement(r));
  if (rows.length > 0) state.historyBeforeId = rows[rows.length - 1].id;
  if (rows.length < HISTORY_PAGE_SIZE) state.historyExhausted = true;

  if (body.children.length === 0) {
    body.appendChild(
      el("tr", {}, el("td", { colspan: String(Math.max(1, state.historyColumns.length)), class: "empty-state", text: "No data in this window" }))
    );
  } else if (!state.historyExhausted) {
    ensureHistoryObserver();
    const sentinel = el(
      "tr",
      { id: "history-sentinel" },
      el("td", { colspan: String(Math.max(1, state.historyColumns.length)), style: "padding:0; border:none; height:1px;" })
    );
    body.appendChild(sentinel);
    historyObserver.observe(sentinel);
  }
  state.historyLoading = false;
}

// ---------- history: service filter ----------

// A row of toggle "pill" buttons, one per service, directly in the panel -
// not a checkbox list tucked behind a button/modal, so the current
// selection is always visible at a glance and a single click adds/removes
// a service. Rebuilt on every loadHistoryTab (cheap at this list size, and
// keeps it in sync if a service is added/removed elsewhere).
function renderHistoryServicePills() {
  const bar = $("#history-services-bar");
  if (!bar) return;
  bar.innerHTML = "";
  if (state.statuses.length === 0) {
    bar.appendChild(el("span", { class: "text-dim", text: "No services configured yet" }));
    return;
  }
  const selected = new Set(state.historySelectedServiceIds);
  for (const s of state.statuses) {
    const active = selected.has(s.service.id);
    bar.appendChild(
      el(
        "button",
        {
          type: "button",
          class: `service-pill${active ? " active" : ""}`,
          "aria-pressed": active ? "true" : "false",
          onclick: () => {
            const next = new Set(state.historySelectedServiceIds);
            if (next.has(s.service.id)) next.delete(s.service.id);
            else next.add(s.service.id);
            state.historySelectedServiceIds = [...next];
            loadHistoryTab();
          },
        },
        s.service.name
      )
    );
  }
}

function setHistorySelectedServices(ids) {
  state.historySelectedServiceIds = ids.slice();
}

// ---------- history: column customization ----------

function openColumnsModal() {
  const list = $("#columns-list");
  if (!list) return;
  list.innerHTML = "";
  const visible = state.historyColumns;
  const hidden = Object.keys(HISTORY_COLUMNS).filter((k) => !visible.includes(k));
  for (const key of [...visible, ...hidden]) {
    list.appendChild(renderColumnRow(key, visible.includes(key)));
  }
  $("#columns-modal").classList.remove("hidden");
}

function closeColumnsModal() {
  const modal = $("#columns-modal");
  if (modal) modal.classList.add("hidden");
}

function renderColumnRow(key, checked) {
  const row = el("div", { class: "column-row", "data-key": key });
  const handle = el("div", { class: "drag-handle" });
  handle.innerHTML = DRAG_HANDLE_ICON;
  const checkbox = el("input", { type: "checkbox" });
  checkbox.checked = checked;
  checkbox.addEventListener("change", () => {
    const anyChecked = $all("#columns-list input[type=checkbox]").some((i) => i.checked);
    if (!checkbox.checked && !anyChecked) {
      toast("At least one column must stay visible", true);
      checkbox.checked = true;
      return;
    }
    onColumnsListChanged();
  });
  row.append(handle, checkbox, el("span", { text: HISTORY_COLUMNS[key].label }));
  attachSimpleDragHandle(handle, row, () => $all(".column-row", $("#columns-list")), onColumnsListChanged);
  return row;
}

function onColumnsListChanged() {
  const rows = $all(".column-row", $("#columns-list"));
  state.historyColumns = rows.filter((r) => r.querySelector("input[type=checkbox]").checked).map((r) => r.dataset.key);
  saveHistoryColumns();
  loadHistoryTab();
}

// ---------- history: CSV export ----------

function csvEscape(value) {
  const s = String(value ?? "");
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function exportHistoryCsv() {
  if (state.historySelectedServiceIds.length === 0) return;
  const btn = $("#history-export-btn");
  const originalLabel = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Exporting…";
  }

  // Not just whatever's scrolled into view so far - the whole filtered set,
  // paginated the same way the table itself is, up to a generous safety cap
  // rather than an unbounded loop.
  const EXPORT_PAGE_SIZE = 1000;
  const MAX_PAGES = 50;
  const allRows = [];
  let beforeId = null;
  try {
    for (let page = 0; page < MAX_PAGES; page++) {
      const cursor = beforeId != null ? `&before_id=${beforeId}` : "";
      const rows = await api(
        `/api/history?${historyServiceIdsQuery()}&minutes=${uptimeRangeMinutes()}&limit=${EXPORT_PAGE_SIZE}${cursor}`
      );
      allRows.push(...rows);
      if (rows.length < EXPORT_PAGE_SIZE) break;
      beforeId = rows[rows.length - 1].id;
    }
  } catch (e) {
    toast("Export failed: " + e.message, true);
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
    return;
  }

  const cols = state.historyColumns.map((k) => HISTORY_COLUMNS[k]);
  const lines = [cols.map((c) => csvEscape(c.label)).join(",")];
  for (const r of allRows) lines.push(cols.map((c) => csvEscape(c.value(r))).join(","));

  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const label =
    state.historySelectedServiceIds.length === 1
      ? serviceNameById(state.historySelectedServiceIds[0]).replace(/[^\w-]+/g, "_")
      : `${state.historySelectedServiceIds.length}_services`;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const link = el("a", { href: url, download: `checkarr-history-${label}-${stamp}.csv` });
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  if (btn) {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
  toast(`Exported ${allRows.length} row(s)`);
}
