# Media Estate HealthChecker

A self-hosted dashboard that periodically polls your media stack (Radarr,
Sonarr, Lidarr, Whisparr, Chaptarr, Prowlarr, Plex, Jellyfin, qBittorrent,
Deluge, rTorrent, or any other HTTP service) and shows one consolidated view
of what's healthy, what's degraded, and why.

## Features

- Polls each service on its own schedule (default every 5 minutes, configurable globally, per-service, and per-check).
- Local and remote addresses: give a service either address, or both. With both set, the Web UI check runs against each (so you know if the reverse-proxied path breaks even when the app itself is fine on the LAN); every other check runs against local only, to avoid needlessly doubling up API-heavy checks - opt into running everything against both with a per-service toggle. See "Adding a service" below.
- Built-in checks: HTTP 200 web UI reachability, *arr-family API status, root-folder accessibility **and population** (drive/mount detection - see below), each app's own system health feed, and for Plex, Remote Access status.
- Fully configurable: add your own checks per service (custom HTTP path/status/keyword checks, or a filesystem existence check).
- Consolidates the *arr apps' own "System > Status" health notifications (indexer down, missing files, low disk space, etc.) into one Notifications tab, with automatic resolve-tracking.
- A second, restricted read-only dashboard on its own port - no settings, no API keys, nothing mutable - safe to expose externally. See "Public dashboard" below.
- Real app icons (not emoji), and a version/build date in the header so you can tell at a glance whether you're running the image you think you are.
- "Test connection" button in the Add/Edit service form - a quick green ✓/red ✕ per address before you even save, plus autofilled Name and a type-appropriate default port in the address placeholder when you pick a service type.
- For Plex, a "Sign in to Plex" button fills in the X-Plex-Token for you via Plex's own sign-in flow - no copying tokens out of your browser's dev tools.
- Quick-edit controls on every check's row in Settings (Enabled, and for Plex/Jellyfin path checks, the empty-path severity and minimum-entries count) - no need to open Edit for a one-field change. These stage locally with an obvious "unsaved changes" banner and explicit Save/Discard, so a stray click can't silently change what's being monitored.
- API keys are encrypted at rest (Fernet/AES) and never echoed back to the browser.
- Historic results stored in SQLite, with a History tab and per-service uptime strip on the dashboard.
- Single Docker container: web GUI + API + scheduler + database, no external dependencies.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Then open `http://<host>:8080`.

## Detecting unmounted/failed drives

The scenario this targets: Radarr/Sonarr's root folder is a network share
(e.g. an SMB share added in Unraid) that sometimes mounts "successfully" as
far as the OS is concerned, but is actually empty - nothing underneath it
mounted properly, so the app is quietly looking at an empty directory. Three
ways to catch this are supported:

1. **Root folder API check (recommended, on by default)** - the built-in
   "Root folders accessible" check calls two of the target app's own API
   endpoints, both from *its* point of view, needing **no extra volume
   mounts** on the HealthChecker container at all:
   - `/api/v3/rootfolder` for the `accessible` flag - catches a mount point
     that's gone entirely.
   - `/api/v3/filesystem` (the same endpoint the app's own "Add Root Folder"
     folder browser uses) to actually list each accessible root folder's
     contents - catches the empty-but-technically-mounted case `accessible`
     alone misses, which is the one that actually matters here.

   Both signals are combined into one check result; either one failing marks
   the check as failing. Covers whatever root folders are already configured
   *inside* Radarr/Sonarr/Lidarr/Whisparr (Prowlarr has none to check).
2. **`arr_filesystem_path` (API-based, add manually)** - same underlying API
   as above, but for any path you give it, not just configured root folders
   - useful for a specific subfolder you want to watch independently. Takes
   a single required field, **Path in `<app>` container**, exactly as that
   app itself sees it. Still no volume mount needed - the app does the
   looking, not HealthChecker.
3. **`filesystem_path` (direct, requires a bind mount)** - for services with
   no such browse API (anything that isn't Radarr/Sonarr/Lidarr/Whisparr).
   Has two path fields, because the path an app sees for a folder is
   essentially never the same path HealthChecker sees for that same
   underlying host directory - each container maps its own volumes
   independently, and they can coincidentally collide (e.g. a torrent
   client's `/data` meaning something completely different to Radarr's
   `/data`):
   - **Path in HealthChecker container** - the actual path this check tests.
     For this to see anything meaningful, bind-mount the host path in
     question into the HealthChecker container (read-only is fine), e.g. in
     `docker-compose.yml`:

     ```yaml
     volumes:
       - /mnt/media:/mnt/media:ro
     ```
   - **Path in `<app>` container** - optional, purely a label so the check's
     message tells you which of the target app's own paths this corresponds
     to. Doesn't affect the check itself.

   A mount point whose backing disk/share failed to mount typically still
   exists as an *empty* directory, so the check flags it as failing if it has
   fewer than `min_entries` items (default: 1).

## Adding a service

Settings tab -> "Add service". Pick a type (see "Supported services" below) -
this autofills the Name field and updates the Local address placeholder with
that app's usual default port, and switches the credential field(s) to match
(see below). Set a **local address**, a **remote address**, or both, then hit
**"Test connection"** for an immediate green ✓/red ✕ per address before you
even save:

- **Local address** - direct/LAN URL (e.g. `http://radarr:7878`).
- **Remote address** - public/reverse-proxied URL, if you have one (e.g.
  `https://radarr.example.com`).
- At least one is required.

With only one address set, checks just run against it as normal - nothing
below applies. With **both** set:

- By default, the **Web UI reachable** check runs against both addresses
  (labeled `(local)` / `(remote)`); every other check runs against the local
  address only. This catches a broken reverse proxy/external access without
  doubling up API-heavy checks that don't gain much from running twice.
- Tick **"Run all checks against both Internal and remote addresses"** (info
  icon next to it in the Add/Edit service form) to run *every* check against
  both addresses instead, each shown as its own row on the dashboard and in
  history.

### Credentials

The credential field(s) shown change based on the service type:

- **Radarr/Sonarr/Lidarr/Whisparr/Prowlarr/Jellyfin/Chaptarr/Generic** - a
  single **API key** field (Settings > General > API Key for the *arr apps;
  Jellyfin: Dashboard > API Keys). Only needed for authenticated checks.
- **Plex** - the field is labeled **X-Plex-Token**. Click **"Sign in to
  Plex"** next to it to get one without copying it out of your browser's dev
  tools: it opens Plex's own sign-in page in a popup, and once you authorize
  there the token is filled in automatically.
- **qBittorrent** - **Username** + **Password**, verified against the WebUI's
  real login API. Leave both blank if that instance has authentication
  disabled.
- **Deluge** - **Password** only (Deluge's WebUI has no username), same
  real-login verification. Leave blank if disabled.
- **rTorrent** - **Username** + **Password**, sent as HTTP Basic Auth on the
  web UI check (rTorrent itself has no API; this covers a ruTorrent frontend
  sitting behind htaccess-style auth). Leave blank if there's none.

A sensible set of default checks is created automatically based on the
type - add more from the service's expanded row, each with its own optional
poll interval override (see below).

## Supported services

| Type | Integration depth |
|---|---|
| Radarr, Sonarr | Full: web UI, API status, root-folder accessibility + population, health/notifications feed, ad-hoc path checks via API |
| Lidarr, Whisparr | Same as Radarr/Sonarr - both are Servarr-family apps with the same API shape (Lidarr on API v1, Whisparr on v3) |
| Prowlarr | Web UI, API status, health/notifications feed (no root folders to check) |
| Plex | Web UI (`/web/index.html`), `/identity` liveness, Remote Access status (plex.tv + plex.direct reachability), library/path checks via API (see "Scanning libraries automatically") |
| Jellyfin | Web UI, `/health` endpoint, library/path checks via API (admin key required - see below) |
| Chaptarr | Web UI only for now - I couldn't verify its API shape, so it isn't assumed to be Servarr-compatible. Add `http_200`/`keyword_match` custom checks as needed; let me know if it does follow the Servarr API and I'll wire up full support. |
| qBittorrent | Web UI + real login verification (Username/Password against the WebUI API) |
| Deluge | Web UI + real login verification (Password only) |
| rTorrent | Web UI, pointed at whatever fronts it - rTorrent itself has no HTTP UI, so this is really monitoring its usual **ruTorrent** frontend (hence the ruTorrent icon). Username/Password apply as HTTP Basic Auth. |
| Generic | Web UI checks only - for anything else |

Any service (regardless of type) can also have `filesystem_path` or
`keyword_match` checks added manually.

## Scanning libraries automatically

For Plex and Jellyfin, instead of typing out `arr_filesystem_path`-style
checks by hand for every library, click **"Scan libraries"** on the
service's expanded row in Settings. It asks the service itself (via the same
browse APIs as the checks below) what libraries and folders it has
configured, and adds one filesystem check per folder automatically - no
guessing paths, no bind mounts. Safe to click again later (e.g. after adding
a library): it skips any path that already has a check.

## Available check types

| Type | Applies to | What it does |
|---|---|---|
| `http_200` | any | GETs a URL, expects one of a list of status codes |
| `keyword_match` | any | GETs a URL, requires/forbids a substring in the body |
| `filesystem_path` | any | Checks a path exists and has a minimum number of entries (see above) |
| `arr_system_status` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Confirms the API is reachable and the API key is valid |
| `arr_root_folder` | Radarr/Sonarr/Lidarr/Whisparr | Flags any root folder reported as inaccessible, empty-from-the-app's-own-view, or below a free-space threshold - see "Detecting unmounted/failed drives" above |
| `arr_filesystem_path` | Radarr/Sonarr/Lidarr/Whisparr | Same empty/populated check as `arr_root_folder`, but for an arbitrary path you specify rather than the app's configured root folders - no volume mount needed |
| `arr_health` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Pulls the app's own health/notifications feed into this dashboard |
| `plex_identity` | Plex | Hits Plex's unauthenticated `/identity` endpoint |
| `plex_remote_access` | Plex | Checks plex.tv for this server's registered connections and actually tries to reach its public `plex.direct` address; reports OK (direct), degraded (relay-only), or failing (nothing registered). Needs the Plex token and outbound internet access. Polled every 10 minutes by default (see below) since it depends on an external API. |
| `plex_filesystem_path` | Plex | Checks a path exists and is non-empty via Plex's own folder-browse API (the same one its "Add Library" picker uses) - no volume mount needed |
| `jellyfin_health` | Jellyfin | Hits Jellyfin's `/health` endpoint |
| `jellyfin_filesystem_path` | Jellyfin | Checks a path exists and is non-empty via Jellyfin's `/Environment/DirectoryContents` API - no volume mount needed. Needs an administrator API key. |
| `qbittorrent_login` | qBittorrent | Confirms the configured Username/Password actually logs in via the WebUI API; a no-op OK if neither is set |
| `deluge_login` | Deluge | Confirms the configured Password actually logs in via the WebUI JSON-RPC API; a no-op OK if not set |

### Per-check poll interval

Every check has an optional interval override (seconds). Leave it blank to
run on every poll of the service; set it higher (e.g. 600) to run that one
check less often than its siblings - the default `plex_remote_access` check
uses this to poll every 10 minutes even on a service polled every 5.

### Quick-editing checks

Every check's row in Settings has an **Enabled** checkbox right there, no
need to open Edit just to pause one check. `plex_filesystem_path` and
`jellyfin_filesystem_path` checks get two more: a **Red/Yellow** toggle for
whether an empty path is a hard failure or just a warning (a brand-new,
legitimately-empty library shouldn't necessarily page you the same way a
dead mount should), and a **−/+** stepper for the minimum entries expected.
Both are also editable the normal way via Edit, kept in sync either way.

None of these save immediately - an **"unsaved changes"** banner appears at
the top of Settings as soon as you touch one, with **Save Changes** (applies
everything you've changed, across as many checks/services as you touched,
in one go) and **Discard Changes** (reverts to what's actually saved).
Switching tabs or triggering other actions elsewhere on the page won't lose
your pending edits; only Save or Discard clears them, and leaving the page
with changes pending prompts you first.

## Public dashboard

A second, minimal web app runs on its own port (`8090` inside the
container) purpose-built to be exposed externally without the risk that
comes with exposing the full admin app:

- Just the dashboard - no top bar, no nav, no settings.
- Two unlinked-from-the-page-but-reachable pages at `/history` and
  `/notifications` (tiny, low-opacity links in the bottom-right corner of
  the dashboard if you want to find them by eye).
- **No mutating routes exist on this port at all** - it's a separate FastAPI
  app that only ever imports read-only query code, not "the same app with
  bits hidden in the UI". There's no `/api/services` route to find here even
  if you go looking, and no API keys are ever serialized to any client.
- No login by default (the point is friction-free viewing) - if you want
  one, put it behind your reverse proxy/VPN, same as you would for anything
  else you expose.

Runs by default; set `HC_PUBLIC_DASHBOARD_ENABLED=false` to turn it off
entirely (then you don't need to publish port 8090 either).

## Security notes

- API keys are encrypted with Fernet before being stored in SQLite, using a
  key from `HC_APP_SECRET_KEY` if set, otherwise a key generated on first run
  and persisted to `/config/secret.key`. **Set `HC_APP_SECRET_KEY` and back it
  up** - if the generated key file is lost, stored API keys can't be
  decrypted and services will need their keys re-entered.
- The admin web UI/API (port 8080) has no authentication by default (fine on
  a trusted LAN behind your own reverse proxy/VPN). Set `HC_AUTH_USERNAME`
  and `HC_AUTH_PASSWORD` in `.env` to require HTTP Basic Auth for it, or put
  it behind your existing reverse proxy's auth. This does **not** apply to
  the public dashboard port (8090), which is unauthenticated by design - see
  "Public dashboard" above.
- Filesystem checks only ever read paths you've explicitly bind-mounted
  read-only; the container does not need write access to your media.
- "Sign in to Plex" never sees your Plex password - it uses Plex's standard
  PIN-based sign-in flow (the same mechanism apps like Overseerr use): this
  app only ever receives the resulting token, via a popup hosted on plex.tv
  itself.

## Upgrading

Schema changes apply automatically on startup (additive `ALTER TABLE`s
against the existing SQLite file - no separate migration step). Services
created before the local/remote address split keep working unchanged: their
old single address becomes their local address automatically.

## Configuration reference

All settings are environment variables (see `.env.example`), prefixed `HC_`:
`HC_DEFAULT_POLL_INTERVAL_SECONDS`, `HC_HTTP_TIMEOUT_SECONDS`,
`HC_HISTORY_RETENTION_DAYS`, `HC_APP_SECRET_KEY`, `HC_AUTH_USERNAME`,
`HC_AUTH_PASSWORD`, `HC_LOG_LEVEL`, `HC_PORT` (default `8080`),
`HC_PUBLIC_DASHBOARD_ENABLED` (default `true`), `HC_PUBLIC_PORT` (default
`8090`), `HC_DATA_DIR` (defaults to `/config`, matching the compose volume -
named to match the convention used by Radarr/Sonarr/etc. images).

## Development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
HC_DATA_DIR=./config python -m app.run          # both ports, matches the container
# or, for just the admin app with auto-reload:
HC_DATA_DIR=./config uvicorn app.main:app --reload --port 8080
```

## Credits

Service icons from [walkxcode/dashboard-icons](https://github.com/walkxcode/dashboard-icons).
