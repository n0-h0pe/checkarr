# Dashboard Tab

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

# History

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

# Notifications tab

Shows every check currently sitting in warn or fail, across every service,
with the service's icon and name, the check name, the message it actually
received, and when it was last checked. This is a live view of what's
wrong right now, not a history, once a check recovers it drops off the
list on the next poll. 
If a whole service goes offline, every check
against it shows up here too, even ones that would otherwise report
through the *arr apps' own health feed, since this reads actual check
results rather than waiting for a service to tell you about itself.
