// Admin app: full CRUD over services/checks, on top of the read-only
// rendering shared with the public dashboard via common.js.

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
  if (tab === "dashboard") loadDashboardAdmin();
  if (tab === "notifications") loadNotifications();
  if (tab === "history") loadHistoryTab();
  if (tab === "settings") loadSettings();
}

function loadDashboardAdmin() {
  return loadDashboard({
    interactive: true,
    onRunNow: runNow,
    onHistory: (id) => { switchTab("history"); $("#history-service").value = id; loadHistoryTab(); },
  });
}

async function runNow(serviceId) {
  try {
    await api(`/api/services/${serviceId}/run-now`, { method: "POST" });
    toast("Checks run");
  } catch (e) {
    toast("Run failed: " + e.message, true);
  }
  if (state.tab === "dashboard") loadDashboardAdmin();
  if (state.tab === "settings") loadSettings();
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
  tr.appendChild(el("td", { text: svc.name }));
  tr.appendChild(el("td", {}, [typeIcon(svc.type), " " + svc.type]));
  tr.appendChild(el("td", { text: svc.local_url || "-" }));
  tr.appendChild(el("td", { text: svc.remote_url || "-" }));
  tr.appendChild(el("td", { text: svc.poll_interval_seconds ? `${svc.poll_interval_seconds}s` : "default" }));
  tr.appendChild(el("td", {}, el("span", { class: `badge ${svc.enabled ? "ok" : "disabled"}`, text: svc.enabled ? "enabled" : "disabled" })));

  const actions = el("div", { style: "display:flex; gap:6px;" }, [
    el("button", { class: "small", onclick: () => openServiceModal(svc) }, "Edit"),
    el("button", { class: "small danger", onclick: () => deleteService(svc) }, "Delete"),
  ]);
  tr.appendChild(el("td", {}, actions));

  const detailRow = el("tr", {}, el("td", { colspan: "7" }, renderChecksPanel(svc)));

  const wrapper = document.createDocumentFragment();
  wrapper.appendChild(tr);
  wrapper.appendChild(detailRow);
  return wrapper;
}

function renderChecksPanel(svc) {
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
  panel.appendChild(
    el("div", { style: "display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;" }, [
      el("strong", { text: "Checks" }),
      el("div", { style: "display:flex; gap:6px;" }, actions),
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
          c.interval_seconds ? el("span", { class: "text-dim", text: ` (every ${c.interval_seconds}s)` }) : null,
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

const CREDENTIAL_MODES = {
  plex: { keyLabel: "X-Plex-Token", showUsername: false, showPlexSignin: true },
  qbittorrent: { keyLabel: "Password", showUsername: true, showPlexSignin: false },
  rtorrent: { keyLabel: "Password", showUsername: true, showPlexSignin: false },
  deluge: { keyLabel: "Password", showUsername: true, showPlexSignin: false },
};

function credentialModeFor(type) {
  return CREDENTIAL_MODES[type] || { keyLabel: "API key", showUsername: false, showPlexSignin: false };
}

function updateCredentialFieldsForType(type) {
  const mode = credentialModeFor(type);
  $("#svc-key-label").childNodes[0].textContent = mode.keyLabel + " ";
  $("#svc-username-field").hidden = !mode.showUsername;
  $("#svc-plex-signin").hidden = !mode.showPlexSignin;
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
  $("#svc-interval").value = svc && svc.poll_interval_seconds ? svc.poll_interval_seconds : "";
  $("#svc-verify-ssl").checked = svc ? svc.verify_ssl : true;
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
    verify_ssl: $("#svc-verify-ssl").checked,
    enabled: $("#svc-enabled").checked,
    poll_interval_seconds: $("#svc-interval").value ? parseInt($("#svc-interval").value, 10) : null,
    notes: $("#svc-notes").value.trim() || null,
  };
  const key = $("#svc-key").value;
  if (key) payload.api_key = key;

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

    const label = f.label.replace("{service}", svc.type);
    const fieldWrap = el("div", { class: "field" }, [el("label", { text: label })]);
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
      el("div", { class: "field hint", text: "Note: 'Path in HealthChecker container' must be bind-mounted into this container to be checked - it's almost never the same path the target app uses internally. For Radarr/Sonarr/Lidarr/Whisparr, prefer 'Filesystem path check via API' instead (below in this list) - it needs no volume mount at all." })
    );
  }
  if (checkType === "arr_filesystem_path") {
    container.appendChild(
      el("div", { class: "field hint", text: "Browses this path through the app's own API, exactly like its 'Add Root Folder' picker does - no volume mount needed on HealthChecker. For a folder already configured as a root folder, the 'Root folders accessible' check already covers this; use this for any other path you want to watch independently." })
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

// ---------- init ----------

async function init() {
  initTabs();
  await loadMeta();
  state.services = await api("/api/services");

  const buildInfo = $("#build-info");
  if (buildInfo && state.meta.build) {
    buildInfo.textContent = `v${state.meta.build.version} · built ${state.meta.build.build_date}`;
  }

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

  loadDashboardAdmin();
  setInterval(() => { if (state.tab === "dashboard") loadDashboardAdmin(); }, 30000);
  setInterval(() => { if (state.tab === "notifications") loadNotifications(); }, 30000);
}

document.addEventListener("DOMContentLoaded", init);
