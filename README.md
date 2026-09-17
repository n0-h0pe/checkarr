# Checkarr

A self-hosted dashboard that periodically polls your media stack (Radarr,
Sonarr, Lidarr, Whisparr, Chaptarr, Prowlarr, Plex, Jellyfin, Immich,
qBittorrent, Deluge, rTorrent, ruTorrent, Seerr, Jellyseerr, Dispatcharr,
Sportarr, Cleanuparr, iPlayarr, iPlayer-Arr, or any other HTTP service) and
shows one consolidated view of what's healthy, what's degraded, and why.

## Features

- Polls each service on its own schedule, with built-in checks for web UI
  reach-ability, API status, root-folder accessibility, disk space, and more.
- Consolidates the *arr apps' own health feeds into one Notifications tab
  that shows the *arr apps current issues.
- A second, restricted, read-only dashboard on its own port, safe to expose
  externally.
- Historic results in a exportable History table and a per-service uptime
  strip on the dashboard.
- Outbound alerting via Email, Discord, Slack, Telegram, Pushbullet,
  Pushover, a generic webhook, or a native browser notification.
- Batches rapid-fire alerts into one message instead of flooding your inbox.
- Self-monitoring for low disk space and failing alert channels.
- Scheduled Down Time to suppress alerts (not checks) during planned
  maintenance, recurring or a one-off instant window.
- Editable, saveable dashboard layouts, drag-and-drop and all, with
  independent Desktop and Mobile layouts.
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
