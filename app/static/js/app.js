// Admin app: full CRUD over services/checks, on top of the read-only
// rendering shared with the public dashboard via common.js.

// Inline SVG (not a Unicode/Braille character - font-dependent glyphs like
// "⠿" render inconsistently and can look lopsided rather than a clean grip)
// for the checks-grid's "Checks" section collapse chevron. DRAG_HANDLE_ICON
// is the equivalent for drag handles - defined in common.js since the
// History columns list (also shared with the public page) needs it too.
const CHEVRON_DOWN_ICON =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6,9 12,15 18,9"/></svg>';

// ---------- tabs ----------

function initTabs() {
  $all(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  $all(".sub-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchSettingsSubTab(btn.dataset.subtab));
  });
}

function switchSettingsSubTab(subtab) {
  $all(".sub-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.subtab === subtab));
  $all(".subtab-panel").forEach((p) => p.classList.toggle("active", p.id === `subtab-${subtab}`));
  if (subtab === "channels") loadChannels();
  if (subtab === "downtime") loadServiceGroups().then(loadSchedules);
  if (subtab === "pruning") loadLogPruningSettings();
  if (subtab === "dashboard-settings") loadDashboardSettings();
}

function switchTab(tab) {
  state.tab = tab;
  $all(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $all(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  document.body.classList.toggle("wide-main", tab === "dashboard");
  updateHeaderControlsVisibility(tab);
  if (tab === "dashboard") loadDashboardAdmin();
  if (tab === "notifications") loadNotifications();
  if (tab === "history") loadHistoryTab();
  if (tab === "settings") loadSettings();
}

// Layout editing only makes sense on the Dashboard; the uptime-range picker
// is meaningless on Settings (nothing on that tab uses it) but still applies
// to Notifications/History same as Dashboard, so it only excludes Settings.
function updateHeaderControlsVisibility(tab) {
  const layoutControls = $(".layout-controls");
  if (layoutControls) layoutControls.hidden = tab !== "dashboard";
  const uptimeControl = $(".uptime-range-control");
  if (uptimeControl) uptimeControl.hidden = tab === "settings";
}

let layoutEditMode = false;

function isDefaultLayoutActive() {
  return !!(state.activeLayout && state.activeLayout.is_default);
}

async function loadDashboardAdmin() {
  await loadDashboard({
    interactive: true,
    editable: layoutEditMode,
    onRunNow: runNow,
    onHistory: (id) => { switchTab("history"); setHistorySelectedServices([id]); loadHistoryTab(); },
    onLayoutChange: persistCardLayout,
    onRemoveCard: layoutEditMode && !isDefaultLayoutActive() ? removeCardFromLayout : null,
  });
  loadLayoutList();
  renderAddCardControl();
  updateCompactBtn();
}

// Compact is fixed on a layout at creation, not a flag flippable on an
// existing one - a layout is either one of your compact layouts or one of
// your full ones, never both at different times (see newLayoutFromCurrent,
// which creates within whichever mode is currently active). "Compact view"
// is a mode switch, not a per-layout toggle: it activates one of your
// compact layouts (or one of your full ones), and the layout dropdown
// (loadLayoutList) only ever lists the ones matching the mode you're
// currently in.
function updateCompactBtn() {
  const btn = $("#layout-compact-btn");
  if (!btn || !state.activeLayout) return;
  const isCompact = !!state.activeLayout.is_compact;
  btn.classList.toggle("primary", isCompact);
  btn.title = isCompact ? "Switch to your full (non-compact) layouts" : "Switch to your compact layouts";
}

async function toggleLayoutCompact() {
  const targetCompact = !(state.activeLayout && state.activeLayout.is_compact);
  let layouts;
  try {
    layouts = await api("/api/dashboard-layouts");
  } catch (e) {
    toast("Could not load layouts: " + e.message, true);
    return;
  }
  const candidates = layouts.filter((l) => !!l.is_compact === targetCompact);

  if (candidates.length === 0) {
    // Bootstrap case: +New always creates within whatever mode is
    // currently active, so switching to a mode with nothing in it yet
    // needs its own explicit "create the first one" prompt instead.
    const name = prompt(`No ${targetCompact ? "compact" : "full"} layouts yet - name your first one:`);
    if (!name) return;
    try {
      state.activeLayout = await api("/api/dashboard-layouts", {
        method: "POST",
        body: JSON.stringify({
          name,
          card_service_ids: state.statuses.map((s) => s.service.id),
          is_compact: targetCompact,
        }),
      });
    } catch (e) {
      toast("Could not create layout: " + e.message, true);
      return;
    }
    toast(`Layout "${name}" created`);
    loadDashboardAdmin();
    return;
  }

  const target = candidates.find((l) => l.is_active) || candidates[0];
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${target.id}/activate`, { method: "POST" });
  } catch (e) {
    toast("Could not switch layout: " + e.message, true);
    return;
  }
  loadDashboardAdmin();
}

// Drag-to-move/resize only work while this is on - browsing the dashboard
// day to day shouldn't risk bumping a card out of place by an accidental
// drag. Not persisted: every page load starts back in plain view mode.
function toggleLayoutEditMode() {
  layoutEditMode = !layoutEditMode;
  const btn = $("#layout-edit-btn");
  btn.textContent = layoutEditMode ? "Done editing" : "Edit layout";
  btn.classList.toggle("primary", layoutEditMode);
  document.body.classList.toggle("layout-editing", layoutEditMode);
  if (state.tab === "dashboard") loadDashboardAdmin();
}

async function runNow(serviceId) {
  try {
    await api(`/api/services/${serviceId}/run-now`, { method: "POST" });
    toast("Checks run");
  } catch (e) {
    toast("Run failed: " + e.message, true);
  }
  if (state.tab === "dashboard" && !layoutEditMode) loadDashboardAdmin();
  if (state.tab === "settings") loadSettings();
}

// ---------- dashboard layouts ----------

// `updates` is [{id, patch}], patch being a partial {w,h} and/or {x,y} -
// each merged onto whatever's already saved for that service so a resize
// doesn't clobber a saved position and vice versa. Always sent as one PUT
// so a multi-card cascade (drag-to-move pushing others out of the way)
// saves every affected card's new position atomically instead of racing
// separate requests against each other. Also stamps `columns` with however
// wide the grid was just now, so the layout remembers the window width it
// was edited at - see computeCardLayout in common.js for how that's used.
async function persistCardLayout(updates) {
  if (!state.activeLayout || !state.activeLayout.id) return;
  const sizes = { ...state.activeLayout.sizes };
  for (const { id, patch } of updates) {
    sizes[String(id)] = { ...(sizes[String(id)] || {}), ...patch };
  }
  const body = { sizes };
  if (Number.isFinite(state.lastGridColumns)) body.columns = state.lastGridColumns;
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${state.activeLayout.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  } catch (e) {
    toast("Could not save layout: " + e.message, true);
  }
}

async function loadLayoutList() {
  let layouts;
  try {
    layouts = await api("/api/dashboard-layouts");
  } catch (e) {
    return;
  }
  // Only ever lists layouts matching the current mode (see
  // toggleLayoutCompact) - a compact and a full layout are never options in
  // the same dropdown, since switching between them is what the Compact
  // view button next to this is for.
  const compactMode = !!(state.activeLayout && state.activeLayout.is_compact);
  const select = $("#layout-select");
  select.innerHTML = "";
  for (const l of layouts) {
    if (!!l.is_compact !== compactMode) continue;
    let text = l.name;
    if (l.is_default) text += " 🔒";
    select.appendChild(el("option", { value: l.id, text, selected: l.is_active ? "selected" : null }));
  }
  const deleteBtn = $("#layout-delete-btn");
  if (deleteBtn) {
    const isDefault = isDefaultLayoutActive();
    deleteBtn.disabled = isDefault;
    deleteBtn.title = isDefault ? "The All Services layout can't be deleted" : "";
  }
}

// The "+ Add card" jump-menu: only meaningful in edit mode, for a custom
// (non-default) layout that's actually missing at least one service's card
// - the is_default "All Services" layout always shows everything, nothing
// to add there.
function renderAddCardControl() {
  const wrap = $("#layout-add-card-wrap");
  const select = $("#layout-add-card-select");
  if (!wrap || !select) return;
  const layout = state.activeLayout;
  if (!layoutEditMode || !layout || layout.is_default) {
    wrap.hidden = true;
    return;
  }
  const shown = new Set(layout.card_service_ids || []);
  const hidden = state.statuses.filter((s) => !shown.has(s.service.id));
  if (hidden.length === 0) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  select.innerHTML = "";
  select.appendChild(el("option", { value: "", text: "+ Add card…" }));
  for (const s of hidden) {
    select.appendChild(el("option", { value: s.service.id, text: s.service.name }));
  }
  select.value = "";
}

async function removeCardFromLayout(serviceId) {
  if (!state.activeLayout || state.activeLayout.is_default) return;
  const cardServiceIds = state.activeLayout.card_service_ids.filter((id) => id !== serviceId);
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${state.activeLayout.id}`, {
      method: "PUT",
      body: JSON.stringify({ card_service_ids: cardServiceIds }),
    });
  } catch (e) {
    toast("Could not remove card: " + e.message, true);
    return;
  }
  loadDashboardAdmin();
}

async function addCardToLayout(serviceId) {
  if (!state.activeLayout || state.activeLayout.is_default) return;
  const cardServiceIds = [...state.activeLayout.card_service_ids, serviceId];
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${state.activeLayout.id}`, {
      method: "PUT",
      body: JSON.stringify({ card_service_ids: cardServiceIds }),
    });
  } catch (e) {
    toast("Could not add card: " + e.message, true);
    return;
  }
  loadDashboardAdmin();
}

async function onLayoutSelectChange() {
  const id = $("#layout-select").value;
  if (!id) return;
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${id}/activate`, { method: "POST" });
  } catch (e) {
    toast("Could not switch layout: " + e.message, true);
    return;
  }
  loadDashboardAdmin();
}

async function newLayoutFromCurrent() {
  const name = prompt("Name for the new layout:");
  if (!name) return;
  const sizes = state.activeLayout ? state.activeLayout.sizes : {};
  const columns = state.lastGridColumns;
  // Starts as a copy of whatever's currently visible (every service, if
  // duplicating the All Services layout) - a sensible starting point the
  // user then trims with the remove-card button, rather than an empty
  // layout with nothing on it.
  const cardServiceIds = isDefaultLayoutActive() || !state.activeLayout
    ? state.statuses.map((s) => s.service.id)
    : state.activeLayout.card_service_ids;
  const isCompact = state.activeLayout ? !!state.activeLayout.is_compact : false;
  try {
    state.activeLayout = await api("/api/dashboard-layouts", {
      method: "POST",
      body: JSON.stringify({ name, sizes, columns, card_service_ids: cardServiceIds, is_compact: isCompact }),
    });
  } catch (e) {
    toast("Could not create layout: " + e.message, true);
    return;
  }
  toast(`Layout "${name}" created`);
  loadDashboardAdmin();
}

async function renameActiveLayout() {
  if (!state.activeLayout) return;
  const name = prompt("Rename layout:", state.activeLayout.name);
  if (!name || name === state.activeLayout.name) return;
  try {
    state.activeLayout = await api(`/api/dashboard-layouts/${state.activeLayout.id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    });
  } catch (e) {
    toast("Rename failed: " + e.message, true);
    return;
  }
  loadLayoutList();
}

async function deleteActiveLayout() {
  if (!state.activeLayout) return;
  if (state.activeLayout.is_default) {
    toast("The All Services layout can't be deleted", true);
    return;
  }
  if (!confirm(`Delete layout "${state.activeLayout.name}"?`)) return;
  try {
    await api(`/api/dashboard-layouts/${state.activeLayout.id}`, { method: "DELETE" });
  } catch (e) {
    toast("Delete failed: " + e.message, true);
    return;
  }
  state.activeLayout = null;
  loadDashboardAdmin();
}

// ---------- settings: services ----------

// check_id -> { enabled?, config? } staged but not yet saved, plus a
// separate set of check_ids staged for deletion. Every render of the
// Settings page (initial load, after Add/Edit/Delete-service, tab switches)
// re-fetches fresh data then re-applies both on top, so nothing but an
// explicit Save/Discard ever loses a pending quick-edit or a pending delete.
let pendingCheckChanges = new Map();
let pendingCheckDeletions = new Set();

function loadCollapsedServiceIds() {
  const raw = getCookie("hc_collapsed_services");
  return raw ? new Set(raw.split(",").filter(Boolean).map(Number)) : new Set();
}

function saveCollapsedServiceIds() {
  setCookie("hc_collapsed_services", Array.from(collapsedServiceIds).join(","), 365);
}

let collapsedServiceIds = loadCollapsedServiceIds();

async function loadSettings() {
  try {
    state.services = await api("/api/services");
  } catch (e) {
    toast("Failed to load services: " + e.message, true);
    return;
  }
  applyPendingChangesToState();
  renderServicesFromState();
}

function applyPendingChangesToState() {
  for (const svc of state.services) {
    for (const c of svc.checks) {
      const patch = pendingCheckChanges.get(c.id);
      if (!patch) continue;
      if (patch.enabled !== undefined) c.enabled = patch.enabled;
      if (patch.config !== undefined) c.config = patch.config;
    }
  }
}

function renderServicesFromState() {
  const body = $("#services-body");
  body.innerHTML = "";
  for (const svc of state.services) {
    body.appendChild(renderServiceRow(svc));
  }
}

function stageCheckChange(check, patch) {
  const existing = pendingCheckChanges.get(check.id) || {};
  const merged = { ...existing };
  if (patch.enabled !== undefined) merged.enabled = patch.enabled;
  if (patch.config !== undefined) merged.config = { ...(existing.config || check.config), ...patch.config };
  pendingCheckChanges.set(check.id, merged);

  if (patch.enabled !== undefined) check.enabled = patch.enabled;
  if (patch.config !== undefined) check.config = { ...check.config, ...patch.config };

  renderServicesFromState();
  updateUnsavedBanner();
}

function stageCheckDeletion(check) {
  pendingCheckDeletions.add(check.id);
  renderServicesFromState();
  updateUnsavedBanner();
}

function undoCheckDeletion(check) {
  pendingCheckDeletions.delete(check.id);
  renderServicesFromState();
  updateUnsavedBanner();
}

function pendingChangeCount() {
  return pendingCheckChanges.size + pendingCheckDeletions.size;
}

function updateUnsavedBanner() {
  const hidden = pendingChangeCount() === 0;
  $("#unsaved-banner").hidden = hidden;
  $("#unsaved-banner-bottom").hidden = hidden;
}

async function saveChanges() {
  const deleteIds = Array.from(pendingCheckDeletions);
  const updates = Array.from(pendingCheckChanges, ([check_id, patch]) => ({ check_id: Number(check_id), ...patch }))
    .filter((u) => !pendingCheckDeletions.has(u.check_id));

  if (deleteIds.length === 0 && updates.length === 0) return;

  const deleteResults = await Promise.allSettled(
    deleteIds.map((id) => api(`/api/checks/${id}`, { method: "DELETE" }))
  );
  const failedDeletes = deleteResults.filter((r) => r.status === "rejected").length;

  let updateFailed = false;
  if (updates.length > 0) {
    try {
      await api("/api/checks/bulk-update", { method: "POST", body: JSON.stringify({ updates }) });
    } catch (e) {
      updateFailed = true;
      toast("Save failed: " + e.message, true);
    }
  }

  if (failedDeletes > 0) {
    toast(`${failedDeletes} deletion(s) failed`, true);
  }
  if (!updateFailed) {
    // Only drop the changes that actually made it - keep anything that
    // failed staged so the user doesn't lose it silently.
    for (const id of deleteIds) pendingCheckDeletions.delete(id);
    for (const u of updates) pendingCheckChanges.delete(u.check_id);
    if (failedDeletes === 0 && !updateFailed) toast("Changes saved");
  }
  updateUnsavedBanner();
  loadSettings();
}

function discardChanges() {
  pendingCheckChanges.clear();
  pendingCheckDeletions.clear();
  updateUnsavedBanner();
  loadSettings();
}

function renderServiceRow(svc) {
  const tr = el("tr", { class: "service-row" });

  tr.appendChild(el("td", { "data-label": "Name", text: svc.name }));
  tr.appendChild(el("td", { "data-label": "Type" }, el("span", {}, [typeIcon(svc.type), " " + svc.type])));
  tr.appendChild(el("td", { "data-label": "Local", text: svc.local_url || "-" }));
  tr.appendChild(el("td", { "data-label": "Remote", text: svc.remote_url || "-" }));
  tr.appendChild(el("td", { "data-label": "Interval", text: svc.poll_interval_seconds ? `${svc.poll_interval_seconds}s` : "default" }));
  tr.appendChild(el("td", { "data-label": "Status" }, el("span", { class: `badge ${svc.enabled ? "ok" : "disabled"}`, text: svc.enabled ? "enabled" : "disabled" })));

  const actions = el("div", { style: "display:flex; gap:6px;" }, [
    el("button", { class: "small", onclick: () => openServiceModal(svc) }, "Edit"),
    el("button", { class: "small danger", onclick: () => deleteService(svc) }, "Delete"),
  ]);
  tr.appendChild(el("td", {}, actions));

  const detailRow = el("tr", { class: "service-detail-row" }, el("td", { colspan: "7" }, renderChecksPanel(svc)));

  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(tr);
  wrapper.appendChild(detailRow);
  return wrapper;
}

function renderChecksPanel(svc) {
  const isCollapsed = collapsedServiceIds.has(svc.id);
  const panel = el("div", { class: "checks-subpanel" });
  const actions = [el("button", { class: "small primary", onclick: () => openCheckModal(svc) }, "+ Add check")];
  if (svc.type === "plex" || svc.type === "jellyfin") {
    actions.unshift(
      el(
        "button",
        {
          class: "small",
          title: "Fetches this service's configured library folders and adds a filesystem check for each",
          onclick: () => scanLibraries(svc),
        },
        "Scan libraries"
      )
    );
  }
  // The expand/collapse toggle lives right above the list it controls
  // (rather than off at the top of the whole service row, far from what it
  // actually does) and only hides the checks-grid itself - Add check/Scan
  // libraries above it stay usable either way.
  const toggleBtn = el("button", { class: "checks-toggle" });
  const chevron = el("span", { class: "checks-toggle-chevron" + (isCollapsed ? " collapsed" : "") });
  chevron.innerHTML = CHEVRON_DOWN_ICON;
  toggleBtn.append(chevron, el("span", { text: `Checks (${svc.checks.length})` }));
  panel.appendChild(
    el("div", { style: "display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;" }, [
      toggleBtn,
      el("div", { style: "display:flex; gap:6px;" }, actions),
    ])
  );
  if (svc.checks.length === 0) {
    panel.appendChild(el("div", { class: "text-dim", text: "No checks configured" }));
    return panel;
  }
  const grid = el("div", { class: "checks-grid" }, [
    el("div", { class: "checks-grid-header" }),
    el("div", { class: "checks-grid-header", text: "Enable" }),
    el("div", { class: "checks-grid-header", text: "Check Type" }),
    el("div", { class: "checks-grid-header", text: "Name" }),
    el("div", { class: "checks-grid-header", text: "Alert level" }),
    el("div", { class: "checks-grid-header", text: "Actions" }),
  ]);
  grid.style.display = isCollapsed ? "none" : "";
  for (const c of svc.checks) {
    appendCheckGridRow(grid, svc, c);
  }
  toggleBtn.addEventListener("click", () => {
    const collapse = grid.style.display !== "none";
    grid.style.display = collapse ? "none" : "";
    chevron.classList.toggle("collapsed", collapse);
    if (collapse) collapsedServiceIds.add(svc.id); else collapsedServiceIds.delete(svc.id);
    saveCollapsedServiceIds();
  });
  panel.appendChild(grid);
  return panel;
}

function appendCheckGridRow(grid, svc, c) {
  const pendingDelete = pendingCheckDeletions.has(c.id);
  const rowClass = pendingDelete ? "row-pending-delete" : "";

  const handle = el("div", { class: "drag-handle", "data-check-id": c.id, title: pendingDelete ? null : "Drag to reorder" });
  if (!pendingDelete) handle.innerHTML = DRAG_HANDLE_ICON;
  grid.appendChild(handle);
  if (!pendingDelete) attachCheckDragHandle(handle, grid, svc);

  grid.appendChild(
    el("div", { class: rowClass, "data-label": "Enable" }, el("input", {
      type: "checkbox",
      checked: c.enabled ? "checked" : null,
      disabled: pendingDelete ? "disabled" : null,
      onchange: (e) => stageCheckChange(c, { enabled: e.target.checked }),
    }))
  );
  grid.appendChild(
    el("div", { class: rowClass, "data-label": "Check type" }, el("span", { class: `badge ${c.enabled ? "ok" : "disabled"}`, text: c.type }))
  );
  grid.appendChild(
    el("div", { class: `check-name-cell ${rowClass}`, "data-label": "Name", title: c.name }, el("span", {}, [
      c.name,
      c.interval_seconds ? el("span", { class: "text-dim", text: ` (every ${c.interval_seconds}s)` }) : null,
    ]))
  );

  const alertLevel = c.config.alert_level === "warn" ? "warn" : "fail";
  grid.appendChild(
    el("div", { class: rowClass, "data-label": "Alert level" }, (() => {
      if (pendingDelete) return el("span", { class: "text-dim", text: "-" });
      if (NO_ALERT_LEVEL_TYPES.has(c.type)) {
        return el("span", { class: "text-dim", title: "This check's own Warn/Fail % thresholds decide this instead", text: "—" });
      }
      return el(
        "button",
        {
          class: `severity-toggle ${alertLevel}`,
          title: "Status reported when this check fails - click to toggle",
          onclick: () => stageCheckChange(c, { config: { alert_level: alertLevel === "fail" ? "warn" : "fail" } }),
        },
        [el("span", { class: `dot ${alertLevel}` }), alertLevel === "fail" ? "Fail" : "Warn"]
      );
    })())
  );

  grid.appendChild(
    el("div", { class: `check-actions ${rowClass}` }, pendingDelete
      ? [el("button", { class: "small", onclick: () => undoCheckDeletion(c) }, "Undo")]
      : [
          el("button", { class: "small", onclick: () => openCheckModal(svc, c) }, "Edit"),
          c.is_builtin ? null : el("button", { class: "small danger", onclick: () => stageCheckDeletion(c) }, "Delete"),
        ]
    )
  );
}

// Each check's row is 6 sibling divs directly under .checks-grid, in DOM
// order (no wrapper element - that would break the flat grid's nth-child
// CSS and its column layout, since only direct children of a CSS Grid
// container participate in it). Reordering therefore means moving real DOM
// nodes as a group of 6, not re-rendering - getRowNodes below walks forward
// from a row's drag handle (always the 1st of the 6) to collect the rest.
function getRowNodes(handleEl) {
  const nodes = [handleEl];
  let n = handleEl;
  for (let i = 0; i < 5; i++) {
    n = n.nextElementSibling;
    nodes.push(n);
  }
  return nodes;
}

function attachCheckDragHandle(handle, grid, svc) {
  let rowNodes = null;

  function onPointerMove(e) {
    if (!rowNodes) return;
    const otherHandles = $all(".drag-handle", grid).filter((h) => h !== handle);
    let targetHandle = null;
    let insertAfter = false;
    for (const h of otherHandles) {
      const rect = h.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      targetHandle = h;
      insertAfter = e.clientY >= mid;
      if (!insertAfter) break;
    }
    if (!targetHandle) return;
    const targetNodes = getRowNodes(targetHandle);
    const anchor = insertAfter ? targetNodes[targetNodes.length - 1].nextSibling : targetNodes[0];
    for (const node of rowNodes) grid.insertBefore(node, anchor);
  }

  function onPointerUp() {
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    for (const node of rowNodes) node.classList.remove("checks-grid-row-dragging");
    rowNodes = null;

    const orderedIds = $all(".drag-handle", grid).map((h) => Number(h.dataset.checkId));
    const byId = new Map(svc.checks.map((c) => [c.id, c]));
    const reordered = orderedIds.map((id) => byId.get(id)).filter(Boolean);
    svc.checks.length = 0;
    svc.checks.push(...reordered);

    api(`/api/services/${svc.id}/checks/reorder`, {
      method: "POST",
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }).catch((e) => toast("Could not save check order: " + e.message, true));
  }

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    rowNodes = getRowNodes(handle);
    for (const node of rowNodes) node.classList.add("checks-grid-row-dragging");
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });
}

async function deleteService(svc) {
  if (!confirm(`Delete service "${svc.name}"? This removes its history and notifications too.`)) return;
  try {
    await api(`/api/services/${svc.id}`, { method: "DELETE" });
    toast("Service deleted");
    for (const c of svc.checks) {
      pendingCheckChanges.delete(c.id);
      pendingCheckDeletions.delete(c.id);
    }
    updateUnsavedBanner();
    loadSettings();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

async function scanLibraries(svc) {
  let result;
  try {
    result = await api(`/api/services/${svc.id}/scan-libraries`, { method: "POST" });
  } catch (e) {
    toast("Library scan failed: " + e.message, true);
    return;
  }
  if (result.checks_created.length === 0) {
    toast(result.paths_found === 0 ? "No libraries found" : "All library paths already have a check");
  } else {
    toast(`Added ${result.checks_created.length} library check(s)`);
  }
  loadSettings();
}

// ---------- service modal ----------

const DEFAULT_USERNAME_HINT = "(optional - leave blank if this instance has no auth)";
const CREDENTIAL_MODES = {
  plex: { keyLabel: "X-Plex-Token", showUsername: false, showPlexSignin: true },
  qbittorrent: { keyLabel: "Password", showUsername: true, showPlexSignin: false, usernameHint: DEFAULT_USERNAME_HINT },
  rtorrent: { keyLabel: "Password", showUsername: true, showPlexSignin: false, usernameHint: DEFAULT_USERNAME_HINT },
  rutorrent: { keyLabel: "Password", showUsername: true, showPlexSignin: false, usernameHint: DEFAULT_USERNAME_HINT },
  deluge: { keyLabel: "Password", showUsername: true, showPlexSignin: false, usernameHint: DEFAULT_USERNAME_HINT },
  jellyfin: {
    keyLabel: "API key",
    showUsername: true,
    showPlexSignin: false,
    usernameLabel: "Admin username",
    usernameHint: "(optional - see \"Admin password\" below)",
    showJellyfinAdmin: true,
  },
};

// Grouping (and alphabetical order within each group) for the Add/Edit
// service type dropdown - purely a display concern, doesn't affect
// SERVICE_TYPES itself. Kept in sync by hand; every type in
// state.meta.service_types is expected to appear in exactly one of these.
const SERVICE_TYPE_CATEGORIES = [
  { label: "Arr Stack", types: ["chaptarr", "lidarr", "prowlarr", "radarr", "sonarr", "whisparr"] },
  { label: "Downloaders", types: ["deluge", "qbittorrent", "rtorrent", "rutorrent"] },
  { label: "Media Servers", types: ["jellyfin", "plex"] },
  { label: "Other", types: ["generic", "jellyseerr", "overseerr"] },
];

function serviceTypeLabel(type) {
  const defaults = state.meta.service_type_defaults && state.meta.service_type_defaults[type];
  return (defaults && defaults.name) || type.charAt(0).toUpperCase() + type.slice(1);
}

function credentialModeFor(type) {
  return CREDENTIAL_MODES[type] || { keyLabel: "API key", showUsername: false, showPlexSignin: false };
}

function updateCredentialFieldsForType(type) {
  const mode = credentialModeFor(type);
  $("#svc-key-label").childNodes[0].textContent = mode.keyLabel + " ";
  $("#svc-username-field").hidden = !mode.showUsername;
  $("#svc-username-label").childNodes[0].textContent = (mode.usernameLabel || "Username") + " ";
  $("#svc-username-hint").textContent = mode.usernameHint || "";
  $("#svc-plex-signin").hidden = !mode.showPlexSignin;
  $("#svc-jellyfin-admin-field").hidden = !mode.showJellyfinAdmin;
}

function applyServiceTypeDefaults(type, { autofillName } = {}) {
  const defaults = (state.meta.service_type_defaults && state.meta.service_type_defaults[type]) || {};
  const nameInput = $("#svc-name");
  const prevAutofill = nameInput.dataset.autofillValue || "";
  if (autofillName && (nameInput.value === "" || nameInput.value === prevAutofill)) {
    nameInput.value = defaults.name || "";
  }
  nameInput.dataset.autofillValue = defaults.name || "";

  const localInput = $("#svc-local-url");
  localInput.placeholder = defaults.port ? `http://${type}:${defaults.port}` : `http://${type}`;
}

function resetConnStatus() {
  for (const which of ["local", "remote"]) {
    const node = $(`#svc-${which}-status`);
    node.className = "conn-status";
    node.textContent = "";
    node.title = "";
  }
}

function openServiceModal(svc = null) {
  $("#service-modal-title").textContent = svc ? "Edit service" : "Add service";
  $("#svc-id").value = svc ? svc.id : "";
  $("#svc-name").value = svc ? svc.name : "";
  $("#svc-local-url").value = svc && svc.local_url ? svc.local_url : "";
  $("#svc-remote-url").value = svc && svc.remote_url ? svc.remote_url : "";
  $("#svc-check-both").checked = svc ? !!svc.check_both_targets : false;
  $("#svc-username").value = svc && svc.username ? svc.username : "";
  setSecretFieldState($("#svc-key"), $("#svc-key-use-env"), svc && svc.api_key_env_var);
  $("#svc-key-hint").textContent = svc && svc.has_api_key && !svc.api_key_env_var ? "(already set - leave blank to keep)" : "";
  setSecretFieldState($("#svc-jellyfin-admin-password"), $("#svc-jellyfin-admin-password-use-env"), svc && svc.jellyfin_admin_password_env_var);
  $("#svc-jellyfin-admin-password-hint").textContent =
    svc && svc.has_jellyfin_admin_password && !svc.jellyfin_admin_password_env_var
      ? "(already set - leave blank to keep)"
      : "(optional, paired with the Admin username above)";
  $("#svc-interval").value = svc && svc.poll_interval_seconds ? svc.poll_interval_seconds : "";
  $("#svc-enabled").checked = svc ? svc.enabled : true;
  $("#svc-notes").value = svc && svc.notes ? svc.notes : "";
  resetConnStatus();

  const typeSelect = $("#svc-type");
  typeSelect.innerHTML = "";
  const knownTypes = new Set(state.meta.service_types);
  for (const cat of SERVICE_TYPE_CATEGORIES) {
    const types = cat.types.filter((t) => knownTypes.has(t));
    if (types.length === 0) continue;
    const group = el("optgroup", { label: cat.label });
    for (const t of types) {
      group.appendChild(el("option", { value: t, text: serviceTypeLabel(t) }));
    }
    typeSelect.appendChild(group);
  }
  typeSelect.disabled = !!svc;
  const initialType = svc ? svc.type : typeSelect.options[0]?.value;
  if (svc) typeSelect.value = svc.type;

  typeSelect.onchange = () => {
    applyServiceTypeDefaults(typeSelect.value, { autofillName: true });
    updateCredentialFieldsForType(typeSelect.value);
  };
  if (initialType) {
    // typeSelect is disabled while editing, so onchange (and thus autofill)
    // can never fire mid-edit - autofillName only ever applies when adding.
    applyServiceTypeDefaults(initialType, { autofillName: !svc });
    updateCredentialFieldsForType(initialType);
  }

  $("#service-modal").classList.remove("hidden");
}

function closeServiceModal() {
  $("#service-modal").classList.add("hidden");
}

// ---------- test connection ----------

function setConnStatus(which, cls, text, title) {
  const node = $(`#svc-${which}-status`);
  node.className = "conn-status" + (cls ? ` ${cls}` : "");
  node.textContent = text;
  node.title = title || "";
}

async function testServiceConnection() {
  const type = $("#svc-type").value;
  const localUrl = $("#svc-local-url").value.trim();
  const remoteUrl = $("#svc-remote-url").value.trim();
  if (!localUrl && !remoteUrl) {
    toast("Enter a Local or Remote address first", true);
    return;
  }
  if (localUrl) setConnStatus("local", "pending", "…");
  if (remoteUrl) setConnStatus("remote", "pending", "…");

  const apiKey = readSecretField($("#svc-key"), $("#svc-key-use-env"));
  let result;
  try {
    result = await api("/api/services/test-connection", {
      method: "POST",
      body: JSON.stringify({
        type,
        local_url: localUrl || null,
        remote_url: remoteUrl || null,
        api_key: apiKey.literal,
        api_key_env_var: apiKey.envVar,
      }),
    });
  } catch (e) {
    toast("Test failed: " + e.message, true);
    resetConnStatus();
    return;
  }

  if (result.local) setConnStatus("local", result.local.ok ? "ok" : "fail", result.local.ok ? "✓" : "✕", result.local.message);
  if (result.remote) setConnStatus("remote", result.remote.ok ? "ok" : "fail", result.remote.ok ? "✓" : "✕", result.remote.message);
}

// ---------- Plex sign-in ----------

let plexAuthTimer = null;

async function startPlexSignIn() {
  let data;
  try {
    data = await api("/api/plex-auth/start", { method: "POST" });
  } catch (e) {
    toast("Could not start Plex sign-in: " + e.message, true);
    return;
  }

  const popup = window.open(data.auth_url, "plex-auth", "width=480,height=700");
  if (!popup) {
    toast("Popup blocked - allow popups for this site and try again", true);
    return;
  }

  if (plexAuthTimer) clearInterval(plexAuthTimer);
  const deadline = Date.now() + 3 * 60 * 1000;
  plexAuthTimer = setInterval(async () => {
    if (Date.now() > deadline) {
      clearInterval(plexAuthTimer);
      plexAuthTimer = null;
      toast("Plex sign-in timed out", true);
      return;
    }
    let res;
    try {
      res = await api(`/api/plex-auth/poll?pin_id=${data.pin_id}`);
    } catch (e) {
      return; // transient failure - keep polling
    }
    if (res.token) {
      clearInterval(plexAuthTimer);
      plexAuthTimer = null;
      // A live sign-in always produces a literal token - drop out of
      // env-var mode if it was on, so the field actually shows/sends it.
      $("#svc-key-use-env").checked = false;
      syncSecretFieldAppearance($("#svc-key"), $("#svc-key-use-env"));
      $("#svc-key").value = res.token;
      $("#svc-key-hint").textContent = "(filled in from Plex sign-in)";
      if (!popup.closed) popup.close();
      toast("Signed in to Plex");
    }
  }, 2000);
}

async function submitServiceForm(ev) {
  ev.preventDefault();
  const id = $("#svc-id").value;
  const localUrl = $("#svc-local-url").value.trim();
  const remoteUrl = $("#svc-remote-url").value.trim();
  if (!localUrl && !remoteUrl) {
    toast("Set at least one of Local address / Remote address", true);
    return;
  }
  const payload = {
    name: $("#svc-name").value.trim(),
    check_both_targets: $("#svc-check-both").checked,
    username: $("#svc-username").value.trim(),
    enabled: $("#svc-enabled").checked,
    poll_interval_seconds: $("#svc-interval").value ? parseInt($("#svc-interval").value, 10) : null,
    notes: $("#svc-notes").value.trim() || null,
  };

  const apiKey = readSecretField($("#svc-key"), $("#svc-key-use-env"));
  if (apiKey.useEnv && !apiKey.envVar) {
    toast("Enter an environment variable name for the API key, or turn that toggle off", true);
    return;
  }
  payload.api_key_use_env = apiKey.useEnv;
  payload.api_key_env_var = apiKey.envVar;
  if (apiKey.literal) payload.api_key = apiKey.literal;

  const jellyfinAdminPassword = readSecretField($("#svc-jellyfin-admin-password"), $("#svc-jellyfin-admin-password-use-env"));
  if (jellyfinAdminPassword.useEnv && !jellyfinAdminPassword.envVar) {
    toast("Enter an environment variable name for the Jellyfin admin password, or turn that toggle off", true);
    return;
  }
  payload.jellyfin_admin_password_use_env = jellyfinAdminPassword.useEnv;
  payload.jellyfin_admin_password_env_var = jellyfinAdminPassword.envVar;
  if (jellyfinAdminPassword.literal) payload.jellyfin_admin_password = jellyfinAdminPassword.literal;

  try {
    if (id) {
      // PUT: an empty box means "clear this address" - null is indistinguishable
      // from "field omitted" in JSON, so use explicit clear flags instead.
      if (localUrl) payload.local_url = localUrl; else payload.clear_local_url = true;
      if (remoteUrl) payload.remote_url = remoteUrl; else payload.clear_remote_url = true;
      await api(`/api/services/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      payload.local_url = localUrl || null;
      payload.remote_url = remoteUrl || null;
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
  $("#chk-interval").value = check && check.interval_seconds ? check.interval_seconds : "";
  $("#chk-alert-level").value = check && check.config && check.config.alert_level === "warn" ? "warn" : "fail";

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

// These check types decide warn vs. fail themselves (from their own %
// thresholds) rather than just reporting a bare pass/fail - the generic
// Alert level toggle would only cause confusion here (or, worse, silently
// downgrade a real fail-level reading it wasn't meant to touch), so it's
// hidden for them and never included in their saved config.
const NO_ALERT_LEVEL_TYPES = new Set(["qbittorrent_disk_space", "deluge_disk_space", "arr_disk_space"]);

function renderDynamicFields(svc, checkType, existingConfig = {}) {
  $("#chk-alert-level-field").hidden = NO_ALERT_LEVEL_TYPES.has(checkType);

  const container = $("#chk-dynamic-fields");
  container.innerHTML = "";
  const meta = state.meta.check_types.find((ct) => ct.type === checkType);
  if (!meta) return;

  for (const f of meta.fields) {
    let value = existingConfig[f.key];
    if (f.key === "expected_status_codes" && Array.isArray(value)) value = value.join(",");
    if (value === undefined || value === null) value = f.default ?? "";

    const label = f.label.replace("{service}", svc.type);

    if (f.kind === "checkbox") {
      const input = el("input", { type: "checkbox", id: `chk-field-${f.key}` });
      input.checked = !!value;
      container.appendChild(
        el("div", { class: "field checkbox" }, [input, el("label", { for: `chk-field-${f.key}`, text: label })])
      );
      continue;
    }

    const fieldWrap = el("div", { class: "field" }, [el("label", { text: label })]);
    let input;
    if (f.kind === "select") {
      input = el("select", { id: `chk-field-${f.key}` });
      for (const opt of f.options) input.appendChild(el("option", { value: opt, text: opt }));
      input.value = value;
    } else if (f.kind === "number") {
      input = el("input", { type: "number", id: `chk-field-${f.key}`, value: value });
    } else if (f.kind === "password") {
      input = el("input", { type: "password", id: `chk-field-${f.key}`, value: value, autocomplete: "new-password" });
    } else {
      input = el("input", { type: "text", id: `chk-field-${f.key}`, value: value });
    }
    fieldWrap.appendChild(input);
    container.appendChild(fieldWrap);
  }

  if (checkType === "filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Note: 'Path in Checkarr container' must be bind-mounted into this container to be checked - it's almost never the same path the target app uses internally. For Radarr/Sonarr/Lidarr/Whisparr, prefer 'Filesystem path check via API' instead (below in this list) - it needs no volume mount at all." })
    );
  }
  if (checkType === "arr_filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Browses this path through the app's own API, exactly like its 'Add Root Folder' picker does - no volume mount needed on Checkarr. For a folder already configured as a root folder, the 'Root folders accessible' check already covers this; use this for any other path you want to watch independently." })
    );
  }
  if (checkType === "plex_remote_access") {
    container.appendChild(
      el("div", { class: "field hint", text: "Queries plex.tv and your server's public plex.direct address - both need outbound internet access from this container. Runs against your saved Plex API key, not the local/remote address above." })
    );
  }
  if (checkType === "plex_filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Browses this path through Plex's own API - no volume mount needed. Use \"Scan libraries\" above to add one of these per library automatically instead of typing paths by hand." })
    );
  }
  if (checkType === "jellyfin_filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Browses this path through Jellyfin's own API - no volume mount needed. Needs an administrator API key. Use \"Scan libraries\" above to add one of these per library automatically instead of typing paths by hand." })
    );
  }
  if (checkType === "qbittorrent_login" || checkType === "deluge_login") {
    container.appendChild(
      el("div", { class: "field hint", text: "Verifies the Username/Password (or just Password for Deluge) configured above actually logs in. Reports OK without checking anything if no credentials are set." })
    );
  }
  if (checkType === "qbittorrent_disk_space" || checkType === "deluge_disk_space") {
    container.appendChild(
      el("div", { class: "field hint", text: "The API only reports how much space is free, not the disk's total size, so there's nothing to compute a percentage against until you fill in 'Total disk size' - leave it blank to just see the free space reported with no threshold applied. No Alert level field here - Warn below/Fail below above already decide that." })
    );
  }
  if (checkType === "arr_disk_space") {
    container.appendChild(
      el("div", { class: "field hint", text: "Reads free AND total space directly from the app's own API, so unlike the torrent client disk-space checks there's nothing to fill in manually - Warn below/Fail below above work out of the box. Leave Path blank to check every disk the app reports on and flag whichever is lowest; set it to check just one. No Alert level field here - Warn below/Fail below above already decide that." })
    );
  }
  if (checkType === "rtorrent_rpc_status") {
    container.appendChild(
      el("div", { class: "field hint", text: "rTorrent has no web UI or API of its own - this speaks its XML-RPC interface directly, so the path varies by setup: plain /RPC2 for a bare rtorrent XML-RPC-over-HTTP bridge (this is the default for the \"rtorrent\" service type), or, when fronted by ruTorrent, something under its plugins directory - commonly /rutorrent/plugins/httprpc/action.php for the httprpc plugin (the default for the \"rutorrent\" service type), or [path to ruTorrent]/plugins/rpc/rpc.php for older setups. If this fails with a 404, that's almost always the fix. Uses the Username/Password above as HTTP Basic Auth, same as the Web UI check." })
    );
  }
  if (checkType === "ftp_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Connects to its own FTP host/port/credentials above, independent of this service's local/remote address - for a NAS or share exposed over FTP rather than one bind-mounted into this container. Same existence/population check as the filesystem path check, just reached over FTP." })
    );
  }
  if (checkType === "overseerr_tmdb_status") {
    container.appendChild(
      el("div", { class: "field hint", text: "There's no dedicated \"test TMDB\" endpoint, so this hits the same trending-movies call the app's own homepage makes on every load - a failure here usually means a TMDB-side or connectivity problem, not the app itself (that's what the Status check above is for)." })
    );
  }
  if (checkType === "ssl_certificate") {
    container.appendChild(
      el("div", { class: "field hint", text: "Added automatically the first time this service gets an https:// local or remote address - does a real, strict certificate check independent of any other check, which never verify certs themselves. Runs against whichever of local/remote is https; harmless against a plain http:// address (reports \"not applicable\")." })
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
    } else if (f.kind === "checkbox") {
      config[f.key] = input.checked;
    } else {
      config[f.key] = val;
    }
  }
  if (!NO_ALERT_LEVEL_TYPES.has(checkType)) config.alert_level = $("#chk-alert-level").value;

  const intervalVal = $("#chk-interval").value;
  const payload = {
    name: $("#chk-name").value.trim(),
    type: checkType,
    config,
    enabled: $("#chk-enabled").checked,
    interval_seconds: intervalVal ? parseInt(intervalVal, 10) : null,
  };

  try {
    if (checkId) {
      if (!intervalVal) payload.clear_interval = true;
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

// ---------- settings: push notifications ----------

async function loadChannels() {
  try {
    state.channels = await api("/api/notification-channels");
  } catch (e) {
    toast("Failed to load notification channels: " + e.message, true);
    return;
  }
  renderChannelsFromState();
}

function renderChannelsFromState() {
  const body = $("#channels-body");
  body.innerHTML = "";
  if (state.channels.length === 0) {
    body.appendChild(el("tr", {}, el("td", { colspan: "6", class: "empty-state", text: "No notification channels configured" })));
    return;
  }
  for (const ch of state.channels) {
    body.appendChild(renderChannelRow(ch));
  }
}

function renderChannelRow(ch) {
  const tr = el("tr", {});
  tr.appendChild(el("td", { "data-label": "Name", text: ch.name }));
  tr.appendChild(el("td", { "data-label": "Type", text: ch.type }));
  tr.appendChild(el("td", { "data-label": "Enabled" }, el("span", { class: `badge ${ch.enabled ? "ok" : "disabled"}`, text: ch.enabled ? "enabled" : "disabled" })));
  tr.appendChild(el("td", { "data-label": "Warn" }, el("span", { class: `dot ${ch.notify_on_warn ? "warn" : "disabled"}` })));
  tr.appendChild(el("td", { "data-label": "Fail" }, el("span", { class: `dot ${ch.notify_on_fail ? "fail" : "disabled"}` })));
  tr.appendChild(
    el("td", {}, el("div", { style: "display:flex; gap:6px;" }, [
      el("button", { class: "small", onclick: () => openChannelModal(ch) }, "Edit"),
      el("button", { class: "small danger", onclick: () => deleteChannel(ch) }, "Delete"),
    ]))
  );
  return tr;
}

function channelTypesFor() {
  return (state.meta.notification_channel_types || []);
}

function openChannelModal(ch = null) {
  $("#channel-modal-title").textContent = ch ? "Edit channel" : "Add channel";
  $("#chn-id").value = ch ? ch.id : "";
  $("#chn-name").value = ch ? ch.name : "";
  $("#chn-notify-warn").checked = ch ? ch.notify_on_warn : true;
  $("#chn-notify-fail").checked = ch ? ch.notify_on_fail : true;
  $("#chn-enabled").checked = ch ? ch.enabled : true;
  $("#chn-test-status").textContent = "";
  $("#chn-test-status").className = "conn-status";

  const typeSelect = $("#chn-type");
  typeSelect.innerHTML = "";
  for (const t of channelTypesFor()) {
    typeSelect.appendChild(el("option", { value: t.type, text: t.label }));
  }
  typeSelect.disabled = !!ch;
  typeSelect.value = ch ? ch.type : typeSelect.options[0]?.value;
  typeSelect.onchange = () => renderChannelDynamicFields(typeSelect.value, {}, false, null);
  renderChannelDynamicFields(typeSelect.value, ch ? ch.config : {}, ch ? ch.has_secret : false, ch ? ch.secret_env_var : null);

  $("#channel-modal").classList.remove("hidden");
}

function closeChannelModal() {
  $("#channel-modal").classList.add("hidden");
}

function renderChannelDynamicFields(channelType, existingConfig = {}, hasSecret = false, existingEnvVar = null) {
  const container = $("#chn-dynamic-fields");
  container.innerHTML = "";
  const meta = channelTypesFor().find((t) => t.type === channelType);
  if (!meta) return;

  for (const f of meta.fields) {
    let value = existingConfig[f.key];
    if (value === undefined || value === null) value = f.default ?? "";
    const label = f.label;

    if (f.kind === "checkbox") {
      const input = el("input", { type: "checkbox", id: `chn-field-${f.key}` });
      input.checked = !!value;
      container.appendChild(
        el("div", { class: "field checkbox" }, [input, el("label", { for: `chn-field-${f.key}`, text: label })])
      );
      continue;
    }

    const fieldWrap = el("div", { class: "field" }, [el("label", { text: label })]);
    let input;
    if (f.kind === "number") {
      input = el("input", { type: "number", id: `chn-field-${f.key}`, value: f.secret ? "" : value });
    } else if (f.kind === "password" || f.secret) {
      input = el("input", {
        type: "password",
        id: `chn-field-${f.key}`,
        placeholder: hasSecret && !existingEnvVar ? "(already set - leave blank to keep)" : "",
        autocomplete: "new-password",
      });
      fieldWrap.appendChild(input);
      const useEnvCheckbox = el("input", { type: "checkbox", id: `chn-field-${f.key}-use-env` });
      fieldWrap.appendChild(
        el("label", { class: "field checkbox", style: "margin-top:6px;" }, [useEnvCheckbox, el("span", { text: "Use environment variable" })])
      );
      initSecretField(input, useEnvCheckbox);
      setSecretFieldState(input, useEnvCheckbox, existingEnvVar);
      container.appendChild(fieldWrap);
      continue;
    } else {
      input = el("input", { type: "text", id: `chn-field-${f.key}`, value: value });
    }
    fieldWrap.appendChild(input);
    container.appendChild(fieldWrap);
  }
}

async function submitChannelForm(ev) {
  ev.preventDefault();
  const channelId = $("#chn-id").value;
  const channelType = $("#chn-type").value;
  const meta = channelTypesFor().find((t) => t.type === channelType);

  const config = {};
  let secretField = null;
  for (const f of meta.fields) {
    const input = $(`#chn-field-${f.key}`);
    if (!input) continue;
    if (f.secret) {
      // secret fields never go into config - see NotificationChannel.secret_encrypted/secret_env_var
      secretField = readSecretField(input, $(`#chn-field-${f.key}-use-env`));
      continue;
    }
    if (f.kind === "number") config[f.key] = input.value === "" ? null : Number(input.value);
    else if (f.kind === "checkbox") config[f.key] = input.checked;
    else config[f.key] = input.value;
  }
  if (secretField && secretField.useEnv && !secretField.envVar) {
    toast("Enter an environment variable name for the secret field, or turn that toggle off", true);
    return;
  }

  const payload = {
    name: $("#chn-name").value.trim(),
    config,
    notify_on_warn: $("#chn-notify-warn").checked,
    notify_on_fail: $("#chn-notify-fail").checked,
    enabled: $("#chn-enabled").checked,
  };
  if (secretField) {
    payload.secret_use_env = secretField.useEnv;
    payload.secret_env_var = secretField.envVar;
    if (secretField.literal) payload.secret = secretField.literal;
  }

  try {
    if (channelId) {
      await api(`/api/notification-channels/${channelId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      payload.type = channelType;
      await api("/api/notification-channels", { method: "POST", body: JSON.stringify(payload) });
    }
    toast("Channel saved");
    closeChannelModal();
    loadChannels();
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

async function deleteChannel(ch) {
  if (!confirm(`Delete notification channel "${ch.name}"?`)) return;
  try {
    await api(`/api/notification-channels/${ch.id}`, { method: "DELETE" });
    toast("Channel deleted");
    loadChannels();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

async function testChannelFromModal() {
  const channelId = $("#chn-id").value;
  if (!channelId) {
    toast("Save the channel before sending a test", true);
    return;
  }
  const statusEl = $("#chn-test-status");
  statusEl.className = "conn-status pending";
  statusEl.textContent = "…";
  let result;
  try {
    result = await api(`/api/notification-channels/${channelId}/test`, { method: "POST" });
  } catch (e) {
    statusEl.className = "conn-status fail";
    statusEl.textContent = "✕ " + e.message;
    return;
  }
  statusEl.className = "conn-status " + (result.ok ? "ok" : "fail");
  statusEl.textContent = (result.ok ? "✓ " : "✕ ") + result.message;
}

// ---------- settings: scheduled down time ----------

// Schedule times are entered/shown in the browser's local time and
// converted to/from UTC ISO strings at the API boundary - same convention
// as every other timestamp in this app (see relTime/fmtTime in common.js).
// parseTs (common.js) treats a 'Z'-less ISO string from the API as UTC;
// the Date it produces then reports back in local time via these getters.
function toLocalDateInput(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function toLocalTimeInput(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
function addDaysToDateInput(dateStr, n) {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + n);
  return toLocalDateInput(d);
}

function serviceNameById(id) {
  const s = state.services.find((sv) => sv.id === id);
  return s ? s.name : `#${id}`;
}

// ---- service groups ----

async function loadServiceGroups() {
  try {
    state.groups = await api("/api/service-groups");
  } catch (e) {
    toast("Failed to load service groups: " + e.message, true);
    return;
  }
  renderGroupsFromState();
  // A group's name/membership can appear on schedule cards (the "applies
  // to" checkboxes) - keep those in sync too, no extra fetch needed since
  // the schedules themselves haven't changed, just how a group renders.
  renderSchedulesFromState();
}

function renderGroupsFromState() {
  const body = $("#groups-body");
  body.innerHTML = "";
  for (const g of state.groups) {
    body.appendChild(renderGroupRow(g));
  }
}

function renderGroupRow(g) {
  const tr = el("tr", {});
  tr.appendChild(el("td", { "data-label": "Name", text: g.name }));
  const svcLabel = g.is_default
    ? `All services (${g.service_ids.length})`
    : g.service_ids.map(serviceNameById).join(", ") || "(none)";
  tr.appendChild(el("td", { "data-label": "Services", text: svcLabel }));
  const actions = g.is_default
    ? [el("span", { class: "text-dim", text: "built-in" })]
    : [
        el("button", { class: "small", onclick: () => openGroupModal(g) }, "Edit"),
        el("button", { class: "small danger", onclick: () => deleteGroup(g) }, "Delete"),
      ];
  tr.appendChild(el("td", {}, el("div", { style: "display:flex; gap:6px;" }, actions)));
  return tr;
}

function openGroupModal(g = null) {
  $("#group-modal-title").textContent = g ? "Edit group" : "Add group";
  $("#grp-id").value = g ? g.id : "";
  $("#grp-name").value = g ? g.name : "";

  const list = $("#grp-services-list");
  list.innerHTML = "";
  const memberIds = new Set(g ? g.service_ids : []);
  for (const svc of state.services) {
    const inputId = `grp-svc-${svc.id}`;
    const input = el("input", { type: "checkbox", id: inputId });
    input.checked = memberIds.has(svc.id);
    input.dataset.serviceId = svc.id;
    list.appendChild(el("div", { class: "field checkbox" }, [input, el("label", { for: inputId, text: svc.name })]));
  }
  $("#group-modal").classList.remove("hidden");
}

function closeGroupModal() {
  $("#group-modal").classList.add("hidden");
}

async function submitGroupForm(ev) {
  ev.preventDefault();
  const groupId = $("#grp-id").value;
  const serviceIds = $all("#grp-services-list input[type=checkbox]")
    .filter((i) => i.checked)
    .map((i) => Number(i.dataset.serviceId));
  const payload = { name: $("#grp-name").value.trim(), service_ids: serviceIds };

  try {
    if (groupId) {
      await api(`/api/service-groups/${groupId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/service-groups", { method: "POST", body: JSON.stringify(payload) });
    }
    toast("Group saved");
    closeGroupModal();
    loadServiceGroups();
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

async function deleteGroup(g) {
  if (!confirm(`Delete group "${g.name}"?`)) return;
  try {
    await api(`/api/service-groups/${g.id}`, { method: "DELETE" });
    toast("Group deleted");
    loadServiceGroups();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

// ---- schedules ----

function describeSchedule(s) {
  const start = new Date(parseTs(s.start_at));
  const end = new Date(parseTs(s.end_at));
  const timeFmt = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const dateFmt = (d) => d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  const timeRange = `${timeFmt(start)} – ${timeFmt(end)}`;

  let base;
  if (s.recurrence === "once") {
    base = `Once: ${dateFmt(start)} ${timeFmt(start)} → ${dateFmt(end)} ${timeFmt(end)}`;
  } else if (s.recurrence === "daily") {
    base = `Daily, ${timeRange}`;
  } else if (s.recurrence === "weekly") {
    base = `Weekly on ${start.toLocaleDateString([], { weekday: "long" })}, ${timeRange}`;
  } else if (s.recurrence === "monthly") {
    base = `Monthly on day ${start.getDate()}, ${timeRange}`;
  } else {
    base = `Yearly on ${start.toLocaleDateString([], { month: "long", day: "numeric" })}, ${timeRange}`;
  }
  if (s.recurrence !== "once" && s.repeat_until) {
    base += ` (until ${dateFmt(new Date(`${s.repeat_until}T00:00:00`))})`;
  }
  return base;
}

async function loadSchedules() {
  try {
    state.schedules = await api("/api/downtime-schedules");
  } catch (e) {
    toast("Failed to load schedules: " + e.message, true);
    return;
  }
  renderSchedulesFromState();
}

function renderSchedulesFromState() {
  const list = $("#schedules-list");
  if (!list) return;
  list.innerHTML = "";
  if (state.schedules.length === 0) {
    list.appendChild(el("div", { class: "empty-state", text: "No schedules configured" }));
    return;
  }
  for (const s of state.schedules) {
    list.appendChild(renderScheduleCard(s));
  }
}

function renderScheduleCard(s) {
  const card = el("div", { class: "schedule-card" });

  const badges = [
    s.suppress_warn ? el("span", { class: "badge warn", text: "Warn" }) : null,
    s.suppress_fail ? el("span", { class: "badge fail", text: "Fail" }) : null,
    !s.enabled ? el("span", { class: "badge disabled", text: "disabled" }) : null,
  ];
  card.appendChild(
    el("div", { class: "schedule-card-header" }, [
      el("div", {}, [
        el("strong", { text: s.name }),
        el("div", { class: "text-dim schedule-card-desc", text: describeSchedule(s) }),
      ]),
      el("div", { class: "schedule-card-actions" }, [
        ...badges,
        el("button", { class: "small", onclick: () => openScheduleModal(s) }, "Edit"),
        el("button", { class: "small danger", onclick: () => deleteSchedule(s) }, "Delete"),
      ]),
    ])
  );

  const groupsWrap = el("div", { class: "schedule-card-groups" }, [
    el("span", { class: "text-dim", text: "Applies to:" }),
  ]);
  for (const g of state.groups) {
    const inputId = `sch-${s.id}-grp-${g.id}`;
    const input = el("input", { type: "checkbox", id: inputId });
    input.checked = s.group_ids.includes(g.id);
    input.addEventListener("change", () => toggleScheduleGroup(s, g.id, input.checked));
    groupsWrap.appendChild(el("label", { class: "schedule-group-toggle", for: inputId }, [input, ` ${g.name}`]));
  }
  card.appendChild(groupsWrap);
  return card;
}

async function toggleScheduleGroup(schedule, groupId, checked) {
  const groupIds = new Set(schedule.group_ids);
  if (checked) groupIds.add(groupId); else groupIds.delete(groupId);
  schedule.group_ids = Array.from(groupIds);
  try {
    await api(`/api/downtime-schedules/${schedule.id}`, {
      method: "PUT",
      body: JSON.stringify({ group_ids: schedule.group_ids }),
    });
  } catch (e) {
    toast("Could not update schedule's groups: " + e.message, true);
  }
}

function updateScheduleFieldsForRecurrence(recurrence) {
  const isOnce = recurrence === "once";
  const isDaily = recurrence === "daily";
  $("#sch-end-date-field").hidden = !isOnce;
  $("#sch-repeat-until-field").hidden = isOnce;
  $("#sch-start-date-field").hidden = isDaily;

  const label = $("#sch-start-date-label");
  const hint = $("#sch-start-date-hint");
  if (recurrence === "weekly") {
    label.textContent = "Date";
    hint.textContent = "Repeats every week on this date's weekday.";
  } else if (recurrence === "monthly") {
    label.textContent = "Date";
    hint.textContent = "Repeats every month on this date's day of month.";
  } else if (recurrence === "yearly") {
    label.textContent = "Date";
    hint.textContent = "Repeats every year on this date's month and day.";
  } else {
    label.textContent = "Start date";
    hint.textContent = "";
  }
}

function openScheduleModal(s = null) {
  $("#schedule-modal-title").textContent = s ? "Edit schedule" : "Add schedule";
  $("#sch-id").value = s ? s.id : "";
  $("#sch-name").value = s ? s.name : "";

  const recurrence = s ? s.recurrence : "once";
  $("#sch-recurrence").value = recurrence;
  $("#sch-recurrence").disabled = !!s;
  $("#sch-recurrence").onchange = () => updateScheduleFieldsForRecurrence($("#sch-recurrence").value);

  const startLocal = s ? new Date(parseTs(s.start_at)) : new Date(Date.now() + 3600000);
  const endLocal = s ? new Date(parseTs(s.end_at)) : new Date(Date.now() + 2 * 3600000);
  $("#sch-start-date").value = toLocalDateInput(startLocal);
  $("#sch-start-time").value = toLocalTimeInput(startLocal);
  $("#sch-end-date").value = toLocalDateInput(endLocal);
  $("#sch-end-time").value = toLocalTimeInput(endLocal);
  $("#sch-repeat-until").value = s && s.repeat_until ? s.repeat_until : "";
  $("#sch-suppress-warn").checked = s ? s.suppress_warn : true;
  $("#sch-suppress-fail").checked = s ? s.suppress_fail : true;
  $("#sch-enabled").checked = s ? s.enabled : true;

  updateScheduleFieldsForRecurrence(recurrence);
  $("#schedule-modal").classList.remove("hidden");
}

function closeScheduleModal() {
  $("#schedule-modal").classList.add("hidden");
}

async function submitScheduleForm(ev) {
  ev.preventDefault();
  const scheduleId = $("#sch-id").value;
  const recurrence = $("#sch-recurrence").value;
  const startTime = $("#sch-start-time").value;
  const endTime = $("#sch-end-time").value;
  if (!startTime || !endTime) {
    toast("Set both a start and end time", true);
    return;
  }

  let startDateStr, endDateStr;
  if (recurrence === "once") {
    startDateStr = $("#sch-start-date").value;
    endDateStr = $("#sch-end-date").value;
    if (!startDateStr || !endDateStr) {
      toast("Set both a start and end date", true);
      return;
    }
  } else if (recurrence === "daily") {
    // No user-facing date for Daily - anchored to today; only the time
    // window (and whether it crosses midnight) actually matters.
    startDateStr = toLocalDateInput(new Date());
    endDateStr = endTime <= startTime ? addDaysToDateInput(startDateStr, 1) : startDateStr;
  } else {
    startDateStr = $("#sch-start-date").value;
    if (!startDateStr) {
      toast("Set a date", true);
      return;
    }
    endDateStr = endTime <= startTime ? addDaysToDateInput(startDateStr, 1) : startDateStr;
  }

  const startAt = new Date(`${startDateStr}T${startTime}:00`);
  const endAt = new Date(`${endDateStr}T${endTime}:00`);
  if (endAt <= startAt) {
    toast("End must be after start", true);
    return;
  }

  const suppressWarn = $("#sch-suppress-warn").checked;
  const suppressFail = $("#sch-suppress-fail").checked;
  if (!suppressWarn && !suppressFail) {
    toast("Suppress at least Warn or Fail", true);
    return;
  }

  const payload = {
    name: $("#sch-name").value.trim(),
    recurrence,
    start_at: startAt.toISOString(),
    end_at: endAt.toISOString(),
    suppress_warn: suppressWarn,
    suppress_fail: suppressFail,
    enabled: $("#sch-enabled").checked,
  };
  if (recurrence !== "once") {
    const repeatUntil = $("#sch-repeat-until").value;
    if (repeatUntil) payload.repeat_until = repeatUntil;
    else if (scheduleId) payload.clear_repeat_until = true;
  }

  try {
    if (scheduleId) {
      await api(`/api/downtime-schedules/${scheduleId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/downtime-schedules", { method: "POST", body: JSON.stringify(payload) });
    }
    toast("Schedule saved");
    closeScheduleModal();
    loadSchedules();
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

async function deleteSchedule(s) {
  if (!confirm(`Delete schedule "${s.name}"?`)) return;
  try {
    await api(`/api/downtime-schedules/${s.id}`, { method: "DELETE" });
    toast("Schedule deleted");
    loadSchedules();
  } catch (e) {
    toast("Delete failed: " + e.message, true);
  }
}

// ---------- settings: log & history pruning ----------

function renderPruneLastRun(lastPrunedAt) {
  $("#prune-last-run").textContent = "Last pruned: " + (lastPrunedAt ? relTime(lastPrunedAt) : "never");
}

async function loadLogPruningSettings() {
  let s;
  try {
    s = await api("/api/log-pruning-settings");
  } catch (e) {
    toast("Failed to load log & history pruning settings: " + e.message, true);
    return;
  }
  $("#prune-retention-days").value = s.retention_days;
  renderPruneLastRun(s.last_pruned_at);
}

async function submitPruningForm(ev) {
  ev.preventDefault();
  const retentionDays = parseInt($("#prune-retention-days").value, 10);
  if (!retentionDays || retentionDays < 1) {
    toast("Enter a valid number of days", true);
    return;
  }
  try {
    const s = await api("/api/log-pruning-settings", {
      method: "PUT",
      body: JSON.stringify({ retention_days: retentionDays }),
    });
    toast("Log & History Pruning settings saved");
    renderPruneLastRun(s.last_pruned_at);
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

// ---------- settings: dashboard settings ----------

// Compactness lives on the layout itself now (DashboardLayout.is_compact,
// toggled from the Dashboard tab's "Compact view" button) - "Restrict to
// compact layouts" here only narrows which layouts this dropdown offers,
// it doesn't force compact rendering on its own. Layouts are fetched once
// per tab visit and re-filtered client-side as the checkbox is toggled,
// no need to re-fetch for that.
let dashboardSettingsLayouts = [];
let dashboardSettingsPublicLayoutId = null;

function renderDashboardSettingsLayoutSelect() {
  const select = $("#dashboard-settings-layout");
  const requireCompact = $("#dashboard-settings-require-compact").checked;
  const options = requireCompact ? dashboardSettingsLayouts.filter((l) => l.is_compact) : dashboardSettingsLayouts;
  select.innerHTML = "";
  for (const l of options) {
    let text = l.name;
    if (l.is_compact) text += " (compact)";
    if (l.is_default) text += " (default)";
    select.appendChild(el("option", { value: l.id, text, selected: l.id === dashboardSettingsPublicLayoutId ? "selected" : null }));
  }
  if (!options.some((l) => l.id === dashboardSettingsPublicLayoutId)) select.value = "";
}

async function loadDashboardSettings() {
  let layouts, s;
  try {
    [layouts, s] = await Promise.all([api("/api/dashboard-layouts"), api("/api/dashboard-settings")]);
  } catch (e) {
    toast("Failed to load dashboard settings: " + e.message, true);
    return;
  }
  dashboardSettingsLayouts = layouts;
  dashboardSettingsPublicLayoutId = s.public_layout_id;
  $("#dashboard-settings-require-compact").checked = s.public_require_compact;
  renderDashboardSettingsLayoutSelect();
}

async function submitDashboardSettingsForm(ev) {
  ev.preventDefault();
  const layoutId = $("#dashboard-settings-layout").value;
  try {
    await api("/api/dashboard-settings", {
      method: "PUT",
      body: JSON.stringify({
        public_layout_id: layoutId ? parseInt(layoutId, 10) : null,
        clear_public_layout: !layoutId,
        public_require_compact: $("#dashboard-settings-require-compact").checked,
      }),
    });
    toast("Dashboard settings saved");
  } catch (e) {
    toast("Save failed: " + e.message, true);
  }
}

async function pruneNow() {
  if (!confirm("Delete check history older than the configured retention right now?")) return;
  const btn = $("#prune-now-btn");
  btn.disabled = true;
  try {
    const result = await api("/api/log-pruning-settings/prune-now", { method: "POST" });
    toast(`Pruned ${result.deleted} row(s)`);
    loadLogPruningSettings();
  } catch (e) {
    toast("Prune failed: " + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ---------- init ----------

async function init() {
  initTabs();
  await loadMeta();
  state.services = await api("/api/services");

  const buildInfo = $("#build-info");
  if (buildInfo && state.meta.build) {
    buildInfo.textContent = `v${state.meta.build.version} · built ${state.meta.build.build_date}`;
  }

  initUptimeRangeSelect();
  $("#add-service-btn").addEventListener("click", () => openServiceModal());
  $("#service-cancel").addEventListener("click", closeServiceModal);
  $("#service-form").addEventListener("submit", submitServiceForm);
  $("#svc-test-connection").addEventListener("click", testServiceConnection);
  $("#svc-plex-signin").addEventListener("click", startPlexSignIn);
  initSecretField($("#svc-key"), $("#svc-key-use-env"));
  initSecretField($("#svc-jellyfin-admin-password"), $("#svc-jellyfin-admin-password-use-env"));
  $("#check-cancel").addEventListener("click", closeCheckModal);
  $("#check-form").addEventListener("submit", submitCheckForm);
  $("#history-columns-btn").addEventListener("click", openColumnsModal);
  $("#columns-done").addEventListener("click", closeColumnsModal);
  $("#history-export-btn").addEventListener("click", exportHistoryCsv);
  $("#save-changes-btn").addEventListener("click", saveChanges);
  $("#discard-changes-btn").addEventListener("click", discardChanges);
  $("#save-changes-btn-bottom").addEventListener("click", saveChanges);
  $("#discard-changes-btn-bottom").addEventListener("click", discardChanges);
  $("#layout-select").addEventListener("change", onLayoutSelectChange);
  $("#layout-edit-btn").addEventListener("click", toggleLayoutEditMode);
  $("#layout-compact-btn").addEventListener("click", toggleLayoutCompact);
  $("#layout-new-btn").addEventListener("click", newLayoutFromCurrent);
  $("#layout-rename-btn").addEventListener("click", renameActiveLayout);
  $("#layout-delete-btn").addEventListener("click", deleteActiveLayout);
  $("#layout-add-card-select").addEventListener("change", (e) => {
    const id = Number(e.target.value);
    if (id) addCardToLayout(id);
  });
  $("#add-channel-btn").addEventListener("click", () => openChannelModal());
  $("#channel-cancel").addEventListener("click", closeChannelModal);
  $("#channel-form").addEventListener("submit", submitChannelForm);
  $("#chn-test").addEventListener("click", testChannelFromModal);
  $("#add-group-btn").addEventListener("click", () => openGroupModal());
  $("#group-cancel").addEventListener("click", closeGroupModal);
  $("#group-form").addEventListener("submit", submitGroupForm);
  $("#add-schedule-btn").addEventListener("click", () => openScheduleModal());
  $("#schedule-cancel").addEventListener("click", closeScheduleModal);
  $("#schedule-form").addEventListener("submit", submitScheduleForm);
  $("#pruning-form").addEventListener("submit", submitPruningForm);
  $("#prune-now-btn").addEventListener("click", pruneNow);
  $("#dashboard-settings-form").addEventListener("submit", submitDashboardSettingsForm);
  $("#dashboard-settings-require-compact").addEventListener("change", renderDashboardSettingsLayoutSelect);

  let resizeTimer = null;
  let lastViewportWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    // innerWidth only, not innerHeight - on mobile, scrolling shows/hides
    // the browser's address bar, which changes innerHeight and fires this
    // same event on every scroll. Reacting to that rebuilds the whole grid
    // mid-scroll, which is what was causing the page to jump back to the
    // top - nothing about the available column width actually changed.
    if (window.innerWidth === lastViewportWidth) return;
    lastViewportWidth = window.innerWidth;
    if (state.tab !== "dashboard" || layoutEditMode) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(loadDashboardAdmin, 200);
  });

  window.addEventListener("beforeunload", (e) => {
    if (pendingChangeCount() > 0) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  document.body.classList.add("wide-main"); // dashboard is the default active tab
  updateHeaderControlsVisibility("dashboard");
  loadDashboardAdmin();
  setInterval(() => { if (state.tab === "dashboard" && !layoutEditMode) loadDashboardAdmin(); }, 30000);
  setInterval(() => { if (state.tab === "notifications") loadNotifications(); }, 30000);
}

document.addEventListener("DOMContentLoaded", init);
