// Admin app: full CRUD over services/checks, on top of the read-only
// rendering shared with the public dashboard via common.js.

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

async function loadDashboardAdmin() {
  await loadDashboard({
    interactive: true,
    editable: layoutEditMode,
    onRunNow: runNow,
    onHistory: (id) => { switchTab("history"); $("#history-service").value = id; loadHistoryTab(); },
    onLayoutChange: persistCardLayout,
  });
  loadLayoutList();
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
  const select = $("#layout-select");
  select.innerHTML = "";
  for (const l of layouts) {
    select.appendChild(el("option", { value: l.id, text: l.name, selected: l.is_active ? "selected" : null }));
  }
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
  try {
    state.activeLayout = await api("/api/dashboard-layouts", { method: "POST", body: JSON.stringify({ name, sizes, columns }) });
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
  const toggleBtn = el("button", { class: "small expand-arrow" }, `${isCollapsed ? "▸" : "▾"} Checks (${svc.checks.length})`);
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
    toggleBtn.textContent = `${collapse ? "▸" : "▾"} Checks (${svc.checks.length})`;
    if (collapse) collapsedServiceIds.add(svc.id); else collapsedServiceIds.delete(svc.id);
    saveCollapsedServiceIds();
  });
  panel.appendChild(grid);
  return panel;
}

function appendCheckGridRow(grid, svc, c) {
  const pendingDelete = pendingCheckDeletions.has(c.id);
  const rowClass = pendingDelete ? "row-pending-delete" : "";

  const handle = el("div", { class: "drag-handle", "data-check-id": c.id, title: pendingDelete ? null : "Drag to reorder" }, pendingDelete ? "" : "⠷");
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
  $("#svc-key").value = "";
  $("#svc-key-hint").textContent = svc && svc.has_api_key ? "(already set - leave blank to keep)" : "";
  $("#svc-jellyfin-admin-password").value = "";
  $("#svc-jellyfin-admin-password-hint").textContent =
    svc && svc.has_jellyfin_admin_password ? "(already set - leave blank to keep)" : "(optional, paired with the Admin username above)";
  $("#svc-interval").value = svc && svc.poll_interval_seconds ? svc.poll_interval_seconds : "";
  $("#svc-enabled").checked = svc ? svc.enabled : true;
  $("#svc-notes").value = svc && svc.notes ? svc.notes : "";
  resetConnStatus();

  const typeSelect = $("#svc-type");
  typeSelect.innerHTML = "";
  for (const t of state.meta.service_types) {
    typeSelect.appendChild(el("option", { value: t, text: t }));
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

  let result;
  try {
    result = await api("/api/services/test-connection", {
      method: "POST",
      body: JSON.stringify({
        type,
        local_url: localUrl || null,
        remote_url: remoteUrl || null,
        api_key: $("#svc-key").value || null,
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
  const key = $("#svc-key").value;
  if (key) payload.api_key = key;
  const jellyfinAdminPassword = $("#svc-jellyfin-admin-password").value;
  if (jellyfinAdminPassword) payload.jellyfin_admin_password = jellyfinAdminPassword;

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
      el("div", { class: "field hint", text: "rTorrent has no web UI or API of its own - this speaks its XML-RPC interface directly, so the path varies by setup: plain /RPC2 for a bare XML-RPC-over-HTTP bridge, or something under ruTorrent's plugins directory when fronted by it - commonly /rutorrent/plugins/httprpc/action.php for the httprpc plugin, or [path to ruTorrent]/plugins/rpc/rpc.php for older setups. If this fails with a 404, that's almost always the fix. Uses the Username/Password above as HTTP Basic Auth, same as the Web UI check." })
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
  typeSelect.onchange = () => renderChannelDynamicFields(typeSelect.value, {}, false);
  renderChannelDynamicFields(typeSelect.value, ch ? ch.config : {}, ch ? ch.has_secret : false);

  $("#channel-modal").classList.remove("hidden");
}

function closeChannelModal() {
  $("#channel-modal").classList.add("hidden");
}

function renderChannelDynamicFields(channelType, existingConfig = {}, hasSecret = false) {
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
        placeholder: hasSecret ? "(already set - leave blank to keep)" : "",
        autocomplete: "new-password",
      });
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
  let secret = null;
  for (const f of meta.fields) {
    const input = $(`#chn-field-${f.key}`);
    if (!input) continue;
    if (f.secret) {
      if (input.value) secret = input.value;
      continue; // secret fields never go into config - see NotificationChannel.secret_encrypted
    }
    if (f.kind === "number") config[f.key] = input.value === "" ? null : Number(input.value);
    else if (f.kind === "checkbox") config[f.key] = input.checked;
    else config[f.key] = input.value;
  }

  const payload = {
    name: $("#chn-name").value.trim(),
    config,
    notify_on_warn: $("#chn-notify-warn").checked,
    notify_on_fail: $("#chn-notify-fail").checked,
    enabled: $("#chn-enabled").checked,
  };
  if (secret) payload.secret = secret;

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
  $("#check-cancel").addEventListener("click", closeCheckModal);
  $("#check-form").addEventListener("submit", submitCheckForm);
  $("#show-resolved").addEventListener("change", loadNotifications);
  $("#history-service").addEventListener("change", loadHistoryTab);
  $("#history-hours").addEventListener("change", loadHistoryTab);
  $("#save-changes-btn").addEventListener("click", saveChanges);
  $("#discard-changes-btn").addEventListener("click", discardChanges);
  $("#save-changes-btn-bottom").addEventListener("click", saveChanges);
  $("#discard-changes-btn-bottom").addEventListener("click", discardChanges);
  $("#layout-select").addEventListener("change", onLayoutSelectChange);
  $("#layout-edit-btn").addEventListener("click", toggleLayoutEditMode);
  $("#layout-new-btn").addEventListener("click", newLayoutFromCurrent);
  $("#layout-rename-btn").addEventListener("click", renameActiveLayout);
  $("#layout-delete-btn").addEventListener("click", deleteActiveLayout);
  $("#add-channel-btn").addEventListener("click", () => openChannelModal());
  $("#channel-cancel").addEventListener("click", closeChannelModal);
  $("#channel-form").addEventListener("submit", submitChannelForm);
  $("#chn-test").addEventListener("click", testChannelFromModal);

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
