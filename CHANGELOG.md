# Changelog

Every release of Checkarr, newest first. The version shown in the app's
header comes from the `VERSION` file.

## 0.34.0 - 2026-10-23

### Added
- **Setup guide on first boot.** A step-by-step guide that opens the first
  time Checkarr starts:
  1. **Encryption key** (only while `HC_APP_SECRET_KEY` isn't set): choose
     between keeping the `/config/secret.key` file (with an "are you sure?"
     warning) and setting `HC_APP_SECRET_KEY` and restarting. That option
     generates a key in your browser and gives the steps for Unraid, Docker
     Compose and `docker run`. After the restart the guide carries on from
     the next step.
  2. **First service**: what each field means, then the usual Add service
     dialog, and a list of what you've added.
  3. **Where things are**: what every tab and Settings page does.
  4. **Done**: a warning if the admin app has no login, and a note about the
     read-only public dashboard.

  Installs that already have services never see it. Settings >
  Customizations > Show setup guide opens it again.
- **Missing files check** (`arr_missing_files`) for Radarr, Sonarr, Lidarr
  and Whisparr. Watches the app's Wanted > Missing list and warns once
  something has been on it for 30 minutes - long enough for a normal
  download and import to finish.
  - Both the wait and the alert level (Warn or Fail) can be changed per
    check.
  - Only monitored items that have actually aired or released count.
  - Whatever is already missing the first time it runs is recorded and not
    alerted on, unless "Also alert on items that were already missing" is
    ticked.
  - Added automatically to new services and, on upgrade, to existing ones.
  - Older Radarr versions without a Wanted page fall back to the movie list.
- **Compact cards open up to the full card.** On desktop, clicking a compact
  card shows the full card in a centered box over a darkened page (✕,
  Escape or a click outside closes it). On a Mobile-Compact layout, tapping a
  card expands it in place, pushing the cards below it down; tap again to
  collapse it. Works on the public dashboard too, and is off while editing a
  layout.
- **`PUID` / `PGID` / `UMASK` support in the container.** Set `PUID`/`PGID` to
  run as an ordinary user instead of root; the container takes ownership of
  `/config` for them on start. The Unraid template already sets `99`/`100`.
- **"Verify the server's TLS certificate"** option on email channels (on by
  default).

### Security
- **cryptography updated from 43.0.3 to 50.0.2.** The old `~=43.0` pin was
  holding it on a version with six known vulnerabilities (CVE-2024-12797,
  CVE-2026-26007, CVE-2026-34073, CVE-2026-69248, CVE-2026-69249 and
  GHSA-537c-gmf6-5ccf - bundled OpenSSL flaws, certificate verification
  bypasses and a denial of service).
- **Patched minimum versions for every dependency.** A rebuild can no longer
  fall back to an older version with a known vulnerability. `pip-audit`
  reports nothing.
- **The public dashboard no longer exposes service details.** Its
  `/api/status` was returning each service's full admin record - internal
  addresses, username, notes, environment variable names and every check's
  settings, including the FTP check's password. It now gets only name, type,
  icon and results.
- **The FTP check's password is encrypted.** It's stored like every other
  secret and never sent back by the API once saved (leave the field blank to
  keep it). Existing plain-text passwords are encrypted on startup.
- **Cross-site requests can't change anything.** The admin app now refuses
  any change made by a browser from another site, so a web page you visit
  can't silently prune history, send test notifications or upload files
  through your browser. Scripts and curl are unaffected.
- **Email alerts verify the SMTP server's certificate.** Before, the SMTP
  password could be intercepted by anyone able to pose as the server.
- **The key file is private from the moment it's created.** A new
  `secret.key` is now created readable by its owner only, instead of being
  readable for an instant before its permissions were tightened.
- **Uploaded icons can't run scripts.** They're served with a locked-down
  Content-Security-Policy, so an uploaded SVG opened directly can't run
  scripts. Every response also gets `X-Content-Type-Options: nosniff` and
  `Referrer-Policy: same-origin`.
- **The container image picks up current security fixes.** It installs
  Debian security updates and the latest pip at build time.

### Fixed
- Centered dialogs taller than the window no longer have their top cut off
  out of reach.
- The History event dialog was stuck at 520px wide instead of 760px.
- An uptime strip no longer changes height when its bars arrive.

### Upgrading
- On Unraid (or anywhere `PUID`/`PGID` are set) Checkarr now runs as that
  user, and the first start changes the owner of `/config` to match. If the
  container can't drop privileges it carries on as root, as before.
- An email channel pointed at a local relay with a self-signed certificate
  will fail to send until "Verify the server's TLS certificate" is turned
  off on that channel.
- Radarr, Sonarr, Lidarr and Whisparr services gain the Missing files check
  automatically. Disable it on a service's Checks panel if you don't want it.

## 0.33.0 - 2026-10-19

### Added
- **History: "All Services" pill.** Always the first pill. Turns every
  service on at once, and clicking it again restores the selection you had
  before.
- **History remembers your selection.** Which services are selected is saved
  in a cookie per browser.
- **History: event details.** On desktop, clicking a row shows every field
  and the full message in a centered dialog.
- **Settings sections in a dropdown on mobile.** The row of section buttons
  becomes a dropdown on phones, instead of making the page scroll sideways.

### Changed
- **History columns size themselves.** They fit their content every time the
  filters change - Time, Status and Response at their natural width, Message
  taking what's left - instead of splitting the width evenly.

### Fixed
- The dashboard no longer jumps back to the top on its 30-second refresh.
- Clicking a tab in the icon picker no longer blanks every Settings panel.
- Clicking several History filters quickly no longer mixes in rows from an
  earlier filter.

## Earlier releases

- **0.32.2** (2026-09-19) - Health check (`arr_health`) reports the actual health message, not just a count.
- **0.32.1** (2026-09-19) - Services page: Scan libraries and the checks box stay hidden until a service is expanded; narrower action column.
- **0.32.0** (2026-09-19) - Scan libraries moved into the Checks panel, saved-secret dots, unsaved-change tracking in Edit service.
- **0.31.0** (2026-09-19) - Longer uptime ranges, separate pruning schedule, default retention raised to 30 days.
- **0.30.3** (2026-09-19) - Fix the dashboard uptime strip cutting off older data for busy services. Documentation reorganised into `docs/`, Unraid template added.
- **0.30.2** (2026-09-17) - Docker deployment docs expanded with editing and Unraid build instructions.
- **0.30.1** (2026-09-15) - Code audit, ARCHITECTURE.md.
- **0.30.0** (2026-09-15) - "Alert after N consecutive" threshold, public port theme override, edit-mode-only theme picker, lighter White-theme warn color.
- **0.29.0** (2026-09-14) - Fix layout themes not reaching background and text, drop the redundant default-theme option, Services page polish.
- **0.28.0** (2026-09-14) - UI themes (Settings > Customizations, per-layout override); Checks toggle moved inline on Services.
- **0.27.1** (2026-09-14) - Fix the Bars input, recalibrate the per-card bar-count limits.
- **0.27.0** (2026-09-14) - Per-card uptime bar count with a width-based limit, replacing the global one.
- **0.26.0** (2026-09-14) - Configurable uptime bars per card (1-200).
- **0.25.0** (2026-09-13) - External port open check.
- **0.24.0** (2026-09-13) - iPlayarr and iPlayer-Arr service types.
- **0.23.0** (2026-09-13) - Discord, Slack, Telegram, Pushbullet, Pushover, webhook and browser notification channels.
- **0.22.2** (2026-09-13) - Drop the redundant "(default)" label in Dashboard Settings, expanded README.
- **0.22.1** (2026-09-12) - Record "In SDT" permanently at poll time.
- **0.22.0** (2026-09-12) - History shows when an event was suppressed by Scheduled Down Time.
- **0.21.1** (2026-09-12) - Separate Desktop and Mobile pins for the public dashboard.
- **0.21.0** (2026-09-12) - History severity filter and compact mobile rows, custom service icons.
- **0.20.0** (2026-09-12) - Fix the mobile dashboard scrolling sideways; layouts split into Desktop, Desktop-Compact, Mobile and Mobile-Compact.
- **0.19.1** (2026-09-12) - More Notifications empty-state quips.
- **0.19.0** (2026-09-11) - Fix the Instant SDT duration input, Immich API key guidance, Dispatcharr, Sportarr and Cleanuparr service types.
- **0.18.0** (2026-09-11) - Instant SDT, "just the last poll" history, compact edit-mode fix, Immich support, notification quips.
- **0.17.1** (2026-09-11) - Separate compact layouts, leaner compact cards, categorised service picker, rTorrent/ruTorrent split, History pill filter.
- **0.17.0** (2026-09-11) - History fixes, batched alerts, self-monitoring, Dashboard Settings, branding, docs split; compact view became a per-layout feature.
- **0.16.0** (2026-09-11) - Secrets from environment variables.
- **0.15.0** (2026-09-11) - Interval-based log pruning, add/remove dashboard cards, compact card header, email SMTPS fix.
- **0.14.1** (2026-09-11) - Fix public History pagination, duplicate SSL checks and Jellyfin admin 401s.
- **0.14.0** (2026-09-11) - History pagination, columns and CSV export; log pruning schedule; Overseerr renamed to Seerr.
- **0.13.1** (2026-09-11) - Fix the checks toggle and drag handle rendering, one History range picker.
- **0.13.0** (2026-09-11) - Scheduled Down Time, auto-scaled disk-space units.
- **0.12.0** (2026-09-11) - Check reordering, SSL check redesign, push notifications, mobile and CSS fixes.
- **0.11.0** (2026-09-11) - Name fade only when clipped, mobile height resize, uptime range picker.
- **0.10.1** (2026-09-11) - Fix a mobile scrolling bug, mobile card editor.
- **0.10.0** (2026-09-11) - Responsive layout for phones.
- **0.9.0** (2026-09-10) - `arr_disk_space` check, Overseerr and Jellyseerr support.
- **0.8.2** (2026-09-10) - Jellyfin login diagnostics, disk-space UI cleanup, Fail/Warn wording.
- **0.8.1** (2026-09-10) - Edit-mode fixes, Jellyfin admin login, Settings table styling.
- **0.8.0** (2026-09-10) - Torrent client disk space, rTorrent XML-RPC and FTP checks.
- **0.7.0** (2026-09-10) - Dashboard edit mode, responsive layouts.
- **0.6.0** (2026-09-10) - Freely movable dashboard cards, wider grid.
- **0.5.0** (2026-09-10) - Resizable, saveable dashboard layouts; renamed to Checkarr.
- **0.4.3** (2026-09-10) - Table layout for checks, Alert level on every check, staged deletion, collapsible services.
- **0.4.2** (2026-09-10) - Quick-edit controls on Settings checks with staged Save/Discard.
- **0.4.1** (2026-09-10) - Test connection, Plex sign-in, torrent client auth, library scanning.
- **Before 0.4.1** (2026-09-10) - First versions: local and remote addresses, split filesystem check paths, Plex remote access, `/config` data directory, the public dashboard port, build info, real service icons, the root-folder check and `arr_filesystem_path`, and local-only checks by default when a remote address is set.
