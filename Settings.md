# Settings and dashboard features

Everything in the Settings tab that isn't adding a service or a check (see
[ConfiguringServices.md](ConfiguringServices.md) for that), plus the
dashboard, History, and Notifications features that live outside Settings
but are configured from it.

## Dashboard layouts

Click "Edit layout" in the top bar to rearrange the dashboard, drag and
resize only work in this mode, so normal day-to-day viewing can't
accidentally bump a card out of place.

Every saved layout belongs to one of four pools - **Desktop**,
**Desktop-Compact**, **Mobile**, and **Mobile-Compact** - and which pool
you're currently editing/viewing determines how editing works:

- **Desktop / Desktop-Compact**: free-form. Drag a card from anywhere on it
  (except the resize handle and its own buttons) to move it anywhere on the
  grid, it snaps to an invisible grid. Drop it on or across other cards and
  whatever's in the way gets pushed out of your way rather than refusing
  the move. Every card has a drag handle in its bottom-right corner, drag
  it to make the card wider or taller.
- **Mobile / Mobile-Compact**: always a single column, one card per row,
  full width, no free-form drag - each card gets Move to top/up/down/to
  bottom buttons instead, and its resize handle only changes height. This
  isn't a narrow-screen fallback view of the same layout your desktop
  edits - it's its own separate saved layout with its own card order,
  never affected by anything you do to a Desktop/Desktop-Compact one.

Sizes and positions save automatically as soon as you release the drag (or
click a reorder button), no separate Save step. Every one of the four pools
always has an "All Services" layout (locked in the dropdown) that always
shows every service, including ones added after the layout was created,
and can't be deleted - every install gets all four the moment it starts up,
nothing to set up first. Any other custom layout only shows the cards
you've explicitly put on it: while editing a custom layout, each card gets
a small remove button next to its status badge, and an Add card dropdown
appears in the top bar. A newly added service only ever appears on All
Services automatically, never inserted into a custom layout behind your
back.

The dropdown in the top bar next to Edit layout holds your saved layouts
**from whichever pool you're currently in** - New saves the current
arrangement as a new layout in that same pool, Rename and Delete act on the
one currently selected (Delete is disabled for All Services), and picking
any layout from the dropdown switches the dashboard to it instantly.

Which of the two *device* pools (Desktop-ish vs Mobile-ish) you're looking
at isn't something you pick - it follows the actual width of whatever
you're viewing it on, automatically, every time the page loads or your
window crosses roughly phone width. Narrow your browser window (or open
the dashboard on a phone) and it switches itself to a Mobile/Mobile-Compact
layout; widen it back out and it switches back - always landing on that
pool's All Services layout unless you've specifically activated a
different one of your own in it. This is also what fixed cards being able
to render partway off the edge of a narrow screen with the rest of the
page scrolling sideways to reach them: a Mobile-pool layout only ever
stores each card's up/down position, never a desktop-shaped horizontal one
that could end up placed past where a narrow screen actually has room.

### Compact view

Next to Edit layout, **Compact view** switches between the compact and
full pool *for whichever device pool you're currently in* - Desktop ⇄
Desktop-Compact, or Mobile ⇄ Mobile-Compact, never crossing between device
pools itself (that half is automatic, see above). A compact layout drops
each card down to just its icon, name, and status badge on one line, then
the uptime history strip on a second, nothing else, no Run now/History
buttons, no type/address/last-checked line, no individual check rows. A
long name that would otherwise run into the status badge fades out
smoothly instead of getting cut off mid-character. Because there's so much
less on a compact card, it can also be resized much smaller than a full
one (on Desktop-Compact; Mobile-Compact cards are always full list-width
either way).

A layout is fixed as compact or not (and Desktop or Mobile) the moment it's
created, never flipped in place afterward - clicking Compact view activates
one of your existing layouts in the other compact-ness within your current
device pool, and the layout dropdown next to it only ever lists layouts
from whichever of the four pools you're currently in. **+ New** always
creates within whichever pool is currently active, so making more compact
layouts later is just Compact view, then + New, same as for full ones.

Useful for a wall-mounted display or anywhere you want "is it up" at a
glance rather than a full breakdown, or just to keep a leaner view of your
services alongside your normal detailed one.

### Dashboard Settings (what the public port shows)

Settings > Dashboard Settings controls which layout the public dashboard
port (8090) shows, independent of whatever you currently have active in the
admin app:

- **Public dashboard layout**: pick any saved layout, from any of the four
  pools. The public port shows this one regardless of what admin is
  actively editing or has switched to, so you can rearrange your own view
  without disturbing what a housemate or a status page pointed at port
  8090 sees. Whether it renders compact simply follows whether the chosen
  layout is one of your compact ones - there's nothing separate to
  configure here for that. A visitor on a phone is the one exception: they
  always get that install's Mobile (or Mobile-Compact, matching whatever
  you picked here) layout instead, the same automatic device-pool
  switching described above - falling back to Mobile's own All Services if
  you haven't specifically pinned one of your own Mobile layouts, but
  never rendered whatever Desktop layout is pinned here.
- **Restrict to compact layouts**: when checked, the dropdown above only
  offers layouts from your compact pools (Desktop-Compact and
  Mobile-Compact), guaranteeing the public dashboard can never accidentally
  get pointed at a full, detailed layout. Leave it unchecked to pick from
  every saved layout, compact or not.

## History

The History tab (admin) and page (public) loads incrementally as you
scroll rather than a single capped fetch, and respects the time range
picked in the top bar down to the minute, not just the hour, so "Last 5
minutes" actually shows five minutes of data instead of quietly rounding up
to an hour. "Just the last poll" is its own special case rather than a
1-minute window (which would come back empty for anything polled less
often than once a minute) - it shows each selected service's most recent
result per check, exactly what the dashboard cards are currently showing.

Every configured service gets its own pill button in a row above the table.
Click one to toggle it on or off - nothing is selected by default, so the
table starts empty and loads nothing until you pick at least one, keeping
the page fast even with a lot of history piled up. Pick more than one and
each row gets a Service column so you can tell them apart.

**Columns** opens a small dialog listing every available column (Time,
Service, Check, Type, Status, Response, Message) with a checkbox and a drag
handle, check to show, drag to reorder, at least one has to stay visible.
The Time column never wraps onto a second line; every other column
truncates with an ellipsis instead of wrapping the row. Drag the edge of a
column header to resize it, both the column set and any manual widths are
remembered.

**Export CSV** downloads every row matching the current service selection
and time range, not just whatever happened to be scrolled into view, using
whichever columns are currently shown, in that order.

## Notifications tab

Shows every check currently sitting in warn or fail, across every service,
with the service's icon and name, the check name, the message it actually
received, and when it was last checked. This is a live view of what's
wrong right now, not a history, once a check recovers it drops off the
list on the next poll. If a whole service goes offline, every check
against it shows up here too, even ones that would otherwise report
through the *arr apps' own health feed, since this reads actual check
results rather than waiting for a service to tell you about itself.

When there's nothing to show, the empty state picks one of a handful of
lines at random each time rather than always saying the same thing.

## Push Notifications

Settings > Push Notifications manages outbound alerting channels, a table
of configured channels, Add channel to add one, Edit/Delete per row.

Today's only channel type is Email (SMTP): host, port, optional
username/password, STARTTLS toggle, From address, and one or more To
addresses. Each channel has its own Send for Warn alerts / Send for Fail
alerts toggles, and a Send test button in its edit form. Passwords are
encrypted at rest the same way API keys are.

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
