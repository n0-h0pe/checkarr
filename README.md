# Media Estate HealthChecker

A self-hosted dashboard that periodically polls your media stack (Radarr,
Sonarr, Lidarr, Whisparr, Chaptarr, Prowlarr, Plex, Jellyfin, qBittorrent,
Deluge, rTorrent, or any other HTTP service) and shows one consolidated view
of what's healthy, what's degraded, and why.

## Features

- Polls each service on its own schedule (default every 5 minutes, configurable globally, per-service, and per-check).
- Local and remote addresses: give a service either address, or both - if both are set, every target-scoped check runs against each on every poll (useful when a service is reachable directly on the LAN and via a reverse proxy, and you want both paths monitored independently).
- Built-in checks: HTTP 200 web UI reachability, *arr-family API status, root-folder accessibility **and population** (drive/mount detection - see below), each app's own system health feed, and for Plex, Remote Access status.
- Fully configurable: add your own checks per service (custom HTTP path/status/keyword checks, or a filesystem existence check).
- Consolidates the *arr apps' own "System > Status" health notifications (indexer down, missing files, low disk space, etc.) into one Notifications tab, with automatic resolve-tracking.
- A second, restricted read-only dashboard on its own port - no settings, no API keys, nothing mutable - safe to expose externally. See "Public dashboard" below.
- Real app icons (not emoji), and a version/build date in the header so you can tell at a glance whether you're running the image you think you are.
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
mounted properly, so the app is quietly looking at an empty directory. Two
ways to catch this are supported, and you can use either or both:

1. **Root folder API check (recommended)** - the built-in "Root folders
   accessible" check calls two of the target app's own API endpoints, both
   from *its* point of view, needing **no extra volume mounts** on the
   HealthChecker container at all:
   - `/api/v3/rootfolder` for the `accessible` flag - catches a mount point
     that's gone entirely.
   - `/api/v3/filesystem` (the same endpoint the app's own "Add Root Folder"
     folder browser uses) to actually list each accessible root folder's
     contents - catches the empty-but-technically-mounted case `accessible`
     alone misses, which is the one that actually matters here.

   Both signals are combined into one check result; either one failing marks
   the check as failing. Applies to Radarr, Sonarr, Lidarr, and Whisparr
   (Prowlarr has no root folders to check).
2. **Direct filesystem check (optional, belt-and-braces)** - add a
   `filesystem_path` check on any service. It has two path fields, because
   the path an app like Radarr sees for a folder is essentially never the
   same path HealthChecker sees for that same underlying host directory -
   each container maps its own volumes independently, and they can
   coincidentally collide (e.g. a torrent client's `/data` meaning something
   completely different to Radarr's `/data`):
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

Settings tab -> "Add service". Pick a type (see "Supported services" below),
and set a **local address**, a **remote address**, or both:

- **Local address** - direct/LAN URL (e.g. `http://radarr:7878`).
- **Remote address** - public/reverse-proxied URL, if you have one (e.g.
  `https://radarr.example.com`).
- At least one is required. If you set both, every check that talks to the
  service's web UI/API runs against **both** addresses on every poll,
  labeled `(local)` / `(remote)` in the dashboard and history - useful for
  catching a reverse-proxy misconfiguration even when the app itself is
  perfectly healthy on the LAN.

Add an API key (Radarr/Sonarr/Lidarr/Whisparr/Prowlarr: Settings > General >
API Key; Plex: your X-Plex-Token; Jellyfin: an API key from Dashboard > API
Keys - only needed for authenticated checks). A sensible set of default
checks is created automatically based on the type - add more from the
service's expanded row, each with its own optional poll interval override
(see below).

## Supported services

| Type | Integration depth |
|---|---|
| Radarr, Sonarr | Full: web UI, API status, root-folder accessibility + population, health/notifications feed |
| Lidarr, Whisparr | Same as Radarr/Sonarr - both are Servarr-family apps with the same API shape (Lidarr on API v1, Whisparr on v3) |
| Prowlarr | Web UI, API status, health/notifications feed (no root folders to check) |
| Plex | Web UI, `/identity` liveness, Remote Access status (plex.tv + plex.direct reachability) |
| Jellyfin | Web UI, `/health` endpoint |
| Chaptarr | Web UI only for now - I couldn't verify its API shape, so it isn't assumed to be Servarr-compatible. Add `http_200`/`keyword_match` custom checks as needed; let me know if it does follow the Servarr API and I'll wire up full support. |
| qBittorrent, Deluge | Web UI only for now - both need session/cookie-based login rather than a simple API key, which isn't implemented yet. Set an address and use custom `http_200`/`keyword_match` checks in the meantime. |
| rTorrent | Web UI only, pointed at whatever fronts it - rTorrent itself has no HTTP UI, so this is really monitoring its usual **ruTorrent** frontend (hence the ruTorrent icon) |
| Generic | Web UI checks only - for anything else |

Any service (regardless of type) can also have `filesystem_path` or
`keyword_match` checks added manually.

## Available check types

| Type | Applies to | What it does |
|---|---|---|
| `http_200` | any | GETs a URL, expects one of a list of status codes |
| `keyword_match` | any | GETs a URL, requires/forbids a substring in the body |
| `filesystem_path` | any | Checks a path exists and has a minimum number of entries (see above) |
| `arr_system_status` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Confirms the API is reachable and the API key is valid |
| `arr_root_folder` | Radarr/Sonarr/Lidarr/Whisparr | Flags any root folder reported as inaccessible, empty-from-the-app's-own-view, or below a free-space threshold - see "Detecting unmounted/failed drives" above |
| `arr_health` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Pulls the app's own health/notifications feed into this dashboard |
| `plex_identity` | Plex | Hits Plex's unauthenticated `/identity` endpoint |
| `plex_remote_access` | Plex | Checks plex.tv for this server's registered connections and actually tries to reach its public `plex.direct` address; reports OK (direct), degraded (relay-only), or failing (nothing registered). Needs the Plex token and outbound internet access. Polled every 10 minutes by default (see below) since it depends on an external API. |
| `jellyfin_health` | Jellyfin | Hits Jellyfin's `/health` endpoint |

### Per-check poll interval

Every check has an optional interval override (seconds). Leave it blank to
run on every poll of the service; set it higher (e.g. 600) to run that one
check less often than its siblings - the default `plex_remote_access` check
uses this to poll every 10 minutes even on a service polled every 5.

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
