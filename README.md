# Checkarr

A self-hosted dashboard that periodically polls your media stack (Radarr,
Sonarr, Lidarr, Whisparr, Chaptarr, Prowlarr, Plex, Jellyfin, Immich,
qBittorrent, Deluge, rTorrent, ruTorrent, Seerr, Jellyseerr, Dispatcharr,
Sportarr, Cleanuparr, or any other HTTP service) and shows one consolidated
view of what's healthy, what's degraded, and why. Think of it as a health
check for the health checkers you already trust to tell you when
something's wrong, on the theory that eventually something has to actually
watch the watchers.

## Features

- Polls each service on its own schedule, with built-in checks for web UI
  reachability, API status, root-folder accessibility, disk space, and more.
- Consolidates the *arr apps' own health feeds into one Notifications tab
  that shows exactly what's currently failing, service name and icon
  included.
- A second, restricted, read-only dashboard on its own port, safe to expose
  externally, with an optional compact mode.
- Historic results in a filterable, resizable, exportable History table,
  and a per-service uptime strip on the dashboard.
- Outbound alerting via Email, Discord, Slack, Telegram, Pushbullet,
  Pushover, a generic webhook, or a native browser notification, batching
  rapid-fire alerts into one message instead of flooding your inbox, plus
  its own self-monitoring for low disk space and failing alert channels.
- Scheduled Down Time to suppress alerts (not checks) during planned
  maintenance, recurring or a one-off instant window, permanently recorded
  against the History rows it applied to.
- Editable, saveable dashboard layouts, drag-and-drop and all, with
  independent Desktop and Mobile layouts so a phone never inherits a
  desktop-shaped card grid.
- Custom service icons: pick from the built-in app logos, any emoji, or
  upload your own image.
- API keys and other secrets encrypted at rest, or skip the database
  entirely and source any of them from an environment variable.
- Single Docker container: web GUI, API, scheduler, and database, no
  external dependencies.

See [ConfiguringServices.md](ConfiguringServices.md) for adding services and
checks, and [Settings.md](Settings.md) for everything else in the Settings
tab (dashboard layouts, History, Push Notifications, Log & History Pruning,
and more).

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Then open `http://<host>:8080`.

For platform-specific instructions (Windows, Linux, Unraid, Mac), the full
environment variable reference, and how to run it without Docker at all,
see [DeployingDocker.md](DeployingDocker.md).

## Credits

Service icons from
[walkxcode/dashboard-icons](https://github.com/walkxcode/dashboard-icons).
