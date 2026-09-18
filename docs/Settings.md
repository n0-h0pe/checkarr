# Settings

Everything you need to know about the Settings/Configuring Checkarr is here.

# Services

How to add each type of service Checkarr supports, what credentials each
one needs, and how to add checks beyond the defaults.

## Adding a service

Settings tab, "Add service". Picking a
type (see "Supported services" below) autofills the Name field, updates the
Local address placeholder with that app's usual default port, and switches
the credential field(s) to match (see "Credentials" below). Set a local
address, a remote address, or both, then hit "Test connection" for an
immediate result per address before you even save:

- **Local address**, direct/LAN URL, e.g. `http://radarr:7878`.
- **Remote address**, public/reverse-proxied URL, if you have one, e.g.
  `https://radarr.example.com`.
- At least one is required.

With only one address set, checks just run against it as normal, nothing
below applies. With both set:

- By default, the "Web UI reachable" check runs against both addresses
  (labeled local/remote); every other check runs against the local address
  only. This catches a broken reverse proxy without doubling up API-heavy
  checks that don't gain much from running twice.
- Tick "Run all checks against both Internal and remote addresses" to run
  every check against both instead, each shown as its own row on the
  dashboard and in History.

A sensible set of default checks is created automatically based on the
type, add more from the service's expanded row, each with its own optional
poll interval override (see "Per-check poll interval" below).

### Icon

Every service shows the type's own logo by default (the same picture as its
entry in the type dropdown above). "Change icon" next to it opens a picker.
Picking anything replaces the default immediately; "Reset to default" next
to "Change icon" goes back to following the service type's own logo again.

### Credentials

The credential field(s) shown change based on the service type:

- **Radarr / Sonarr / Lidarr / Whisparr / Prowlarr / Chaptarr / Sportarr /
  Seerr / Jellyseerr / Dispatcharr / Cleanuparr / iPlayarr / iPlayer-Arr /
  Generic**: a single API key field (Settings > General > API Key in the
  app itself, where that app has one). Only needed for authenticated
  checks - Dispatcharr, Sportarr, Cleanuparr, iPlayarr, and iPlayer-Arr
  don't have any yet (see "Supported services" below), so it's unused for
  them for now.
- **Immich**: a single API key field, created under your account menu (top
  right) > Account Settings > API Keys > New API Key. Immich lets a key be
  scoped to specific permissions instead of granted full access - for least
  privilege, tick only "Server" (read-only server info/statistics) and
  "Job" (read-only job status), which is everything `immich_server_status`,
  `immich_storage`, and `immich_jobs` use between them. No asset, album,
  user, or admin permissions are needed.
- **Jellyfin**: an API key field (Dashboard > API Keys), plus optional
  admin username and admin password fields. The API key alone covers the
  basic health check, but some admin-only endpoints (library scanning, the
  filesystem path check) reject it even when it belongs to an admin. Filling
  in both admin fields logs in as that account instead for just those
  specific calls.
- **Plex**: the field is labeled X-Plex-Token. Click "Sign in to Plex" next
  to it to get one without copying it out of your browser's dev tools, it
  opens Plex's own sign-in page in a popup, and once you authorize there
  the token is filled in automatically.
- **qBittorrent**: username and password, verified against the WebUI's 
  login API. Leave both blank if that instance has authentication disabled.
- **Deluge**: password only (Deluge's WebUI has no username), same 
  login verification.
- **rTorrent / ruTorrent**: username and password, sent as HTTP Basic Auth
  on the web UI check and the XML-RPC check alike (rTorrent itself has no
  auth of its own - this covers ruTorrent, or whatever else fronts it,
  sitting behind htaccess-style auth).

### Secrets from environment variables

Every password/API-key field in the app has a "Use environment variable"
checkbox next to it. Check it and type the name of an environment variable
(e.g. `RADARR_API_KEY`) set on the container instead of pasting the secret
itself, the app reads that variable at the moment it's needed rather than
storing anything for it.

Switching a field to this mode immediately deletes whatever was stored for
it (encrypted or not) from the database, so the secret stops existing in
`/config` entirely. Switching back to typing the secret directly works the
same in reverse, the environment variable name is dropped and a fresh value
is required, since there's nothing left in the database to fall back to.

An environment variable named this way only needs to be visible to the
container process, it doesn't need an `HC_` prefix or any other special
naming. If the named variable isn't actually set (or is empty) when a check
or notification runs, that secret is treated as unconfigured, same as if
the field had been left blank.

## Supported services

| Type | Integration depth |
|---|---|
| Radarr, Sonarr, Lidarr, Whisparr | Web UI, API status, root-folder accessibility and population, free disk space, health feed, ad-hoc path checks via API |
| Prowlarr | Web UI, API status, health feed |
| Plex | Web UI, identity liveness, Remote Access status, library/path checks via API |
| Jellyfin | Web UI, health endpoint, library/path checks via API (admin-only endpoints, see Credentials above) |
| Chaptarr, Sportarr, Dispatcharr, iPlayarr, iPlayer-Arr | Web UI only for now. |
| qBittorrent | Web UI, real login verification, free disk space via API |
| Deluge | Web UI, real login verification, free disk space via API |
| Cleanuparr | Web UI only for now, its API hasn't been integrated yet. Add `http_200`/`keyword_match` checks as needed. |
| rTorrent | XML-RPC interface, see below. Use this for a bare rTorrent with no ruTorrent in front of it. |
| ruTorrent | Web UI (ruTorrent's own, at `/rutorrent/` by default) plus the XML-RPC interface, defaulted to ruTorrent's httprpc plugin path. Use this instead of rTorrent above whenever ruTorrent is actually what's fronting it - see below, they're separate types because their correct defaults differ. |
| Seerr, Jellyseerr | Web UI, API status, and a check that TMDB is reachable through the app. |
| Immich | Web UI, API status (library counts), free disk space, background job queue failures |
| Generic | Web UI checks only, for anything else |

Any service, regardless of type, can also have `filesystem_path`,
`keyword_match`, or `ftp_path` checks added manually.

### BBC iPlayer downloaders

**iPlayarr** and **iPlayer-Arr** are two separate, independently-maintained
projects that do the same job - each downloads BBC iPlayer content and
presents itself to Sonarr/Radarr as a Newznab indexer plus a
SABnzbd-compatible download client, so it's not a typo seeing both in the
type dropdown. Add whichever one you actually run as its own service here
the same as anything else; this only gets you a dashboard card and uptime
history for it, it doesn't change how Sonarr/Radarr are configured to talk
to it as an indexer/download client, that's still done in their own
Settings the normal way.

iPlayer-Arr additionally exposes an unauthenticated `/api/healthz`
endpoint (its own geo/disk/ffmpeg status check) - worth pointing an
`http_200` check's Path field at directly instead of relying on the
default root-path check, if you'd rather monitor that than just "the web
server is up".

## Detecting unmounted/failed drives

The scenario this targets: a root folder is a network share that sometimes
mounts "successfully" as far as the OS is concerned, but is actually empty,
nothing underneath it mounted properly, so the app is quietly looking at an
empty directory. Three ways to catch this:

1. **Root folder API check (recommended, on by default)**: the built-in
   "Root folders accessible" check calls Radarr/Sonarr/Lidarr/Whisparr's own
   API, from the app's own point of view, needing no extra volume mounts on
   the Checkarr container at all. It checks both that the mount is
   reachable and that it actually lists contents, catching the
   empty-but-technically-mounted case a bare reachability check would miss.
2. **`arr_filesystem_path` (API-based, add manually)**: API checks any path
   you give it exactly like the *arr's native "Browse" interface on the WebUI.
   Looks for the number of files and folders in that directory, and returns
   OK if that count is >0. 
4. **`filesystem_path` (direct, requires a bind mount)**: for services with
   no such browse API. Has two path fields, since the path an app sees for
   a folder is essentially never the path Checkarr sees for that same
   underlying host directory:
   - **Path in Checkarr container**: the actual path this check tests. For
     this to see anything meaningful, bind-mount the host path in question
     into the Checkarr container, read-only is fine, see
     [DeployingDocker.md](DeployingDocker.md).
   - **Path in `<app>` container**: optional, purely a label so the check's
     message tells you which of the target app's own paths this corresponds
     to.

   A mount point whose backing disk or share failed to mount typically
   still exists as an empty directory, so the check flags it as failing if
   it has fewer than the configured minimum number of entries (default 1).

## Scanning libraries automatically

For Plex and Jellyfin, instead of typing out filesystem checks by hand for
every library, click "Scan libraries" on the service's expanded row in
Settings. It asks the service itself what libraries and folders it has
configured, and adds one filesystem check per folder automatically. Safe 
to click again later, it skips any path that already has a check.

## Available check types

| Type | Applies to | What it does |
|---|---|---|
| `http_200` | any | GETs a URL, expects one of a list of status codes |
| `keyword_match` | any | GETs a URL, requires/forbids a substring in the body |
| `filesystem_path` | any | Checks a path exists and has a minimum number of entries |
| `arr_system_status` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Confirms the API is reachable and the API key is valid |
| `arr_root_folder` | Radarr/Sonarr/Lidarr/Whisparr | Flags any root folder reported as inaccessible or empty, see "Detecting unmounted/failed drives" above |
| `arr_disk_space` | Radarr/Sonarr/Lidarr/Whisparr | Free disk space via the app's own API, as a percentage of total capacity |
| `arr_filesystem_path` | Radarr/Sonarr/Lidarr/Whisparr | Same empty/populated check as `arr_root_folder`, for an arbitrary path, no volume mount needed |
| `arr_health` | Radarr/Sonarr/Lidarr/Whisparr/Prowlarr | Pulls the app's own health feed into this dashboard |
| `plex_identity` | Plex | Hits Plex's unauthenticated identity endpoint |
| `plex_remote_access` | Plex | Checks plex.tv for this server's registered connections and tries to reach its public address directly |
| `plex_filesystem_path` | Plex | Checks a path exists and is non-empty via Plex's own folder-browse API |
| `jellyfin_health` | Jellyfin | Hits Jellyfin's health endpoint |
| `jellyfin_filesystem_path` | Jellyfin | Checks a path exists and is non-empty via Jellyfin's own directory-listing API (admin-only endpoint, see Credentials above) |
| `qbittorrent_login` | qBittorrent | Confirms the configured username/password actually logs in |
| `deluge_login` | Deluge | Confirms the configured password actually logs in |
| `qbittorrent_disk_space` | qBittorrent | Free space on qBittorrent's default save path |
| `deluge_disk_space` | Deluge | Free space at a path via its API |
| `rtorrent_rpc_status` | rTorrent, ruTorrent | Confirms rTorrent's XML-RPC interface is reachable, see below |
| `ftp_path` | any | Checks a path exists and has a minimum number of entries, over FTP/FTPS |
| `external_port_open` | any | Plain TCP connect to a static IP/hostname and port you provide, independent of the service's own address - see "Checking a port-forwarded address" below |
| `overseerr_status` | Seerr, Jellyseerr | Confirms the API is reachable and the API key is valid |
| `overseerr_tmdb_status` | Seerr, Jellyseerr | Confirms TMDB is reachable through it, see below |
| `ssl_certificate` | any | Validates the actual TLS certificate for an `https://` address, see below |
| `immich_server_status` | Immich | Confirms the API is reachable and the API key is valid, reports photo/video counts |
| `immich_storage` | Immich | Free disk space via the app's own API, as a percentage of total capacity |
| `immich_jobs` | Immich | Flags any background job queue (thumbnails, metadata, facial recognition, etc.) with failed jobs |

### Disk space

`arr_disk_space`, `immich_storage`, and `qbittorrent_disk_space`/
`deluge_disk_space` all report free space as a percentage of total
capacity, with two adjustable thresholds in the Add/Edit check panel: Warn
below % free (default 10) and Fail below % free (default 3).

They differ in where the numbers come from:

- `arr_disk_space` and `immich_storage` both read free and total space
  straight from the app's own API, so the percentage thresholds work
  immediately. For `arr_disk_space`, leave Path blank to check every disk
  the app reports on and flag whichever is lowest.
- `qbittorrent_disk_space`/`deluge_disk_space` only get free space from
  their APIs, not total capacity, so there's nothing to compute a
  percentage against until you fill in "Total disk size (GB)" yourself.
  Leave it blank and the check just reports free space with no threshold.

Neither rTorrent nor ruTorrent has an equivalent, the XML-RPC interface
they're both built on has no disk-space method.

### rTorrent vs ruTorrent, and the XML-RPC endpoint

rTorrent has no web UI or REST API of its own, a design decision it made
sometime around when XML-RPC still seemed like a fine idea. `rtorrent_rpc_status`
speaks that interface directly instead, whichever service type it's
attached to - but the correct URL Path to it depends entirely on how
rTorrent is actually set up, which is why **rTorrent** and **ruTorrent**
are two separate service types rather than one, each defaulting this check
to the path that setup actually needs:

- **rTorrent** (bare, no ruTorrent in front of it): a direct XML-RPC-over-HTTP
  bridge, e.g. via `xmlrpc.scgi_port` and a webserver proxying to it.
  Defaults to `/RPC2`. Has no web UI at all, so this type skips the Web UI
  reachable check entirely rather than seeding one against nothing.
- **ruTorrent**: rTorrent fronted by the actual ruTorrent web app, which
  does have a real web UI (defaults to `/rutorrent/`). Its own httprpc
  plugin is the common RPC bridge here, so this type defaults the XML-RPC
  check to `/rutorrent/plugins/httprpc/action.php`. Older ruTorrent setups
  instead use `[path to ruTorrent]/plugins/rpc/rpc.php`.

If you picked the right type and it's still 404ing, your install just uses
a different path than that type's default - edit the check's URL Path
field directly, it's just a starting point, not a hard requirement.

Uses the service's username/password as HTTP Basic Auth, same as the web UI
check.

### Seerr/Jellyseerr

Two default checks:

- `overseerr_status`, the app itself is up and the API key works.
- `overseerr_tmdb_status`, TMDB, the external metadata API both Seerr and
  Jellyseerr depend on for basically everything they show, is reachable
  through the app. A failure here usually points at TMDB or connectivity,
  not the app itself.

Jellyseerr is Seerr's Jellyfin-focused fork and shares an identical API, so
both get the exact same checks.

### SSL certificate checks

The first time a service gets a local or remote address starting with
`https://`, an SSL certificate valid check is added automatically. It does
a real, strict certificate check (trust chain, hostname, and expiry, warns
within 14 days of expiring by default), independent of every other check.

This is deliberately decoupled from ordinary checks: `http_200`, the *arr
API checks, and everything else no longer verify certificates at all, so a
self-signed certificate on a local reverse proxy never breaks them. Cert
health is the SSL check's job alone.

### Checking a port-forwarded address

`external_port_open` is a plain TCP connect (open the connection, confirm
it accepted, close it again) to a Static IP or hostname and External port
you type in - not the service's own Local/Remote address above, and not
specific to Plex, though checking Plex's forwarded port (the one set in
Plex's own Settings > Remote Access) is the obvious use for it. Add it to
any service the same way as `filesystem_path` or `ftp_path`.

**Important caveat**: if Checkarr runs on the same network as the service
you're pointing this at (the common case - this container sitting on your
LAN alongside Plex), a FAIL here isn't reliable proof the port is actually
closed to the outside world. Most consumer routers don't support "NAT
hairpin/loopback" - reaching your own public IP from inside your own LAN -
so the connection can fail purely because of that, even though the port is
genuinely open to real outside traffic. A PASS is a much stronger signal
(it means something really is listening on that IP:port from wherever this
container's traffic actually routed through); treat a FAIL as "worth
double-checking from an actual external network or a site like
canyouseeme.org", not as certain. Plex's own `plex_remote_access` check
above doesn't have this problem, since it's plex.tv itself doing the
probing from outside - prefer that one for Plex specifically when you can,
and reach for this one when you want a direct check independent of
plex.tv, or need it for a service that has no such external validator of
its own.

### Per-check poll interval

Every check has an optional interval override in seconds. Leave it blank to
run on every poll of the service, set it higher (e.g. 600) to run that one
check less often than its siblings.

### Alert after (consecutive failures/warns before paging)

Every check also has an "Alert after" count, default 1 (today's behavior:
alert the moment it enters warn/fail). Set it higher to require that many
consecutive polls at the same warn/fail status before a Push Notification
actually goes out - useful for a flaky check that clears itself up within a
poll or two and isn't worth waking anyone up over, without turning the
check off or downgrading its alert level entirely.

This only ever affects the outbound alert. The dashboard, History, and
Notifications tab all still show every result exactly as it happened,
warn/fail badge and all, the moment it happens - nothing about *detecting*
or *displaying* a problem is delayed, only whether Checkarr pages you about
it. A result that didn't yet meet the count gets a small icon next to its
Status badge in History (see Settings.md), the same way an SDT-suppressed
one does, so you can always tell why a given bad result didn't alert.

The count resets whenever the status itself changes - three consecutive
Fails needed to alert, then a Warn in between, means the Fail streak starts
over from zero the next time it fails again, not from wherever it left off.

### Quick-editing checks

Each service's checks are laid out as a table: Enable, Check Type, Name,
Alert level, Edit/Delete. Alert level caps how a failure reports: Warn
downgrades what would otherwise be a Fail for that check to a warning
instead (a brand-new, legitimately-empty Plex/Jellyfin library shouldn't
necessarily page you the same way a dead mount should). It applies to every
check type except the torrent client disk-space checks, whose own warn/fail
thresholds already decide this.

Click the Checks (N) button - its own column in the services table, right
next to Type - to collapse or expand just that service's checks table,
remembered per service in a browser cookie. Add check and, for Plex/
Jellyfin, Scan libraries sit on the service's own row, after Edit/Delete -
they act immediately (no Save Changes needed), same as always.

The Status column is a real toggle, not just a readout - click it to
enable/disable the whole service. Like Enable/Alert level/Delete above,
this doesn't save immediately either: it joins the same unsaved-changes
banner, Save Changes/Discard Changes apply or drop it together with
whatever else is pending.

### Reordering checks

Drag a check by its handle to reorder it within its service, the new order
saves immediately and is reflected in that service's check order on the
dashboard too.

None of Enable, Alert level, or Delete save immediately: deleting a check
just marks its row for deletion, with an Undo button, rather than removing
it outright. An unsaved-changes banner appears as soon as you change
anything, with Save Changes and Discard Changes. Leaving the page with
changes pending prompts you first.


# Push Notifications

Settings > Push Notifications manages outbound alerting channels, a table
of configured channels, Add channel to add one, Edit/Delete per row.

Eight channel types are available, add as many of each as you want (e.g.
one Discord channel for Warn, another for Fail, with different
severity toggles on each):

- **Email (SMTP)**: host, port, optional username/password, STARTTLS
  toggle, From address, and one or more To addresses.
- **Discord**: an incoming webhook URL (Server Settings > Integrations >
  Webhooks on the channel you want alerts in).
- **Slack**: an incoming webhook URL the same way.
- **Telegram**: a bot token (from @BotFather) plus the chat ID to send to.
- **Pushbullet**: an access token (Settings > Account > Create Access
  Token).
- **Pushover**: an application API token plus your user key.
- **Webhook (generic)**: any URL that accepts a JSON POST, for anything
  without a named integration above - Home Assistant, ntfy, n8n, a script
  of your own. Posts `{"subject": "...", "message": "..."}`.
- **Browser**: a native OS notification in any admin browser tab that's
  currently open and connected - see "Browser notifications" below, this
  one works differently from the rest.

Every channel has its own Send for Warn alerts / Send for Fail alerts
toggles, and a Send test button in its edit form. Whichever field is that
channel's actual credential (a webhook URL, a bot token, an access token)
is encrypted at rest the same way API keys are, with the same "Use
environment variable" option; anything else a type needs (a chat ID, a
user key) is stored as plain configuration alongside it, it isn't secret in
the same way.

An alert fires on a check transitioning into warn or fail (not on every
poll while it stays that way, and not on recovery), or a new consolidated
notification from the *arr apps' health feed.

**Alerts are batched.** When the first alert fires, Checkarr holds it for
ten seconds instead of sending immediately. Anything else that fires in
that same window, any service, any check, joins the same batch, and the
notification's subject changes to "Checkarr: Multiple alerts" listing
everything that happened. After the ten seconds, one combined message goes
out and the window closes; the next alert to fire opens a fresh one. This
caps outbound notifications at six a minute even if several services are
flapping at once, so a bad night doesn't also mean your inbox (or your
notification provider's rate limit) has a bad night.

The channel type is deliberately pluggable, adding another alerting
service later is a matter of one more channel type, not a redesign.

### Browser notifications

Unlike every other channel type, Browser doesn't send anywhere external -
when an alert matches an enabled Browser channel, it's pushed live to every
admin tab that's currently open and connected, which then shows it as a
native OS-level notification. There's no address or account to configure,
just this browser.

This is genuinely best-effort, the same way a phone that's locked and
asleep doesn't see a push notification either:

- The connection only exists while an admin tab is open, so a closed
  browser (or one that's lost its connection) simply doesn't get the
  alert - it isn't queued for when the tab reopens.
- Each browser has to grant notification permission separately, once - Add
  or Edit a Browser channel and click "Grant browser notification
  permission". If a browser has already blocked notifications for this
  site, the button won't reappear; allow it again in that browser's own
  site settings first.
- Every other enabled channel still receives the alert as normal
  regardless of whether any tab is connected - Browser is one more
  destination, not a replacement for the others.

### Self-monitoring alerts

Checkarr also watches its own health, checked every 30 minutes alongside
Log & History Pruning (see below), and alerts through the same channels and
the same batching described above:

- **Low disk space on `/config`**: warns under 100 MB free, escalates to
  fail under 10 MB free. Alerts only on the transition into a worse tier
  (or back to fine), not every 30 minutes while it stays low.
- **A notification channel failing to send**: if a channel errors out
  while trying to deliver an alert, Checkarr notices and alerts about it
  through whichever other channels are still working, naming the broken
  one. If you only have one channel and it's the one that's broken, this
  alert has nowhere to go, check the container logs instead.


# Scheduled Down Time

Settings > Scheduled Down Time suppresses Push Notifications alerts during
known-noisy windows (an update, a planned reboot) so they don't page you
the same as a real incident, check results, the Notifications tab, and the
dashboard are all completely unaffected, only the outbound alert is held
back. Two sections:

**Instantly start SDT** is a shortcut for right-now suppression, no form to
fill in: pick a duration (a number plus minutes/hours/days) and it
immediately suppresses both Warn and Fail alerts for every service. While
one is running, a banner takes its place above Service Groups showing a
live countdown, an Extend button (add more time, same duration dialog), and
a Cancel button to end it early. It doesn't appear in the Schedules list
below or count against your saved schedules, it's a separate one-off that
quietly cleans itself up once it ends.

- **Service Groups**: which services a schedule covers. All Services always
  exists and can't be edited or deleted, it covers every service
  automatically. Create your own groups with Add group and a checkbox per
  service.
- **Schedules**: when, how often, and which severities to suppress. Add
  schedule sets a recurrence (Once, Daily, Weekly, Monthly, or Yearly), a
  time window (crossing midnight is fine), an optional repeat-until date,
  and which severities to suppress (at least one required). Times are
  entered and shown in your browser's local time.

  Once saved, a schedule appears as a card with a checkbox per Service
  Group beneath it, check whichever groups it should apply to. A schedule
  applying to no group suppresses nothing.


# Log & History Pruning

Settings > Log & History Pruning controls how long check history sticks
around: delete check history after a number of days (default 7). That's
the only setting, there's no time of day to configure, a background job
simply checks every 30 minutes for anything older than the configured
number of days and deletes it. Prune now runs it immediately, useful for
confirming a new retention value takes effect without waiting for the next
cycle. A "Last pruned" readout shows when it last ran.

This only covers History, the check results stored in the database. There
isn't a separate container log file to prune, Checkarr's own process logs
go straight to stdout the same way any other Docker container's do, and
Docker's own log rotation settings are the right place to manage those if
you need to.


# Dashboard Settings

Settings > Dashboard Settings controls which layout the public dashboard
port (8090) shows, independent of whatever you currently have active in the
admin app:

- **Dashboard to show on Desktop**: which layout a desktop-width visitor to
  port 8090 gets. Only lists your Desktop and Desktop-Compact layouts
  (compact ones are labeled so you can tell them apart) Leave unset to fall
  back to your Desktop pool's All Services.
- **Dashboard to show on Mobile**: which layout a phone-width visitor to
  port 8090 gets. Only lists your Mobile and Mobile-Compact layouts
  (compact ones are labeled so you can tell them apart) Leave unset to fall
  back to your Mobile pool's All Services.

**Public port theme override**: forces port 8090 to always render this
theme. Overriding whichever layout is actually pinned above and that layout's 
own theme entirely. Leave it at "No override" to follow the pinned layout's 
own theme.


## Customizations

Settings > Customizations picks the admin app's overall theme - the whole
app, header included - from four:
Takes effect immediately.



## Security notes

- API keys are encrypted with Fernet before being stored in SQLite, using a
  key from `HC_APP_SECRET_KEY` if set, otherwise a key generated on first
  run and persisted to `/config/secret.key`. Set `HC_APP_SECRET_KEY` and
  back it up, if the generated key file is lost, stored API keys can't be
  decrypted and services will need their keys re-entered. This only applies
  to secrets actually stored in the database, one sourced from an
  environment variable never touches this encryption at all, by design.
- The admin web UI/API (port 8080) has no authentication by default (fine
  on a trusted LAN behind your own reverse proxy/VPN). Set `HC_AUTH_USERNAME`
  and `HC_AUTH_PASSWORD` to require HTTP Basic Auth for it. This does not
  apply to the public dashboard port (8090), which is unauthenticated by
  design, see Public dashboard above.
- Filesystem checks only ever read paths you've explicitly bind-mounted
  read-only, the container does not need write access to your media.
- "Sign in to Plex" never sees your Plex password, it uses Plex's standard
  PIN-based sign-in flow: this app only ever receives the resulting token,
  via a popup hosted on plex.tv itself.

Two internal identifiers kept their old `healthchecker` naming on purpose
rather than being renamed for the sake of it: the SQLite database filename
and the `filesystem_path` check's internal config key. Renaming either
would have made every existing install's database or already-configured
filesystem checks stop working after an upgrade, which is a strange way to
say hello to a new name.
