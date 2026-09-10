# Media Estate HealthChecker

A self-hosted dashboard that periodically polls your media stack (Radarr,
Sonarr, Prowlarr, Plex, Jellyfin, or any other HTTP service) and shows one
consolidated view of what's healthy, what's degraded, and why.

## Features

- Polls each service on its own schedule (default every 5 minutes, configurable globally, per-service, and per-check).
- Local and remote addresses: give a service either address, or both - if both are set, every target-scoped check runs against each on every poll (useful when a service is reachable directly on the LAN and via a reverse proxy, and you want both paths monitored independently).
- Built-in checks: HTTP 200 web UI reachability, Radarr/Sonarr/Prowlarr API status, Radarr/Sonarr root-folder accessibility (drive/mount detection), each app's own system health feed, and for Plex, Remote Access status.
- Fully configurable: add your own checks per service (custom HTTP path/status/keyword checks, or a filesystem existence check).
- Consolidates Radarr/Sonarr/Prowlarr's own "System > Status" health notifications (indexer down, missing files, low disk space, etc.) into one Notifications tab, with automatic resolve-tracking.
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

Two ways are supported, and you can use either or both:

1. **Root folder API check (recommended)** - the built-in "Root folders
   accessible" check calls Radarr's/Sonarr's own
   `/api/v3/rootfolder` endpoint and reads the `accessible` flag they report
   for each of their root folders. This is exactly what Radarr/Sonarr use
   internally to detect a dead mount, so it needs **no extra volume mounts**
   on the HealthChecker container - it just asks the app what it sees.
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

Settings tab -> "Add service". Pick a type (Radarr/Sonarr/Prowlarr/Plex/
Jellyfin/Generic), and set a **local address**, a **remote address**, or
both:

- **Local address** - direct/LAN URL (e.g. `http://radarr:7878`).
- **Remote address** - public/reverse-proxied URL, if you have one (e.g.
  `https://radarr.example.com`).
- At least one is required. If you set both, every check that talks to the
  service's web UI/API runs against **both** addresses on every poll,
  labeled `(local)` / `(remote)` in the dashboard and history - useful for
  catching a reverse-proxy misconfiguration even when the app itself is
  perfectly healthy on the LAN.

Add an API key (Radarr/Sonarr/Prowlarr: Settings > General > API Key; Plex:
your X-Plex-Token; Jellyfin: an API key from Dashboard > API Keys, only
needed for authenticated checks). A sensible set of default checks is
created automatically based on the type - add more from the service's
expanded row, each with its own optional poll interval override (see below).

## Available check types

| Type | Applies to | What it does |
|---|---|---|
| `http_200` | any | GETs a URL, expects one of a list of status codes |
| `keyword_match` | any | GETs a URL, requires/forbids a substring in the body |
| `filesystem_path` | any | Checks a path exists and has a minimum number of entries (see above) |
| `arr_system_status` | Radarr/Sonarr/Prowlarr | Confirms the API is reachable and the API key is valid |
| `arr_root_folder` | Radarr/Sonarr | Flags any root folder reported as inaccessible, or below a free-space threshold |
| `arr_health` | Radarr/Sonarr/Prowlarr | Pulls the app's own health/notifications feed into this dashboard |
| `plex_identity` | Plex | Hits Plex's unauthenticated `/identity` endpoint |
| `plex_remote_access` | Plex | Checks plex.tv for this server's registered connections and actually tries to reach its public `plex.direct` address; reports OK (direct), degraded (relay-only), or failing (nothing registered). Needs the Plex token and outbound internet access. Polled every 10 minutes by default (see below) since it depends on an external API. |
| `jellyfin_health` | Jellyfin | Hits Jellyfin's `/health` endpoint |

### Per-check poll interval

Every check has an optional interval override (seconds). Leave it blank to
run on every poll of the service; set it higher (e.g. 600) to run that one
check less often than its siblings - the default `plex_remote_access` check
uses this to poll every 10 minutes even on a service polled every 5.

## Security notes

- API keys are encrypted with Fernet before being stored in SQLite, using a
  key from `HC_APP_SECRET_KEY` if set, otherwise a key generated on first run
  and persisted to `/data/secret.key`. **Set `HC_APP_SECRET_KEY` and back it
  up** - if the generated key file is lost, stored API keys can't be
  decrypted and services will need their keys re-entered.
- The web UI/API has no authentication by default (fine on a trusted LAN
  behind your own reverse proxy/VPN). Set `HC_AUTH_USERNAME` and
  `HC_AUTH_PASSWORD` in `.env` to require HTTP Basic Auth for the whole app,
  or put it behind your existing reverse proxy's auth.
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
`HC_AUTH_PASSWORD`, `HC_LOG_LEVEL`, `HC_DATA_DIR` (defaults to `/data`,
matching the compose volume).

## Development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
HC_DATA_DIR=./data uvicorn app.main:app --reload --port 8080
```
