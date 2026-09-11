// Restricted public dashboard: read-only rendering only, via common.js.
// No CRUD, no API keys, no settings - just whichever of dashboard/history/
// notifications this page is.

async function init() {
  await loadMeta();

  if (window.PUBLIC_PAGE === "dashboard") {
    initUptimeRangeSelect();
    // Compact is read straight off the pinned layout itself
    // (DashboardLayout.is_compact, see loadDashboard in common.js) - no
    // separate settings fetch needed here.
    loadDashboard(); // interactive/editable default to falsy - no Run now, no drag/resize
    setInterval(loadDashboard, 30000);
    let resizeTimer = null;
    let lastViewportWidth = window.innerWidth;
    window.addEventListener("resize", () => {
      // innerWidth only - see the matching comment in app.js's resize
      // listener for why (mobile address-bar show/hide on scroll).
      if (window.innerWidth === lastViewportWidth) return;
      lastViewportWidth = window.innerWidth;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(loadDashboard, 200);
    });
  } else if (window.PUBLIC_PAGE === "notifications") {
    loadNotifications();
    setInterval(loadNotifications, 30000);
  } else if (window.PUBLIC_PAGE === "history") {
    initUptimeRangeSelect();
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
