// Shared between the full admin app (app.js) and the restricted public
// dashboard (public.js). Keeps their read-only rendering identical without
// the public surface ever importing anything that can mutate state.

const state = { meta: null, services: [], statuses: [], channels: [], groups: [], schedules: [], tab: "dashboard", activeLayout: null, lastGridColumns: null, lastCardPositions: null };

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
  { value: "20160", minutes: 20160, label: "Last 2 weeks" },
  { value: "43200", minutes: 43200, label: "Last month" },
  { value: "129600", minutes: 129600, label: "Last 3 months" },
  { value: "525600", minutes: 525600, label: "Last year" },
];
const DEFAULT_UPTIME_RANGE = "2880";

// Per-card uptime bar count (Dashboard > Edit layout > the "Bars" field
// above each card's strip, admin only) - stored as DashboardLayout.sizes[id].bars
// alongside that card's w/h/x/y, so different cards on the same layout can
// genuinely have different counts (unlike the single global setting this
// replaced - a fixed count that looked fine on a wide card just broke on a
// narrow one, and there was no way to have both on one dashboard).
//
// A card's own current width caps how high this can be set at all: past a
// certain point, `.uptime-strip`'s `gap: 2px` between an ever-growing number
// of `flex: 1` bars eats more of the available width than the bars
// themselves have left, and they start rendering at 0/negative width -
// invisible or visually corrupted, not just "thin". maxUptimeBarsForGridWidth
// below is a straight-line ramp between two anchors picked by eye against
// what actually still looks right at each size: 16 grid units (a card's
// practical minimum width day to day) caps at UPTIME_BAR_MIN_LIMIT, 64
// units caps at the full UPTIME_BAR_MAX_LIMIT, and anything narrower than
// 16 still floors at UPTIME_BAR_MIN_LIMIT rather than extrapolating lower -
// deliberately in grid units (the same number dragged/persisted as w, and
// shown by the resize-debug badge in attachResizeHandle below) rather than
// a measured pixel width, so what you see while dragging, what gets saved,
// and what this ramp is keyed to are all the same number.
const DEFAULT_CARD_UPTIME_BARS = 20;
const UPTIME_BAR_MIN_LIMIT = 50;
const UPTIME_BAR_MAX_LIMIT = 200;
const UPTIME_BAR_MIN_WIDTH_UNITS = 16;
const UPTIME_BAR_MAX_WIDTH_UNITS = 64;

function maxUptimeBarsForGridWidth(w) {
  if (w <= UPTIME_BAR_MIN_WIDTH_UNITS) return UPTIME_BAR_MIN_LIMIT;
  if (w >= UPTIME_BAR_MAX_WIDTH_UNITS) return UPTIME_BAR_MAX_LIMIT;
  const t = (w - UPTIME_BAR_MIN_WIDTH_UNITS) / (UPTIME_BAR_MAX_WIDTH_UNITS - UPTIME_BAR_MIN_WIDTH_UNITS);
  return Math.round(UPTIME_BAR_MIN_LIMIT + t * (UPTIME_BAR_MAX_LIMIT - UPTIME_BAR_MIN_LIMIT));
}

// Falls back to this pool's own default card width when a card hasn't been
// individually placed/resized yet (no positions entry, or none computed at
// all outside a dashboard render, e.g. before the very first one) - an
// approximation (computeCardLayout's own auto-pack might land it somewhere
// slightly different), but only ever feeds a bar-count ceiling, not
// anything persisted, so exactness doesn't matter here.
function resolveCardGridWidth(serviceId, compact) {
  const pos = state.lastCardPositions && state.lastCardPositions.get(serviceId);
  if (pos && Number.isFinite(pos.w)) return pos.w;
  return compact ? DEFAULT_CARD_W_COMPACT : DEFAULT_CARD_W;
}

// Single source of truth for "how many bars does this card actually draw
// right now" - shared by loadUptimeStrip (which draws them) and the Bars
// control (which needs the same number to initialize its input) so they
// can never disagree with each other.
function effectiveUptimeBarCount(serviceId, compact) {
  const layout = state.activeLayout;
  const saved = layout && layout.sizes && layout.sizes[String(serviceId)];
  const stored = saved && Number.isFinite(saved.bars) ? saved.bars : DEFAULT_CARD_UPTIME_BARS;
  const w = resolveCardGridWidth(serviceId, compact);
  return Math.max(1, Math.min(stored, maxUptimeBarsForGridWidth(w)));
}

// The "Bars" control rendered above a card's uptime strip in edit mode -
// see renderServiceCard. min/max on the <input> itself do the actual
// clamping on manual entry (a browser number input already refuses to leave
// a value past those via its up/down arrows, and reports validity on
// out-of-range typed values); the change handler below still re-clamps
// defensively, since a typed value bypasses the arrows entirely.
function renderUptimeBarControl(svc, pos, compact, onLayoutChange) {
  const w = pos ? pos.w : resolveCardGridWidth(svc.id, compact);
  const maxBars = maxUptimeBarsForGridWidth(w);
  const value = effectiveUptimeBarCount(svc.id, compact);

  const input = el("input", {
    type: "number",
    class: "uptime-bar-count-input",
    min: "1",
    max: String(maxBars),
    value: String(value),
    title: `Uptime bars shown on this card (1-${maxBars} at its current width)`,
  });
  input.addEventListener("change", async () => {
    const max = Number(input.max) || UPTIME_BAR_MAX_LIMIT;
    let next = Math.round(Number(input.value));
    if (!Number.isFinite(next) || next < 1) next = 1;
    if (next > max) next = max;
    input.value = String(next);
    // Must actually finish before redrawing - persistCardLayout updates
    // state.activeLayout.sizes[id].bars asynchronously, and
    // effectiveUptimeBarCount reads straight off that same state, so
    // calling loadUptimeStrip before this resolves would just redraw with
    // whatever was there before the change.
    if (onLayoutChange) await onLayoutChange([{ id: svc.id, patch: { bars: next } }]);
    loadUptimeStrip(svc.id);
  });

  return el("div", { class: "uptime-bar-control" }, [
    el("span", { class: "text-dim", text: "Bars" }),
    input,
  ]);
}

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
// "Just the last poll" (0 minutes) is passed through as 0, not floored to
// 1 - the uptime strip special-cases it before ever calling this (see
// loadUptimeStrip above) so it never actually sends 0 itself, but the
// History tab calls this directly and relies on 0 reaching /api/history
// unchanged, where it means "latest result per check", not "last minute"
// (see queries.get_history's docstring - a 1-minute window would come back
// empty for any service polled less often than once a minute).
function uptimeRangeMinutes() {
  const range = UPTIME_RANGES.find((r) => r.value === state.uptimeRange) || UPTIME_RANGES.find((r) => r.value === DEFAULT_UPTIME_RANGE);
  return range.minutes;
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

// Compact "YY-MM-DD HH:MM" stand-in for fmtTime, for the History tab's
// mobile row (see historyRowElement) - narrow enough to share a line with
// everything else there, unlike a full locale datetime string.
function fmtTimeCompact(iso) {
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  const p = (n) => String(n).padStart(2, "0");
  return `${String(d.getFullYear()).slice(-2)}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
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

// Fallback img/emoji-as-image loader shared by every icon path below -
// if it 404s or otherwise fails to load (a deleted upload, a renamed
// library key), drop back to the generic puzzle piece rather than leaving
// a broken-image icon in its place.
function _iconImg(src, alt) {
  return el("img", {
    class: "type-icon",
    src,
    alt,
    loading: "lazy",
    onerror: function () { this.replaceWith(el("span", { class: "type-icon-fallback", text: "\u{1F9E9}" })); },
  });
}

// `svc` is anything with `.type` plus optionally `.icon_type`/`.icon_value`
// (a full ServiceOut works; a plain string type still works too, for any
// caller that only ever has the bare type and no per-service override to
// honor). See models.Service.icon_type's docstring for what each
// icon_type means and why an "upload" is always rendered via <img src>
// here, never inline.
function typeIcon(svc) {
  if (typeof svc === "string") svc = { type: svc };
  svc = svc || {};
  if (svc.icon_type === "emoji" && svc.icon_value) {
    return el("span", { class: "type-icon-emoji", text: svc.icon_value });
  }
  if (svc.icon_type === "upload" && svc.icon_value) {
    return _iconImg(`/custom-icons/${svc.icon_value}`, svc.type || "");
  }
  const libraryType = svc.icon_type === "library" && svc.icon_value ? svc.icon_value : svc.type;
  const url = iconUrlFor(libraryType);
  if (!url) return el("span", { class: "type-icon-fallback", text: "\u{1F9E9}" }); // puzzle piece
  return _iconImg(url, svc.type || libraryType);
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

// Re-fetches whenever the cached layout's own device pool (is_mobile)
// doesn't match the actual current viewport, not just on first load -
// resize across the phone-width breakpoint (see isMobileViewport below)
// needs to land on a genuinely different saved layout now, not just a
// different rendering of the same one. The `mobile` hint travels to the
// server either way (harmless on the fast path, where it's not even
// looked at again) so a fresh page load already asks for the right pool
// the first time, no "loads desktop, flashes to mobile" round trip.
async function ensureActiveLayout(force = false) {
  const mobileNow = await _currentViewportMobile();
  const upToDate = mobileNow !== null && state.activeLayout && !!state.activeLayout.is_mobile === mobileNow;
  if (force || !upToDate) {
    try {
      const qs = mobileNow === null ? "" : `?mobile=${mobileNow}`;
      state.activeLayout = await api(`/api/dashboard-layouts/active${qs}`);
    } catch (_) { /* leave whatever we had, or null - computeCardLayout() falls back to defaults */ }
  }
  return state.activeLayout;
}

// window.innerWidth briefly reads 0 - never a real device width - on a tab
// that technically exists but hasn't actually been laid out/painted yet
// (this call landing before the very first layout pass). Trusting it then
// would risk landing on the wrong device pool with nothing to correct it
// until the next resize event or 30-second poll (see the resize listeners
// in app.js/public.js, which only re-check on an actual width *change*).
// One rendered frame is enough for a real width to show up; if it somehow
// still hasn't, `null` skips the `mobile` hint entirely rather than guess,
// same as never sending it at all (the pre-device-pools behavior).
async function _currentViewportMobile() {
  if (window.innerWidth === 0) {
    await new Promise((resolve) => requestAnimationFrame(resolve));
    if (window.innerWidth === 0) return null;
  }
  return isMobileViewport();
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
//
// None of the above applies to a mobile-pool layout (`mobile` true, see
// DashboardLayout.is_mobile) - it's handled by its own much simpler branch
// below instead, since it's always a single full-width column regardless of
// actual window width, ordered by each card's saved `y` alone. Only `y`/`h`
// are ever read back from a mobile layout's saved sizes - `x`/`w` are always
// forced to 1/full-width, never taken from saved data, which is what used
// to let a card end up positioned past the edge of the grid the app was
// actually rendering (a desktop-shaped x position surviving into a much
// narrower render) and create implicit off-screen columns the whole page
// could scroll sideways to reach.
function computeCardLayout(statuses, compact = false, mobile = false) {
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

  if (mobile) {
    const entries = statuses.map((s, i) => {
      const id = s.service.id;
      const saved = sizes[String(id)];
      const h = saved && Number.isFinite(saved.h) ? Math.max(minH, saved.h) : defaultH;
      // Unset (no saved y - a brand new card) sorts after every positioned
      // one, in whatever order `statuses` already had them - the `|| `
      // fallback below only ever kicks in when both sides are the same
      // (including both Infinity, where `Infinity - Infinity` is NaN, which
      // is falsy), so it's a stable tiebreak, not a real comparison.
      const y = saved && Number.isFinite(saved.y) ? saved.y : Infinity;
      return { id, h, y, i };
    });
    entries.sort((a, b) => (a.y - b.y) || (a.i - b.i));
    const positions = new Map();
    let cursorY = 1;
    for (const it of entries) {
      positions.set(it.id, { x: 1, y: cursorY, w: totalCols, h: it.h });
      cursorY += it.h;
    }
    return positions;
  }

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
    const w = Math.min(savedW, totalCols);
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
    class: `card${opts.compact ? " card-compact" : ""}`,
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
      el("div", { class: "title" }, [typeIcon(svc), el("span", { text: svc.name })]),
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

  // "Over the top of every card's bar" per-card control - edit mode only,
  // since it mutates layout state (DashboardLayout.sizes[id].bars) the same
  // way drag/resize does. Its max is this card's *current* width-derived
  // ceiling (maxUptimeBarsForGridWidth), so two cards on the same dashboard
  // can genuinely carry different counts, and a card that's since been made
  // narrower can't keep offering a count that would glitch at its new size.
  if (opts.editable) {
    body.appendChild(renderUptimeBarControl(svc, pos, opts.compact, opts.onLayoutChange));
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
    // Which edit controls a card gets is a property of the layout's own
    // pool (opts.mobile, from DashboardLayout.is_mobile) now, not the
    // actual current window width - a mobile-pool layout is always a
    // single reorderable column, even previewed on a wide screen; a
    // desktop-pool one always gets free-form drag/resize, even narrowed
    // below the phone breakpoint. See ensureActiveLayout for how the
    // *active* layout's pool itself does still follow the real viewport.
    if (opts.mobile) {
      attachMobileReorderControls(body, svc.id, positions, opts.onLayoutChange);
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange, positions, opts.compact);
    } else {
      attachResizeHandle(card, svc.id, pos, opts.onLayoutChange, null, opts.compact);
      attachMoveHandle(card, svc.id, pos, positions, opts.onLayoutChange);
    }
  }

  return card;
}

// Below ~700px, there's only ever room for one card per row anyway - the
// `mobile` hint ensureActiveLayout sends the server on every fetch, so the
// dashboard actually renders a Mobile/Mobile-Compact pool layout (single
// column, Move to top/up/down/bottom instead of free-form drag-to-move/
// resize - see DashboardLayout.is_mobile) below this width, a Desktop/
// Desktop-Compact one above it. Matches the `main { max-width: 700px }`-ish
// breakpoint in style.css, not a coincidence - keep them in sync if either
// changes.
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

  // Troubleshooting aid: this card's own internal grid width/height (the
  // same w/h persisted to DashboardLayout.sizes, in GRID_UNIT-px units) and
  // the uptime bar-count ceiling that width currently implies
  // (maxUptimeBarsForGridWidth), shown live while actively dragging - so a
  // "why are my bars glitching/invisible at this size" question has a
  // direct, on-screen answer instead of needing to guess pixel math by eye.
  const debugBadge = el("div", { class: "resize-debug-badge", hidden: true });
  card.appendChild(debugBadge);

  function updateDebugBadge() {
    debugBadge.textContent = `${pos.w} × ${pos.h} grid · max ${maxUptimeBarsForGridWidth(pos.w)} bars`;
  }

  // Keeps the Bars input (renderUptimeBarControl) honest live during the
  // drag, not just after it ends - both its max attribute (so the browser's
  // own up/down arrows and typed-value validation reflect the card's
  // current width) and its displayed value if that's now above the new
  // ceiling. Purely visual until pointerup actually persists a bars change
  // of its own or a resize of this card's w/h - this never writes anything.
  function updateBarControlMax() {
    const input = card.querySelector(".uptime-bar-count-input");
    if (!input) return;
    const max = maxUptimeBarsForGridWidth(pos.w);
    input.max = String(max);
    if (Number(input.value) > max) input.value = String(max);
  }

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
    updateDebugBadge();
    if (!heightOnly) updateBarControlMax();
  }

  async function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    debugBadge.hidden = true;
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
      await onLayoutChange([heightPatch, ...renumberMobileList(orderedIds, mobilePositions, mobileTotalCols())]);
    } else {
      await onLayoutChange([{ id: serviceId, patch: { w: pos.w, h: pos.h } }]);
    }
    // Width just changed - redraw the strip so it's actually drawing at
    // whatever count this new width now caps out at, not still showing
    // however many bars fit the size it was before this drag.
    loadUptimeStrip(serviceId);
  }

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    start = { px: e.clientX, py: e.clientY, w: pos.w, h: pos.h };
    debugBadge.hidden = false;
    updateDebugBadge();
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
    // input - the Bars field (renderUptimeBarControl) - without this, this
    // handler's own preventDefault() below fires on every pointerdown
    // anywhere on the card, including that field, before the browser ever
    // gets to focus it or register a click on its up/down spinner arrows,
    // so it looked "broken" (stuck, unclickable) when it was actually just
    // never receiving the click at all.
    if (e.target.closest(".resize-handle, button, input")) return;
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

  const barCount = effectiveUptimeBarCount(serviceId, !!(state.activeLayout && state.activeLayout.is_compact));

  let buckets;
  try {
    // Bucketed server-side (queries.get_uptime_buckets) rather than
    // fetching raw rows and reducing them here, like this used to - that
    // relied on /api/history's row limit, which silently truncated the
    // older end of the range for any service whose checks, combined,
    // produce a lot of rows (several checks, a short poll interval), even
    // though the same range's data was all there in the History export.
    buckets = await api(`/api/uptime?service_id=${serviceId}&minutes=${uptimeRangeMinutes()}&bars=${barCount}`);
  } catch (_) {
    return;
  }
  // loadUptimeStrip runs once per card per render pass, all in parallel -
  // the strip element (and the range picked) can be stale by the time this
  // particular fetch resolves if the user changed the dropdown mid-flight.
  if (state.uptimeRange !== range.value || !document.body.contains(strip)) return;

  const now = Date.now();
  const rangeMs = range.minutes * 60000;
  const rangeStart = now - rangeMs;
  const bucketMs = rangeMs / barCount;

  for (let i = 0; i < barCount; i++) {
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

// The active layout's own theme override (Dashboard tab's theme picker,
// edit mode), if it has one - see DashboardLayout.theme's docstring for
// why admin and public apply this differently. Distinguishes the two by
// whether #tab-dashboard exists at all rather than a public/admin flag -
// it's simply not part of public.html's markup.
async function applyActiveLayoutTheme(layout) {
  const dashboardTab = document.getElementById("tab-dashboard");
  if (dashboardTab) {
    // Admin: scoped to the dashboard tab's own background/text/cards - the
    // header/nav stay on whatever Settings > Customizations set globally,
    // see html[data-theme] vs #tab-dashboard[data-layout-theme] in style.css.
    // "dark" for a legacy layout saved before this column existed (still
    // genuinely NULL) - every layout going forward always has one of the
    // four concrete themes.
    dashboardTab.dataset.layoutTheme = (layout && layout.theme) || "dark";
    return;
  }
  // Public: no separate chrome to protect, so this effectively is the
  // whole page's theme. Asks the server for the actually-effective one
  // (queries.resolve_public_theme) rather than just reading layout.theme -
  // Dashboard Settings' "Public port theme override" can make the real
  // theme differ from this specific layout's own stored value, and only
  // the server knows whether that's set. layout.is_mobile (the pool the
  // *resolved* layout actually belongs to, not just a guess) is the
  // correct viewport hint to send here, same as get_public_layout uses.
  try {
    const { theme } = await api(`/api/theme?mobile=${!!(layout && layout.is_mobile)}`);
    document.documentElement.dataset.theme = theme;
  } catch (_) {
    document.documentElement.dataset.theme = (layout && layout.theme) || "dark";
  }
}

async function loadDashboard(cardOpts = {}) {
  const statuses = await ensureStatuses(true);
  const layout = await ensureActiveLayout();
  await applyActiveLayoutTheme(layout);
  const grid = $("#dashboard-grid");
  if (!grid) return;
  grid.innerHTML = "";

  // Compact and mobile are both properties of the layout itself
  // (DashboardLayout.is_compact/is_mobile) - not a per-viewer display
  // option - so admin and public both render a given layout the same way,
  // wherever it's shown. Which layout is active in the first place *is*
  // viewport-driven (see ensureActiveLayout), but once one's chosen,
  // rendering it is deterministic.
  const opts = { ...cardOpts, compact: !!(layout && layout.is_compact), mobile: !!(layout && layout.is_mobile) };

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

  const positions = computeCardLayout(visible, opts.compact, opts.mobile);
  // Cached for effectiveUptimeBarCount/resolveCardGridWidth - the same
  // position objects stay live-mutated in place during a resize drag (see
  // attachResizeHandle), so reading pos.w back out through this later still
  // reflects an in-progress drag, not just whatever was true when this
  // render pass started.
  state.lastCardPositions = positions;
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

// Empty-state copy for "nothing in warn or fail" - one picked at random on
// each render rather than a single fixed line, since this is the view
// you'll load over and over on a healthy system and the same joke gets old
// fast.
const NOTHING_TO_REPORT_LINES = [
  "It's quiet... too quiet...",
  "Nothing to see here!",
  "Clean bill of health.",
  "I forgot to code this bit... Just kidding! There's no notifications.",
  "Nothing to report, Captain.",
  "“These aren’t the notifications you’re looking for. \u{1F44B} There’s nothing to see here.”",
  "“Breaking News: Absolutely nothing has happened. More at 10.”",
  "“Houston, we have no problems…”",
  "“There’s nothing here. We checked twice. Then we checked again because apparently that’s what debugging is.”",
  "“Beep boop. Nothing to report!”",
  "“Nothing to see here. Move along, citizen. This page is completely normal.”",
  "“All caught up! You’re officially more organised than whoever wrote this page.”",
  "“No notifications. The machines have nothing to report. Yet.”",
  "“Congratulations on having nothing to worry about. Please enjoy this suspiciously empty screen.”",
  "“No news is good news. Unless you were expecting news. In which case… awkward.”",
];
// A joke on the joke - 1 in 10000 odds, checked separately below rather
// than just being one more entry in the list above (which would make it
// roughly as common as every other line instead of a genuine rarity).
const NOTHING_TO_REPORT_RARE_LINE = "You actually have notifications! Trust me bro, they're here: https://www.youtube.com/watch?v=dQw4w9WgXcQ";
const NOTHING_TO_REPORT_RARE_ODDS = 10000;

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
    const line = Math.random() < 1 / NOTHING_TO_REPORT_RARE_ODDS
      ? NOTHING_TO_REPORT_RARE_LINE
      : NOTHING_TO_REPORT_LINES[Math.floor(Math.random() * NOTHING_TO_REPORT_LINES.length)];
    list.appendChild(el("div", { class: "empty-state", text: line }));
    return;
  }
  for (const n of items) {
    const row = el("div", { class: "notif-row" }, [
      el("div", { class: "top" }, [
        typeIcon({ type: n.service_type, icon_type: n.icon_type, icon_value: n.icon_value }),
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
// "bell-off" (Feather-style outline icon, matching REORDER_ICONS/
// DRAG_HANDLE_ICON's stroke-based visual language) - shown next to a
// warn/fail row's status whenever that result's own in_sdt (see
// schemas.CheckResultOut) says an alert for it would have been suppressed
// by Scheduled Down Time at the time. Hover explains it via the element's
// own title attribute (see sdtIcon below) rather than a separate label,
// so it stays a compact icon instead of another column to scan.
const SDT_ICON =
  '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.89 17.89 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

function sdtIcon() {
  const span = el("span", {
    class: "sdt-icon",
    title: "This service was in Scheduled Down Time when this happened - any alert for it was suppressed.",
  });
  span.innerHTML = SDT_ICON;
  return span;
}

// "repeat" (Feather-style, same stroke language as SDT_ICON above) - shown
// next to a warn/fail row whenever that result's own suppressed_by_threshold
// (see schemas.CheckResultOut) says its check's "Alert after N consecutive"
// hadn't been reached yet at the time, so no alert went out for it either -
// a separate reason from SDT, and a row can show both icons at once if both
// happen to apply.
const THRESHOLD_ICON =
  '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>';

function thresholdIcon() {
  const span = el("span", {
    class: "threshold-icon",
    title: "This check's \"Alert after\" consecutive count hadn't been reached yet - no alert was sent for this result.",
  });
  span.innerHTML = THRESHOLD_ICON;
  return span;
}

const HISTORY_COLUMNS = {
  time: { label: "Time", value: (r) => fmtTime(r.timestamp), nowrap: true },
  service: { label: "Service", value: (r) => serviceNameById(r.service_id) },
  check: { label: "Check", value: (r) => r.check_name },
  type: { label: "Type", value: (r) => r.check_type },
  status: {
    label: "Status",
    value: (r) => r.status,
    renderCell: (r) =>
      el("span", { class: "history-status-cell" }, [
        el("span", { class: `badge ${r.status}`, text: r.status }),
        r.in_sdt ? sdtIcon() : null,
        r.suppressed_by_threshold ? thresholdIcon() : null,
      ]),
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

// Which result severities currently show - unlike the service filter
// above, defaults to all three (existing behavior, unfiltered) rather than
// none, since narrowing this down is a refinement of an already-useful
// view, not a prerequisite to seeing anything at all. Also not persisted.
const HISTORY_SEVERITIES = [
  { value: "ok", label: "OK" },
  { value: "warn", label: "Warn" },
  { value: "fail", label: "Fail" },
];
state.historySelectedSeverities = HISTORY_SEVERITIES.map((s) => s.value);

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

function serviceById(serviceId) {
  const s = state.statuses.find((s) => s.service.id === serviceId);
  return s ? s.service : null;
}

const HISTORY_SEVERITY_SHORT_LABEL = { ok: "OK", warn: "WARN", fail: "FAIL" };

function historyRowElement(r) {
  if (isMobileViewport()) return historyRowElementMobile(r);
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

// Mobile's History row: everything that matters at a glance on one line -
// compact time, the service's icon alone (its full name doesn't fit and
// rarely adds much once you recognize the icon), a short severity badge,
// and the same abbreviated result summary the mobile dashboard card checks
// use (shortCheckSummary) - then a ">" button that expands a second block
// with everything left out (full service/check name, type, full message,
// response time), the same information the row would have shown outright
// before this compact layout existed. One <td> (not one per column - the
// column-customization feature is desktop-only, there's nothing to
// individually show/hide/reorder here) keeps this compatible with the
// same infinite-scroll append logic (loadMoreHistoryRows) as the desktop
// row.
function historyRowElementMobile(r) {
  const svc = serviceById(r.service_id);
  const detail = el("div", { class: "history-row-detail hidden" }, [
    el("div", {}, [el("span", { class: "text-dim" }, "Service: "), svc ? svc.name : `#${r.service_id}`]),
    el("div", {}, [el("span", { class: "text-dim" }, "Check: "), r.check_name]),
    el("div", {}, [el("span", { class: "text-dim" }, "Type: "), r.check_type]),
    el("div", {}, [el("span", { class: "text-dim" }, "Time: "), fmtTime(r.timestamp)]),
    r.response_time_ms
      ? el("div", {}, [el("span", { class: "text-dim" }, "Response: "), `${Math.round(r.response_time_ms)} ms`])
      : null,
    r.in_sdt ? el("div", {}, [el("span", { class: "text-dim" }, "In SDT: "), "Yes - alert was suppressed"]) : null,
    r.suppressed_by_threshold
      ? el("div", {}, [el("span", { class: "text-dim" }, "Alert threshold: "), "Not yet reached - no alert was sent"])
      : null,
    el("div", {}, [el("span", { class: "text-dim" }, "Message: "), r.message || "(none)"]),
  ]);
  const expandBtn = el(
    "button",
    { type: "button", class: "history-expand-btn", "aria-label": "More info", title: "More info" },
    "›"
  );
  expandBtn.addEventListener("click", () => {
    const expanded = detail.classList.toggle("hidden") === false;
    expandBtn.classList.toggle("expanded", expanded);
  });
  const compactRow = el("div", { class: "history-row-compact" }, [
    el("span", { class: "history-compact-time", text: fmtTimeCompact(r.timestamp) }),
    svc ? typeIcon(svc) : null,
    el("span", { class: `badge ${r.status} badge-sm`, text: HISTORY_SEVERITY_SHORT_LABEL[r.status] || r.status }),
    r.in_sdt ? sdtIcon() : null,
    r.suppressed_by_threshold ? thresholdIcon() : null,
    el("span", { class: "history-compact-msg", text: shortCheckSummary(r.check_type, r.status, r.message) }),
    expandBtn,
  ]);
  return el(
    "tr",
    { class: "history-row-mobile" },
    el("td", { colspan: String(Math.max(1, state.historyColumns.length)) }, [compactRow, detail])
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

function historySeveritiesQuery() {
  return state.historySelectedSeverities.map((s) => `statuses=${s}`).join("&");
}

// Resets to page 1 - called on service-selection/severity/range change and
// whenever the column set changes (simplest way to keep already-rendered
// rows in sync with a new column list, and cheap enough at this page size
// to just do).
async function loadHistoryTab() {
  await ensureStatuses();
  renderHistoryServicePills();
  renderHistorySeverityPills();
  renderHistoryHeader();
  state.historyBeforeId = null;
  state.historyExhausted = false;
  state.historyLoading = false;
  const body = $("#history-body");
  if (!body) return;
  body.innerHTML = "";
  if (state.historySelectedServiceIds.length === 0 || state.historySelectedSeverities.length === 0) {
    const text = state.historySelectedServiceIds.length === 0 ? "Pick at least one service above" : "Pick at least one severity above";
    body.appendChild(el("tr", {}, el("td", { colspan: String(Math.max(1, state.historyColumns.length)), class: "empty-state", text })));
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
  if (state.historySelectedServiceIds.length === 0 || state.historySelectedSeverities.length === 0) return;
  state.historyLoading = true;

  let rows;
  try {
    const cursor = state.historyBeforeId != null ? `&before_id=${state.historyBeforeId}` : "";
    rows = await api(
      `/api/history?${historyServiceIdsQuery()}&${historySeveritiesQuery()}&minutes=${uptimeRangeMinutes()}&limit=${HISTORY_PAGE_SIZE}${cursor}`
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

// Same floating pill pattern as the service filter above, one per result
// severity - click to toggle it in or out of the result set. Colored by
// severity when active (rather than the generic accent every other pill
// uses) so Fail/Warn/OK are distinguishable at a glance in the bar itself,
// not just in the rows below it.
function renderHistorySeverityPills() {
  const bar = $("#history-severity-bar");
  if (!bar) return;
  bar.innerHTML = "";
  const selected = new Set(state.historySelectedSeverities);
  for (const sev of HISTORY_SEVERITIES) {
    const active = selected.has(sev.value);
    bar.appendChild(
      el(
        "button",
        {
          type: "button",
          class: `service-pill severity-pill-${sev.value}${active ? " active" : ""}`,
          "aria-pressed": active ? "true" : "false",
          onclick: () => {
            const next = new Set(state.historySelectedSeverities);
            if (next.has(sev.value)) next.delete(sev.value);
            else next.add(sev.value);
            state.historySelectedSeverities = [...next];
            loadHistoryTab();
          },
        },
        sev.label
      )
    );
  }
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
  if (state.historySelectedServiceIds.length === 0 || state.historySelectedSeverities.length === 0) return;
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
        `/api/history?${historyServiceIdsQuery()}&${historySeveritiesQuery()}&minutes=${uptimeRangeMinutes()}&limit=${EXPORT_PAGE_SIZE}${cursor}`
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

  // "In SDT"/"Alert Threshold Suppressed" always export regardless of
  // which columns are currently shown/hidden on screen - both are audit
  // data (was this row's alert suppressed, and why), not really a display
  // preference the Columns dialog's show/hide is meant to cover, unlike
  // the rest.
  const cols = state.historyColumns.map((k) => HISTORY_COLUMNS[k]);
  const header = [...cols.map((c) => c.label), "In SDT", "Alert Threshold Suppressed"];
  const lines = [header.map(csvEscape).join(",")];
  for (const r of allRows) {
    const values = [...cols.map((c) => c.value(r)), r.in_sdt ? "TRUE" : "FALSE", r.suppressed_by_threshold ? "TRUE" : "FALSE"];
    lines.push(values.map(csvEscape).join(","));
  }

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
