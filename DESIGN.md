# StudyRoom – design notes

How StudyRoom works and why it was built this way. Written so that a person or an LLM can understand
and modify the project without other context.

## 1. Goals

- A YPT-style **subject-based study timer** for the Linux desktop, **without** any blocking of apps or
  websites.
- **Study history for all time**, by subject, viewable in the app and stored in a format that is easy to
  analyse later.
- A built-in **deadline tracker**: a colour-coded to-do list plus a calendar of deadlines.
- Feels like a normal desktop app launched from the dock/taskbar.
- Design priority: **functionality > good looks > minimalism**.
- 24-hour time, day/month/year dates (DD/MM/YY; DD/MM/YYYY in calendar views), always from the local
  system clock — never a server.
- Safe to install: per-user only, no root, no system files, never silently deletes user data.

## 2. Architecture

**A standalone native app** (Python + GTK4 + libadwaita via PyGObject) plus an **optional tiny GNOME Shell
extension** that only displays the running timer in the top bar.

Why not build everything as a GNOME Shell extension?
- Shell extensions run *inside* the compositor; a bug can freeze or crash the whole desktop session.
  A normal app window cannot.
- Rich UI (calendar, charts, dialogs) is far easier and safer in a regular app.
- "Launched from the taskbar" is fully met by a pinned `.desktop` launcher.

Why Python + GTK4/libadwaita?
- Ships with GNOME-based distributions: nothing to compile or install, no root.
- Looks native, follows the system light/dark preference, fonts and accessibility settings.

The app runs directly from its folder (`bin/studyroom` adds the folder to `sys.path`). Updating means
`git pull` and reopening the app.

### Modules (`studyroom/`)

| module | responsibility |
|---|---|
| `store.py` | **all** persistence and business logic; a `GObject` that emits `changed(kind)` |
| `app.py` | `Adw.Application`, main window, sidebar, 250 ms tick, background timing, notifications, sound, D-Bus actions |
| `study_page.py` | subjects list, ring timer, start / countdown / pause / stop / discard, subject dialog |
| `deadlines_page.py` | To-do and Calendar views, task/deadline editor |
| `history_page.py` | range selection, stats, charts, breakdown, session list, manual-session dialog |
| `charts.py` | cairo-drawn `StackedBars`, `DayTimeline`, `ShareBar` |
| `settings_page.py` | preferences, top-bar extension switch |
| `theme.py` | stylesheet + themes (libadwaita CSS variable overrides) |
| `timeutil.py` | formatting (DD/MM/YY, HH:MM, durations, "time left") and study-day maths |
| `colors.py` | colour palette and hex helpers |
| `widgets.py` | shared small widgets (colour dot, swatches, tick button, confirm dialog, menus) |

Pages subscribe to `Store.changed` and redraw the parts they own. The `kind` argument
(`subjects | sessions | tasks | deadlines | settings | timer`) limits unnecessary refreshes.

## 3. Data

Folder: `~/.local/share/ypt-study/` (`$XDG_DATA_HOME/ypt-study`). Overridable with the environment
variable `STUDYROOM_DATA_DIR`, which is how tests use a throwaway folder.

| file | purpose |
|---|---|
| `data.json` | subjects, tasks, deadlines, settings |
| `sessions.jsonl` | append-only log, one completed session per line |
| `SESSIONS-FORMAT.md` | field documentation for the log (regenerated on start) |
| `timer.json` | running timer or `{"active": false}`; also read by the top-bar extension |
| `backups/YYYY-MM-DD/` | daily copy of `data.json` + `sessions.jsonl`; newest 30 kept |

**Safety rules**
- Writes are atomic (`.tmp` → `fsync` → `os.replace`); the session log is appended with `fsync`.
- An unreadable `data.json` is copied aside as `data.json.unreadable-<timestamp>` and the newest backup is
  loaded, with a warning. It is never deleted.
- Damaged lines in `sessions.jsonl` are skipped on load, not removed.
- Backup pruning only touches folders named exactly `YYYY-MM-DD` inside the app's own `backups/` folder.
- Every user-initiated deletion (subject, task, deadline, session, discard) asks for confirmation.
  The only automatic deletion is the 14-day removal of completed items, which is a feature and is
  shown in the UI ("Clears in 5d").

**Records**

```
subject   {id, name, color (hex), created}
task      {id, title, color (palette name), notes, done, done_at, created}
deadline  {id, title, date "YYYY-MM-DD", time "HH:MM" | "", color, notes, done, done_at, created}
          (no time = due at 23:59, shown as "End of day")
settings  theme, scheme (system|light|dark), day_start "HH:MM", first_weekday (0 Mon | 6 Sun),
          countdown_minutes, min_session_seconds, countdown_sound, last_subject
```

**Session log line** (chosen to be self-describing for spreadsheets/LLMs, with both ISO and DD/MM/YY forms):

```json
{"id": "…", "subject": "Physics", "subject_id": "…", "color": "#e67c73",
 "mode": "countup", "target_minutes": null,
 "start": "2026-01-18T22:06:39+00:00", "end": "2026-01-18T22:56:49+00:00",
 "study_seconds": 3007, "paused_seconds": 3,
 "study_day": "2026-01-18", "date": "18/01/26", "start_time": "22:06", "end_time": "22:56",
 "manual": false}
```

The subject's name and colour are copied into every session so history survives renames and erasure.

## 4. Timer model

`timer.json`: `{active, subject_id, subject, color, mode "up"|"down", target (s) | null, started_at (epoch),
accum (s), run_start (epoch) | null}`

- `elapsed = accum + (now − run_start if running)`. Pausing folds the current run into `accum` and clears
  `run_start`. Because only timestamps are stored, the time stays correct across app restarts, crashes
  and suspend; the app resumes a running timer on start.
- While a session exists the application calls `hold()`, so closing the window can hide it and keep timing
  in the background (the user is asked: *Keep timing / Stop & save / Cancel*). Launching the app again
  brings the same window back (single instance).
- Stop: `study_seconds = elapsed`, `paused_seconds = (end − start) − study_seconds`.
- A countdown that reaches zero is **always** saved (end time = the exact moment it hit zero), then a
  notification and a sound play. Other sessions shorter than the minimum length (default 1 min) are not saved.
- One session at a time; switching subject requires stopping first (as in YPT).

## 5. Study day

`study_day(t) = date(t − day_start)`. With `day_start = 05:00`, a session started at 02:00 on the 19th
belongs to the 18th. A session is attributed entirely to the day it **started** (not split across the
boundary): simpler, and matches how people think about a late-night session. History recomputes the study
day from `start` using the current setting, so changing the setting re-buckets all sessions consistently.

## 6. Subjects and erasure

Erasing a subject removes it from the list only. History groups sessions by `subject_id` while the subject
exists, and by the recorded `name + colour` once it has been erased, so erased subjects still appear as
normal rows and bars. The subject of the running session cannot be erased.

## 7. UI design

General: `Adw.NavigationSplitView` with a sidebar (Study, Deadlines, History, Settings) that collapses below
820sp; every page has its own header bar; toasts for feedback; `Adw.AlertDialog` for destructive actions.
While a session runs, a small card at the bottom of the sidebar shows the subject and live time.

**Study** — subject list (colour dot, name, today's HH:MM:SS, ⋯ menu: edit, move up/down, erase) on the
left; on the right the date, today's total, and a ring timer. In count-up mode the ring fills once per
hour; in countdown mode it drains to empty; when paused it dims. Idle controls are a large **Start**
(count-up, the default) and a separate **Countdown** button joined to a minutes field, so starting
a countdown needs no extra dialog.

**Deadlines** — header toggle *To-do | Calendar*.
- To-do: quick-add entry and colour picker; a "Due today" section fed from the calendar (ticking it
  completes the deadline); open tasks; a collapsible completed list. Rows have a round tick in the item's
  colour and a 4px coloured left stripe.
- Calendar: 6-week grid (Monday or Sunday first) with up to three coloured chips per day and "+N more";
  today's number in an accent circle. Click selects a day; double-click adds a deadline. The side panel
  shows the selected day, then **Upcoming** (all open deadlines by due time, grouped by month, with
  "2d 4h left" — amber under 24h, red when overdue), then completed deadlines.
- Editor: title, date (DD/MM/YYYY button with a calendar popover), optional 24-hour time, colour swatches,
  notes, delete.
- Colours: the 11 Google-Calendar-style event colours (Tomato, Flamingo, Tangerine, Banana, Sage, Basil,
  Peacock, Blueberry, Lavender, Grape, Graphite), stored by name.

**History** — header toggle *Day | Week | Month | Year | All time*; range label, Today, previous/next
(next is disabled for the future). Four stat cards (Day view replaces "Daily average" with the first
session's start time). Chart: 24-hour timeline for a day; stacked daily bars for week/month; monthly bars
for a year; monthly (or yearly beyond 36 months) bars for all time. Then a per-subject breakdown with
proportional bars and percentages, and the session list (newest first, up to 200 shown per range; totals
and charts always include everything).

Chart rules: thin bars, 2px gaps between stacked segments, 4px rounded tops sitting on the baseline, faint
gridlines, a single y-axis in hours, a legend for every multi-series chart, text in normal text colours
(never in series colours), hover tooltips. Series colours are the user's subject colours, always in the
subject list's order so a subject keeps its place.

**Settings** — light/dark/system; theme grid (each swatch shows the light background, dark background and
accent); study-day start; default countdown; minimum session length; countdown sound; week start;
top-bar timer switch; data folder location.

**Themes** — implemented by overriding libadwaita's CSS variables (`--accent-bg-color`,
`--window-bg-color`, `--view-bg-color`, `--sidebar-bg-color`, `--card-bg-color`, …) on `:root`. Each theme
defines an accent plus one light and one dark tint; the other surfaces are derived by mixing toward white.
The CSS is regenerated whenever light/dark changes (`Adw.StyleManager` `notify::dark`).

## 8. Top-bar timer (GNOME Shell extension)

UUID `studyroom-timer@studyroom.local`, ES-module extension for GNOME Shell 48–51.
- Visible only while a session exists: colour dot (pause icon when paused) + subject + HH:MM:SS
  (remaining time for countdowns).
- Menu: status line, Pause/Resume, Stop & save, Open StudyRoom.
- It **only reads** `timer.json` (directory file monitor plus a 10-second safety re-read) and computes the
  time itself each second. It never writes files.
- Buttons call the app's exported actions over D-Bus (`org.gtk.Actions.Activate` on
  `io.github.studyroom.Studyroom`, path `/io/github/studyroom/Studyroom`; actions `toggle-pause`, `stop`,
  `show`). If the app isn't running it is launched instead.
- Keeping all data ownership in the app avoids write races and keeps the code running inside the shell
  tiny and low-risk.
- Off by default. The Settings switch runs `gnome-extensions enable/disable` and also adds/removes only
  this UUID in `org.gnome.shell enabled-extensions` (on Wayland a newly copied extension is discovered
  only after the next login).

## 9. Install / uninstall

`install.sh` (idempotent, no root): writes the `.desktop` launcher pointing at `bin/studyroom` in the
cloned folder, installs the icon, copies the extension, refreshes desktop/icon caches, and appends the app
to `org.gnome.shell favorite-apps` if missing (existing entries untouched).
`uninstall.sh` lists what it will remove, asks for confirmation, removes only those items and keeps the
user's data.

Naming: the display name is **StudyRoom**; the application ID `io.github.studyroom.Studyroom` is the
`.desktop` name and D-Bus name the dock pin and the extension rely on, so it is kept stable.

## 10. Testing approach

- Data layer tested against a throwaway folder via `STUDYROOM_DATA_DIR`.
- UI tested inside an isolated, invisible GNOME Shell so the developer's real session is never touched:
  `dbus-run-session` (private bus) + `gnome-shell --headless --wayland --virtual-monitor 1280x820`, with
  `GSETTINGS_BACKEND=memory` and all `XDG_*_HOME` folders redirected to a temporary directory. Sample data
  was seeded, each page rendered to PNG in light and dark mode, and the images inspected.
- Verified: count-up, pause/resume, stop; countdown auto-finish and save; short sessions discarded;
  erasing a subject keeps its sessions; manual sessions; theme and day-start changes; resuming a timer
  left running; the extension loads (state ACTIVE, no errors) and its D-Bus pause/stop actions work.
- Not verified visually: the extension's appearance in the top bar (the headless shell does not allow
  screenshots).

## 11. Known limitations / ideas

- Sessions crossing the study-day boundary count fully toward the day they started.
- Tasks have no due date or drag-to-reorder (dated items belong in the calendar).
- One session at a time.
- The History session list shows at most 200 sessions per range.
- No import/export UI and no sync; data is local by design (the JSON files are easy to process).
- No automated test suite in the repository yet.
