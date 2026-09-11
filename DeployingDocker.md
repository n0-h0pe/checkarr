# Deploying Checkarr

Checkarr ships as a single Docker container: web GUI, API, scheduler, and
SQLite database, all in one image. This covers building and running it on
each platform, the full environment variable reference, volumes, the
health check, upgrading, and running it without Docker at all.

## Windows (Docker Desktop)

1. Install Docker Desktop and make sure it's running.
2. Clone or download this repository.
3. Copy `.env.example` to `.env` and adjust if you want (all values are
   optional, defaults work fine for a first run).
4. From the project folder, in PowerShell or a terminal:

   ```powershell
   docker compose up -d --build
   ```
5. Open `http://localhost:8080`.

The `./config` volume in `docker-compose.yml` maps to a folder next to the
compose file. On Windows that folder lives wherever you cloned the repo, no
special path translation needed.

## Linux

Same steps as Windows, run from a shell instead of PowerShell:

```bash
cp .env.example .env
docker compose up -d --build
```

If your Docker daemon requires `sudo`, prefix accordingly. Linux is also
where Checkarr is most likely to sit next to the actual media stack it's
watching, so this is the natural home for the optional read-only
bind-mounts described below.

## Unraid

Checkarr doesn't (yet) have a Community Applications template, so it's a
manual container for now:

1. Build the image once (SSH into Unraid, or build it elsewhere and load
   the image): from the project folder,

   ```bash
   docker build -t checkarr:latest .
   ```
2. In the Unraid Docker tab, add a new container by hand (or edit an
   existing one), pointing it at the `checkarr:latest` image you just built.
3. Add the ports (`8080` and, if you want the public dashboard, `8090`),
   and a path mapping for `/config` to an appdata folder, e.g.
   `/mnt/user/appdata/checkarr` on the host mapped to `/config` in the
   container.
4. Add whatever environment variables you need from the reference below
   (or none, the defaults are fine).
5. Apply, then open `http://<unraid-ip>:8080`.

To pick up a new version later: rebuild the image with the same command
above, then Edit the container in the Unraid GUI and hit Apply again to
recreate it from the new image. Your data stays put, since it lives in the
bind-mounted `/config` folder, not inside the container.

## Mac

Same as Linux, using Docker Desktop for Mac:

```bash
cp .env.example .env
docker compose up -d --build
```

## Environment variables

All settings are environment variables, prefixed `HC_`, set in `.env`
(copied from `.env.example`) or however your platform passes environment
variables to a container. Everything is optional.

| Variable | Default | What it does |
|---|---|---|
| `HC_APP_SECRET_KEY` | (generated on first run) | Fixed Fernet key for encrypting stored API keys. Set and back this up, see Security notes in [Settings.md](Settings.md). |
| `HC_DEFAULT_POLL_INTERVAL_SECONDS` | `300` | Default poll interval for services that don't override it. |
| `HC_HTTP_TIMEOUT_SECONDS` | `10` | Request timeout for checks. |
| `HC_AUTH_USERNAME` / `HC_AUTH_PASSWORD` | (unset) | Set both to require HTTP Basic Auth on the admin app (port 8080). Unset means no auth, fine on a trusted LAN. |
| `HC_LOG_LEVEL` | `INFO` | Python logging level. |
| `HC_PORT` | `8080` | The admin app's port. Only change this if you also change the container's port mapping to match. |
| `HC_PUBLIC_DASHBOARD_ENABLED` | `true` | Set to `false` to disable the read-only public dashboard entirely. |
| `HC_PUBLIC_PORT` | `8090` | The public dashboard's port. |
| `HC_DATA_DIR` | `/config` | Where the database, secret key, and everything else Checkarr writes lives. Matches the `./config` volume in `docker-compose.yml`. |

How long check history is kept is not an environment variable, it's
configured in Settings > Log & History Pruning, see [Settings.md](Settings.md).

### Secrets from environment variables

Every password/API-key field in the app (a service's API key, its Jellyfin
admin password, a notification channel's secret) can instead be sourced
from an environment variable, so it never touches the database at all. In
the field's "Use environment variable" checkbox, give it a variable name
like `RADARR_API_KEY`, then set that variable on the container the same way
as any other `HC_` variable above, no `HC_` prefix required for these.

```yaml
environment:
  - RADARR_API_KEY=abcdef1234567890
```

Switching a field to this mode deletes whatever secret was previously
stored for it out of the database, so it stops existing in `/config`
entirely. See Settings.md for the full behavior, including what happens if
the variable isn't actually set.

## Volumes

`docker-compose.yml` maps `./config` to `/config` inside the container.
This one folder holds the SQLite database, the generated encryption key
(unless `HC_APP_SECRET_KEY` is set), and nothing else. Back it up if you
care about your configured services, checks, and history.

Optionally, bind-mount the same host paths your *arr apps use, read-only,
so a `filesystem_path` check can independently confirm a drive or share is
actually mounted inside the Checkarr container too:

```yaml
volumes:
  - ./config:/config
  - /mnt/media:/mnt/media:ro
```

This is only needed for the direct filesystem check. The built-in "Root
folders accessible" check talks to Radarr/Sonarr's own API instead and
needs no extra mounts, see [ConfiguringServices.md](ConfiguringServices.md).

## Health check

The image ships a Docker `HEALTHCHECK` that curls `http://127.0.0.1:8080/healthz`
every 30 seconds. It only checks that the admin app itself is up and
answering, not that any particular monitored service is healthy, that part
is what the dashboard is for.

## Upgrading

Pull or rebuild the new image, then recreate the container the same way you
created it (`docker compose up -d --build`, or Edit and Apply on Unraid).
Schema changes apply automatically on startup: additive `ALTER TABLE`s
against the existing SQLite file, no separate migration step, and no
downtime beyond the container restart itself.

## Development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
HC_DATA_DIR=./config python -m app.run          # both ports, matches the container
# or, for just the admin app with auto-reload:
HC_DATA_DIR=./config uvicorn app.main:app --reload --port 8080
```

No Docker required for this, just Python 3.12 and the packages in
`requirements.txt`. If you've made it this far into a deployment doc just to
run it locally instead, no judgment, that's what half of us do anyway.
