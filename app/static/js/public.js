// Restricted public dashboard: read-only rendering only, via common.js.
// No CRUD, no API keys, no settings - just whichever of dashboard/history/
// notifications this page is.

// Compact mode (Settings > Dashboard Settings, admin-only) hides each
// card's individual check rows on the public dashboard - re-read on every
// load rather than cached once, so a toggle in admin takes effect on this
// page's next 30s refresh without needing a reload.
async function loadPublicDashboard() {
  let compact = false;
  try {
    const s = await api("/api/dashboard-settings");
    compact = !!s.public_compact;
  } catch (_) {
    // fall through with compact=false - a stale/unreachable settings
    // fetch shouldn't blank the dashboard itself.
  }
  await loadDashboard({ compact }); // interactive/editable default to falsy - no Run now, no drag/resize
}

async function init() {
  await loadMeta();

  if (window.PUBLIC_PAGE === "dashboard") {
    initUptimeRangeSelect();
    loadPublicDashboard();
    setInterval(loadPublicDashboard, 30000);
    let resizeTimer = null;
    let lastViewportWidth = window.innerWidth;
    window.addEventListener("resize", () => {
      // innerWidth only - see the matching comment in app.js's resize
      // listener for why (mobile address-bar show/hide on scroll).
      if (window.innerWidth === lastViewportWidth) return;
      lastViewportWidth = window.innerWidth;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(loadPublicDashboard, 200);
    });
  } else if (window.PUBLIC_PAGE === "notifications") {
    loadNotifications();
    setInterval(loadNotifications, 30000);
  } else if (window.PUBLIC_PAGE === "history") {
    initUptimeRangeSelect();
    $("#history-services-btn").addEventListener("click", openHistoryServicesModal);
    $("#history-services-done").addEventListener("click", closeHistoryServicesModal);
    $("#history-columns-btn").addEventListener("click", openColumnsModal);
    $("#columns-done").addEventListener("click", closeColumnsModal);
    $("#history-export-btn").addEventListener("click", exportHistoryCsv);
    loadHistoryTab();
    // No periodic auto-refresh here (unlike the dashboard/notifications
    // above) - it would silently reset the user back to page 1 every 30s
    // while they're scrolled several pages deep into infinite-scroll
    // history. Changing the service or range still reloads, same as admin.
  }
}

document.addEventListener("DOMContentLoaded", init);
