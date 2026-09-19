# Architecture overview

A tour of how Checkarr is put together, for anyone (including future-you)
reading the code cold. The other docs at the repo root ([README.md](README.md),
[ConfiguringServices.md](ConfiguringServices.md), [Settings.md](Settings.md),
[DeployingDocker.md](DeployingDocker.md)) are user-facing - what the app does
and how to run it. This one is developer-facing - how it's built.

## The shape of it

Two ASGI apps, one process, one SQLite database:

- **`app/main.py`** - the admin app (port 8080 by default). Full CRUD,
  settings, everything.
- **`app/public.py`** - a second, deliberately minimal app (port 8090) for
  the read-only public dashboard. It shares the database and query helpers
  with the admin app but never imports anything that can mutate state or
  read a secret - not "hidden from the UI", actually absent from that
  process's route table. A probing request to the public port has nowhere
  to go looking for a services CRUD route or an API key, because there
  isn't one wired up.
- **`app/run.py`** - the actual entrypoint (`python -m app.run`, what the
  Dockerfile runs). Starts both uvicorn servers on one asyncio event loop
  so a single `docker stop` shuts both down together. `HC_PUBLIC_DASHBOARD_ENABLED=false`
  skips building the second server entirely.

Both apps read from the same SQLite file (`app/database.py`'s `engine`,
one file per install, path from `Settings.db_path`). There's no message
queue, no cache layer, no separate worker process - a home-lab monitoring
tool for a handful of services doesn't need one, and every "job" (polling,
pruning, self-monitoring) runs as an APScheduler job inside the admin
app's own event loop (`app/scheduler.py`).

## Directory layout

```
app/
  main.py, public.py, run.py    the two ASGI apps + the process entrypoint
  config.py                     Settings (pydantic-settings, HC_* env vars)
  database.py                   engine/session, create_all, additive migrations
  models.py                     every SQLAlchemy table
  schemas.py                    every pydantic request/response shape
  serializers.py                the handful of ORM->schema mappings too
                                 involved for schema.model_validate() alone
  queries.py                    shared read/singleton-seed helpers used by
                                 both apps and by routers
  security.py                   Fernet encryption, HTTP Basic auth, the
                                 "use environment variable" secret pattern
  poller.py                     the poll loop - the center of the app
  scheduler.py                  APScheduler wiring around poller.py
  alerting.py                   outbound alert batching/dispatch
  downtime.py                   Scheduled Down Time suppression logic
  housekeeping.py               the 30-minute self-upkeep job (disk space,
                                 failing notification channels)
  log_pruning.py                check history retention, its own 6-hour job
  library_scan.py               Plex/Jellyfin "Scan libraries"
  connection_test.py            the Add Service "Test connection" probe
  plex_client.py, jellyfin_client.py
                                 small per-app auth helpers shared by
                                 multiple checks

  checks/                       one module per check *type*, dispatched by
                                 runner.py (see "Checks" below)
  notifiers/                    one module per notification channel *type*,
                                 dispatched by alerting.py
  routers/                      one module per admin API resource, each a
                                 FastAPI APIRouter mounted in main.py

  static/js/common.js           shared rendering, used by both frontends
  static/js/app.js              admin-only: everything that mutates state
  static/js/public.js           public-only: thin init/polling glue
  static/css/style.css          one stylesheet, both apps, theme variables
  templates/index.html          admin shell
  templates/public.html         public shell (one template, three pages -
                                 see the `page` Jinja variable)
```

## Data model

Everything lives in `app/models.py`. The load-bearing tables:

- **`Service`** - one row per monitored app (Radarr, Plex, a generic HTTP
  thing, whatever). Holds its address(es), credentials (encrypted or an
  env-var name, never both), and an `icon_type`/`icon_value` pair for the
  custom icon picker.
- **`CheckDefinition`** - one row per check attached to a service. `type`
  selects which function in `checks/` runs it (see below); `config` is a
  schema-free JSON blob whose shape is entirely up to that check type -
  this is why adding a new check type never needs a migration for its own
  settings, just a new key convention documented in its `CHECK_TYPE_META`
  entry (`routers/meta.py`).
- **`CheckResult`** - one row per (check, poll). This is History. Two
  columns worth knowing about because they're *not* what they look like at
  first glance: `in_sdt` and `suppressed_by_threshold` are both recorded
  **once, permanently, at poll time** - not derived later from whatever
  Scheduled Down Time schedules or "Alert after" counts happen to be
  configured when someone views History. That's deliberate: an Instant SDT
  window gets deleted once it ends (see `routers/downtime.py`'s reaping),
  and a live re-derivation would silently lose the historical truth the
  moment that happens. Recording it once at the moment it was actually
  true is the whole point.
- **`DashboardLayout`** - a named, saveable card arrangement. Split into
  four independent pools by `(is_mobile, is_compact)`, each with its own
  protected `is_default` "All Services" layout. `sizes` is a JSON blob
  keyed by service id holding each card's `{x, y, w, h}` *and* two
  per-card extras that live in the same blob rather than earning their own
  columns: `bars` (uptime strip bar count) and nothing else yet - the
  pattern to follow if a future per-card setting shows up. `theme` is a
  real column, not part of `sizes`, since it's a property of the whole
  layout, not one card.
- **`NotificationChannel`** - one row per outbound alert destination.
  Deliberately generic: `type` + a JSON `config` + exactly *one* secret
  slot (`secret_encrypted`/`secret_env_var`). Every channel type funnels
  its one real credential (a webhook URL, a bot token) into that one slot
  and puts everything else (a chat ID, a user key) in `config` - see
  `routers/meta.py`'s `NOTIFICATION_CHANNEL_TYPE_META` comment for why.
- **`DashboardSettings`, `UiSettings`, `LogPruningSettings`,
  `SelfMonitoringState`** - singleton rows (exactly one ever exists),
  each seeded by a `get_or_create_*` helper in `queries.py`, called once at
  startup (`database.init_db`) and read on demand everywhere else.
- **`DowntimeSchedule`, `ServiceGroup`** - Scheduled Down Time's own model,
  covered in its own section below.

### The additive-migration convention

There's no Alembic, no migration files - `database._run_migrations()` is a
flat list of `if "column" not in existing_columns: ALTER TABLE ... ADD COLUMN`
checks, run on every startup. **Columns are never dropped or renamed.** A
retired column gets left in place, unused, with a comment explaining why -
search `models.py` for "retired" to see the pattern. This is the rule to
follow for any new column: add the field to the model, add the matching
`ALTER TABLE` guard in `database.py`, never touch what's already there. A
brand new *table* needs no migration at all - `Base.metadata.create_all()`
handles it for every install, new or upgrading, since a table that never
existed can't have missing columns.

## The poll cycle (`poller.py`)

This is the one function worth reading start to finish before touching
anything else: `poll_service(service_id)`. Runs on a per-service
APScheduler interval (`scheduler.schedule_service`), once per service, and
for one poll:

1. Loads the service and its enabled checks; skips any check whose own
   interval override hasn't elapsed yet (`_due_checks`).
2. Builds a list of (check, target) jobs - most checks run once per
   configured address, some (`SERVICE_SCOPED_TYPES` in `checks/runner.py`)
   run once regardless of address, `ssl_certificate` runs once per
   `https://` address specifically.
3. Runs every job concurrently (`asyncio.gather`) through one shared
   `httpx.AsyncClient`, dispatched by `checks.runner.run_check` - a plain
   `if ctype == "...": return await check_fn(...)` chain, not a registry
   dict, so a new check type is exactly one new `elif` branch plus a new
   function in `checks/`.
4. For each result: applies "Alert level" (an optional Fail->Warn
   downgrade from the check's own `config`), computes `in_sdt` and
   `suppressed_by_threshold` (see below), decides whether to queue an
   alert, and writes one `CheckResult` row - always, regardless of whether
   an alert fires. The dashboard/History/Notifications tab read
   `CheckResult` directly; they have no concept of "was this alerted",
   only "what happened".
5. Commits everything in one transaction, *then* fires queued alerts - so
   a rolled-back poll can never send a false alert.

### Alert gating: two independent, stackable reasons not to alert

A warn/fail result can fail to alert for either (or both) of two
unrelated reasons, each recorded as its own permanent boolean on
`CheckResult`:

- **Scheduled Down Time** (`in_sdt`, via `downtime.is_suppressed`) - a
  human said "don't page me about this right now". Checked here purely
  for the audit trail; the *actual* gate is a second `is_suppressed` call
  right before `queue_alert` at the very end of `poll_service`, after the
  DB commit.
- **Consecutive-count threshold** (`suppressed_by_threshold`, via each
  check's own `config.alert_after_count`, default 1) - not enough
  identical bad results in a row *yet*. `poll_service` computes the
  current streak by walking backward through just enough prior
  `CheckResult` rows (`limit(threshold)`) to tell "streak length is
  exactly N" from "already past N" - it alerts only in the first case,
  which is what makes this "alert once per streak" instead of "alert
  every poll once flaky enough".

Both flags feed History's icons (`sdtIcon`/`thresholdIcon` in
`common.js`) and CSV export - the point of recording them permanently
instead of deriving them live is that they stay true forever, even after
the SDT schedule that caused one is long deleted.

## Checks (`app/checks/`)

Each module is one or a few related check *implementations* - plain async
functions taking whatever they need (an `httpx.AsyncClient`, a base URL, an
API key, that check's own `config` dict) and returning a `CheckOutcome`
(`checks/base.py`: status + message + response time + optional
`Notification` items for the *arr health-feed pass-through). `checks/runner.py`
is the only place that knows how to route a `CheckDefinition.type` string
to the right function, and also owns:

- `default_checks_for_service_type()` - what gets auto-created when a
  service is added.
- `TARGET_SCOPED_TYPES` / `SERVICE_SCOPED_TYPES` / `ALWAYS_BOTH_TARGETS_TYPES` -
  which checks care about local vs. remote address at all.

To add a new check type: write the function in the right module (or a new
one), add one dispatch line in `run_check`, add one entry to
`CHECK_TYPE_META` in `routers/meta.py` (this is what renders its config
fields in the Add/Edit Check modal - see `renderDynamicFields` in
`app.js`), and add it to `schemas.CHECK_TYPES`.

## Alerting (`app/alerting.py` + `app/notifiers/`)

`poller.py` (and `housekeeping.py`, for self-monitoring alerts) never send
anything directly - they call `queue_alert(tier, subject, body)`, which
holds the first alert for a 10-second window and folds in anything else
that fires in that window into one combined send (so a service tripping
five checks at once, or flapping, sends one message, not five). After the
window, `dispatch_alert` fans out to every enabled `NotificationChannel`
whose `notify_on_warn`/`notify_on_fail` matches the tier, via
`alerting._SENDERS` - a `{type: function}` dict, one entry per module in
`notifiers/`. Adding a new channel type is: write `send_x(channel, subject,
body)` in a new `notifiers/x.py`, add it to `_SENDERS`, add its config
shape to `NOTIFICATION_CHANNEL_TYPE_META` in `routers/meta.py`, add it to
`schemas.NOTIFICATION_CHANNEL_TYPES`.

`notifiers/browser.py` is the odd one out - it doesn't call an external
API at all, it publishes to an in-process pub/sub of Server-Sent-Events
subscribers (`routers/notification_channels.py`'s `/stream` endpoint),
since the "destination" is literally whichever admin browser tabs are
currently connected. Worth reading once as an example of bridging a
worker-thread call (`send_via_channel` runs off the event loop, same as
every other notifier) back into asyncio via `loop.call_soon_threadsafe` -
the one place in this codebase that pattern shows up.

## Scheduled Down Time (`app/downtime.py` + `routers/downtime.py`)

Two concepts: a **Service Group** (which services a schedule covers -
`ServiceGroup`/`ServiceGroupMember`) and a **Schedule** (`DowntimeSchedule`
- when, how often, which severities). `downtime.is_suppressed(db,
service_id, tier, now)` is the one function everything else calls; it's
pure and read-only, no state mutation, safe to call as many times as
needed (poller.py calls it twice per alert-worthy result, once for the
audit trail and once for the real dispatch gate). An "Instant SDT" is just
a `DowntimeSchedule` row with `is_instant=True` and `recurrence="once"`,
created and later deleted (reaped) by `routers/downtime.py` - it has no
special-cased suppression logic of its own, `is_suppressed` doesn't know
or care that it's "instant".

## Frontend

Vanilla JS, no build step, no framework. Three files:

- **`common.js`** - shared between both apps. Owns dashboard rendering
  (cards, drag/resize math, the uptime strip), History rendering, the
  `api()` fetch wrapper, the `el()` DOM-builder helper, and theme
  application. The rule that keeps this file safe for the public app to
  load: nothing in here ever assumes a mutation endpoint exists - every
  write path is passed in as a callback (`onLayoutChange`, `onRunNow`,
  etc.) from whichever app actually wired one up, defaulting to inert if
  not.
- **`app.js`** - admin only. Every CRUD flow, every settings panel,
  Save/Discard Changes staging (`pendingCheckChanges`/`pendingServiceChanges`/
  `pendingCheckDeletions` - nothing except an explicit Save actually calls
  a write endpoint), the theme pickers.
- **`public.js`** - ~45 lines. Calls `loadMeta()` then, depending on
  `window.PUBLIC_PAGE` (set inline by `public.html`), one of
  `loadDashboard()`/`loadHistoryTab()`/`loadNotifications()` from
  `common.js`, on a polling interval. That's the entire public app's own
  logic - everything else is common.js doing the same rendering it does
  for admin.

State lives in one plain object, `state` (declared in `common.js`), shared
by reference across all three files - `state.services`, `state.activeLayout`,
`state.meta` (the `/api/meta` payload: service/check-type catalogs, icons,
build info), etc. No reactivity system; a mutation is always followed by
an explicit re-render call.

### The `el()` helper and why there's no XSS here

```js
function el(tag, attrs = {}, children = []) { ... }
```

`{text: "..."}` sets `textContent`; string children become `createTextNode`s.
**No path in the app ever assigns user-controlled data via `innerHTML`.**
The only `innerHTML` assignments in the whole frontend are `= ""` (clearing
a container) or a hardcoded SVG icon constant. A custom-uploaded icon is
always rendered as `<img src>`, never injected inline, for the same reason.
Keep it that way - it's a deliberate invariant, not an accident.

## Theming

Four palettes, defined once as CSS custom properties in `style.css`
(`html[data-theme="X"]`), reused for a *layout's own* theme via a second,
narrower selector (`#tab-dashboard[data-layout-theme="X"]`). Three
resolution layers, each independent:

- **Settings > Customizations** (`UiSettings.theme`) - the admin app's own
  chrome (header/nav), always, full stop. Rendered server-side into
  `<html data-theme>` on `main.py`'s `index()` route so there's no flash
  of the wrong theme.
- **A dashboard layout's own theme** (`DashboardLayout.theme`, always one
  of the four, no "inherit" state) - scoped to `#tab-dashboard` alone on
  admin (`applyActiveLayoutTheme` in `common.js`), so switching layouts
  never touches the header.
- **Public port theme override** (`DashboardSettings.public_theme_override`,
  optional) - when set, wins outright over whatever the public dashboard
  would otherwise show. `queries.resolve_public_theme` is the one function
  that knows this precedence; both the server-rendered page and the
  client-side post-load correction (`/api/theme`, public-only) call it, so
  the frontend never has to reimplement the rule.

Why a plain CSS variable re-declared at a narrower scope wasn't quite
enough on its own: a property like `color` that's only ever *explicitly*
set once (on `body`) doesn't get re-evaluated just because a descendant
re-scopes the custom property it references - inheritance passes the
already-computed value down, not the `var()` expression. `#tab-dashboard`
restates both `background` and `color` itself for exactly this reason; see
the comment above it in `style.css` if this needs touching again.

## Secrets

Every credential field (a service's API key, a notification channel's
token) follows the same pattern (`security.py`):

- Stored encrypted at rest (Fernet, key from `HC_APP_SECRET_KEY` or a
  generated `/config/secret.key`), **or**
- Sourced from an environment variable by name, never both at once.

`apply_secret_field()` enforces the "at most one populated" rule on
write; `resolve_secret()` reads whichever mode is active on demand,
env-var lookups always fresh (never cached). A field in this mode is
never echoed back in plaintext - only a `has_secret: bool` and, if
applicable, the env var *name*.

## Testing this project

There's no automated test suite. The convention used throughout
development (see recent commit messages for examples) is: a throwaway
venv, a real server boot on scratch ports, `curl`/browser-tool
verification of the actual behavior, an additive-migration test for any
new/changed column (simulate the old schema, run `init_db()`, assert the
new column exists and old data survived), then a clean-venv import check
before shipping. All scratch artifacts get deleted afterward - nothing
like `.venv_test` or `localtestdata/` belongs in a commit.
