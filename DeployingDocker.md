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

## Editing docker-compose.yml and .env

Both files are plain text and live in the project folder (wherever you
cloned or downloaded the repo). `docker-compose.yml` controls port
mappings, volume mounts, and container settings; `.env` (copied from
`.env.example`) holds the environment variables listed further down.
There's nothing Docker-specific about editing either one - any plain text
editor works.

**Windows**

- Easiest: open the project folder in File Explorer, right-click the file
  (`.env` or `docker-compose.yml`), and "Open with" Notepad, VS Code,
  Notepad++, or whatever you have installed.
- From PowerShell, in the project folder: `notepad .env`
- If `.env` doesn't show up in File Explorer, turn on "Show hidden
  files" (or "Show file name extensions") - dotfiles are hidden by
  default on Windows. It's not actually hidden, just named that way.
- Save as plain text (Notepad does this by default). Don't open it with
  Word or another word processor, which would save it with formatting
  Docker can't parse.

**macOS**

- From Terminal, in the project folder: `nano .env` (Ctrl+O, Enter to
  save, Ctrl+X to exit), or `open -a TextEdit .env`.
- If using TextEdit, switch it to plain-text mode first (Format > Make
  Plain Text) before saving, for the same reason as Notepad above.
- `.env` is a dotfile, so it won't show in a Finder "Open" dialog unless
  you press Cmd+Shift+. to reveal hidden files.

**Linux**

- Same idea: `nano .env` or `nano docker-compose.yml` from a shell in
  the project folder, or `vim`/`gedit`/`kate` if you prefer. Any GUI
  text editor on a desktop environment works too.

**Unraid**

The Windows/macOS/Linux instructions above assume you're running
`docker compose` yourself, where `docker-compose.yml` and `.env` are the
real source of truth. The Unraid section below instead uses the Docker
tab's own "Add Container" form, which stores its settings in Unraid's
container template rather than reading `.env` at all - so on Unraid you
generally don't hand-edit these files, you fill in the equivalent fields
in the GUI (covered in detail below). If you'd rather run Checkarr from
an actual compose file on Unraid anyway (for example via the community
"Compose Manager" plugin), the same edits apply: open a shell via the
webGUI's Terminal icon or SSH, then `nano /mnt/user/appdata/checkarr-src/.env`,
same as the Linux instructions above.

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
manual container for now: pull the source onto Unraid, build the image
locally, then point the Docker tab's GUI at it. No compose file needed
for this path - Unraid's own "Add Container" form replaces it.

### 1. Get the source onto Unraid

Open a shell on Unraid - the Terminal icon in the top-right of the
webGUI, or SSH in from another machine (`ssh root@<unraid-ip>`). Then
clone the repo into a dedicated source folder under appdata:

```bash
mkdir -p /mnt/user/appdata/checkarr-src
cd /mnt/user/appdata/checkarr-src
git clone https://github.com/n0-h0pe/checkarr.git .
```

Unraid doesn't ship `git` by default. If the clone command isn't found,
either install it via the "NerdPack"/"NerdTools" plugin (Apps tab, if
you have Community Applications installed) and re-run the command
above, or skip git entirely and grab a zip instead:

```bash
cd /mnt/user/appdata/checkarr-src
curl -L -o checkarr.zip https://github.com/n0-h0pe/checkarr/archive/refs/heads/master.zip
unzip checkarr.zip
mv checkarr-master/* checkarr-master/.* . 2>/dev/null
rmdir checkarr-master && rm checkarr.zip
```

`checkarr-src` is only the build source. It's intentionally a separate
folder from `/mnt/user/appdata/checkarr` (used below for `/config`),
which holds the live database and settings - so you can safely delete
and re-clone `checkarr-src` at any time without touching your data.

### 2. Build the image

From that same folder:

```bash
cd /mnt/user/appdata/checkarr-src
docker build -t checkarr:latest .
```

The first build takes a few minutes (installing Python dependencies
into the image); later rebuilds after a `git pull` are faster since
Docker reuses unchanged layers. When it finishes, confirm it's there:

```bash
docker images | grep checkarr
```

### 3. Add the container via the Unraid Docker GUI

Go to the **Docker** tab and click **Add Container**. Fill in:

- **Name**: `checkarr` (or anything you like).
- **Repository**: `checkarr:latest` - the image you just built. Leave
  it exactly as that; don't let Unraid try to pull it from Docker Hub,
  there's nothing published there.
- **Network Type**: `Bridge` works for most setups.
- **Port mappings**: click "Add another Path, Port, Variable, Label or
  Device" once per port and add:
  - Container Port `8080` -> Host Port `8080` (the admin GUI).
  - Container Port `8090` -> Host Port `8090` (the read-only public
    dashboard - skip this one if you don't want it exposed at all, and
    also set `HC_PUBLIC_DASHBOARD_ENABLED=false` as a variable below).
- **Path mapping**: add one more entry -
  - Container Path `/config` -> Host Path `/mnt/user/appdata/checkarr`.
  - This is deliberately a *different* folder than `checkarr-src` from
    step 1 - this one holds the running database, not the source code.
- **Variables** (optional): add one "Variable" entry per environment
  variable you want to override, using a name from the reference table
  below as both the Key and Name, e.g. Key `HC_LOG_LEVEL`, Value
  `DEBUG`. There's no `.env` file in play here since the GUI form is
  what actually launches the container - leave this section empty and
  everything just uses its documented default.
- Click **Apply**. Unraid creates and starts the container from the
  image.

Open `http://<unraid-ip>:8080` once it's running.

### 4. Upgrading later

Pull the latest source and rebuild the image:

```bash
cd /mnt/user/appdata/checkarr-src
git pull
docker build -t checkarr:latest .
```

(No `git`? Re-download and re-extract the zip from step 1 over the same
folder instead.)

Then, in the Docker tab, click the checkarr container's icon and choose
**Edit**, then **Apply** without changing anything - this recreates the
container from the freshly built `checkarr:latest` image using the same
settings as before. Your data is untouched, since it lives in the
bind-mounted `/config` folder (`/mnt/user/appdata/checkarr`), not inside
the container image itself.

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
