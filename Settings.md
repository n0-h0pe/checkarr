# Settings and dashboard features

Everything in the Settings tab that isn't adding a service or a check (see
[ConfiguringServices.md](ConfiguringServices.md) for that), plus the
dashboard, History, and Notifications features that live outside Settings
but are configured from it.

## Dashboard layouts

Click "Edit layout" in the top bar to rearrange the dashboard, drag and
resize only work in this mode.
Every saved layout belongs to one of four pools - **Desktop**,
**Desktop-Compact**, **Mobile**, and **Mobile-Compact** - and which pool
you're currently editing/viewing determines how editing works:

- **Desktop / Desktop-Compact**: free-form. Drag a card from anywhere on it
  (except the resize handle and its own buttons) to move it anywhere on the
  grid, it snaps to an invisible grid. Drop it on or across other cards and
  whatever's in the way gets pushed out of your way. Every card has a drag
  handle in its bottom-right corner, drag it to make the card wider or taller.
- **Mobile / Mobile-Compact**: always a single column, one card per row,
  full width, no free-form drag - each card gets Move to top/up/down/to
  bottom buttons instead, and its resize handle only changes height. This
  isn't a narrow-screen fallback view of the same layout your desktop
  edits - it's its own separate saved layout with its own card order,
  never affected by anything you do to a Desktop/Desktop-Compact one.

Sizes and positions save automatically as soon as you release the drag (or
click a reorder button). Every one of the four pools always has an
"All Services" layout that always shows every service. Any other custom
layout only shows the cards you've explicitly put on it: while editing a 
custom layout, each card gets a small remove button next to its status badge, 
and an Add card dropdown appears in the top bar.

The dropdown in the top bar next to Edit layout holds your saved layouts
**from whichever pool you're currently in** - New saves the current
arrangement as a new layout in that same pool, Rename and Delete act on the
one currently selected, and picking any layout from the dropdown switches 
the dashboard.

Which of the two *device* pools (Desktop vs Mobile) you're looking
at isn't something you pick - it follows the actual width of whatever
you're viewing it on, automatically, every time the page loads or your
window crosses roughly phone width.

### Compact view

Next to Edit layout, **Compact view** switches between the compact and
full pool *for whichever dashboard pool you're currently in* - Desktop ⇄
Desktop-Compact, or Mobile ⇄ Mobile-Compact. A compact layout drops
each card down to just its icon, name, and status badge on one line, then
the uptime history strip on a second, nothing else. Because there's so much
less on a compact card, it can also be resized much smaller than a full
one.

A layout is fixed as compact or not (and Desktop or Mobile) the moment it's
created, never flipped in place afterward - clicking Compact view activates
one of your existing layouts in the other compact-ness within your current
dashboard pool.

### Uptime bars per card

In edit mode, a small **Bars** field sits directly above every card's
uptime strip - how many bars that specific card's strip is divided into,
for every ranged option in the uptime/History picker ("Last 5 minutes"
through "Last 1 week"). A card's own current width caps how high this can be set

### Layout theme

The **Theme** dropdown in the top bar sets this specific layout's own theme. 
There's no "inherit the admin theme" option: every layout always has one of 
the four picked explicitly, Dark being what a newly created layout starts with.

On the admin app this is deliberately narrow: only the dashboard tab's own
background, text, and cards switch, the header and nav bar stay on
whatever Settings > Customizations is set to, regardless of which layout
(or its theme) you're currently looking at. 
The public dashboard theme simply is the whole page's look, 
unless Dashboard Settings' "Public port theme override" is set (see
below), which wins outright over any layout's own theme.

### Dashboard Settings (what the public port shows)

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

## History

The History tab (admin) and page (public) loads all poll results for the selected
filters for the time range picked in the top bar down to the minute.

Every configured service gets its own pill button in a row above the table.
Click one to toggle it on or off. Pick more than one and each row gets a Service 
column so you can tell them apart.

A second row of pills right below it - **OK / Warn / Fail** - filters by
result severity the same way, toggle any combination on or off.

A warn/fail row that happened while its service was covered by an active
Scheduled Down Time schedule gets a small bell-with-a-slash icon next to
its Status badge

A separate small repeat-arrows icon appears the same way whenever a
warn/fail row's own check has an "Alert after" count above 1 (see
ConfiguringServices.md) and this particular result hadn't reached that
count yet, so no alert went out for it.

**Export CSV** downloads every row matching the current service/severity
selection and time range, using whichever columns are currently shown, in that order.
The CSV includes "In SDT" and "Alert Threshold Suppressed" TRUE/FALSE columns too.

## Notifications tab

Shows every check currently sitting in warn or fail, across every service,
with the service's icon and name, the check name, the message it actually
received, and when it was last checked. This is a live view of what's
wrong right now, not a history, once a check recovers it drops off the
list on the next poll. 
If a whole service goes offline, every check
against it shows up here too, even ones that would otherwise report
through the *arr apps' own health feed, since this reads actual check
results rather than waiting for a service to tell you about itself.

## Push Notifications

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

## Scheduled Down Time

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

## Log & History Pruning

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

## Public dashboard

A second, minimal web app runs on its own port (8090 inside the container)
purpose-built to be exposed externally without the risk that comes with
exposing the full admin app:

- Just the dashboard (see Dashboard Settings above for which layout and
  whether it's compact), no top bar, no nav, no settings.
- Two unlinked-from-the-page-but-reachable pages at `/history` and
  `/notifications`, tiny links in the bottom-right corner of the dashboard.
- No mutating routes exist on this port at all, it's a separate app that
  only ever imports read-only query code. There's no services route to
  find here even if you go looking, and no API keys are ever sent to any
  client on this port.
- No login by default, if you want one, put it behind your reverse
  proxy/VPN, same as anything else you expose.

Runs by default, set `HC_PUBLIC_DASHBOARD_ENABLED=false` to turn it off
entirely.

## Secrets from environment variables

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
