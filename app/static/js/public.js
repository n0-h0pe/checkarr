// Restricted public dashboard: read-only rendering only, via common.js.
// No CRUD, no API keys, no settings - just whichever of dashboard/history/
// notifications this page is.

async function init() {
  await loadMeta();

  if (window.PUBLIC_PAGE === "dashboard") {
    loadDashboard(); // interactive defaults to falsy - no Run now / edit affordances
    setInterval(loadDashboard, 30000);
  } else if (window.PUBLIC_PAGE === "notifications") {
    const showResolvedBox = $("#show-resolved");
    if (showResolvedBox) showResolvedBox.addEventListener("change", loadNotifications);
    loadNotifications();
    setInterval(loadNotifications, 30000);
  } else if (window.PUBLIC_PAGE === "history") {
    $("#history-service").addEventListener("change", loadHistoryTab);
    $("#history-hours").addEventListener("change", loadHistoryTab);
    loadHistoryTab();
    setInterval(loadHistoryTab, 30000);
  }
}

document.addEventListener("DOMContentLoaded", init);
