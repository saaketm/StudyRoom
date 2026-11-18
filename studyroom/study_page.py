"""Study space: subjects on the left, the timer on the right."""
import math

from gi.repository import Adw, Gtk

from . import timeutil as tu
from .colors import hex_to_rgb
from .widgets import ColorDot, SubjectColorPicker, clear, confirm, label, popover_menu


class TimerRing(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_content_width(300)
        self.set_content_height(300)
        self.fraction = 0.0
        self.color = "#888888"
        self.paused = False
        self.set_draw_func(self._draw)

    def update(self, fraction, color, paused):
        self.fraction, self.color, self.paused = fraction, color, paused
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        fg = self.get_color()
        r = min(w, h) / 2 - 10
        cx, cy = w / 2, h / 2
        cr.set_line_width(10)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.08)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        if self.fraction > 0:
            rr, gg, bb = hex_to_rgb(self.color)
            cr.set_source_rgba(rr, gg, bb, 0.45 if self.paused else 1.0)
            cr.set_line_cap(1)  # round
            a0 = -math.pi / 2
            cr.arc(cx, cy, r, a0, a0 + 2 * math.pi * min(self.fraction, 0.9999))
            cr.stroke()


class SubjectDialog(Adw.Dialog):
    def __init__(self, store, subject=None):
        super().__init__(title="Edit subject" if subject else "New subject", content_width=480)
        self.store, self.subject = store, subject
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._save)
        hb.pack_start(cancel)
        hb.pack_end(self.save_btn)
        tv.add_top_bar(hb)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=12, margin_bottom=24,
                      margin_start=18, margin_end=18)
        grp = Adw.PreferencesGroup()
        self.name = Adw.EntryRow(title="Name")
        self.name.set_text(subject["name"] if subject else "")
        self.name.connect("changed", lambda *_: self.save_btn.set_sensitive(bool(self.name.get_text().strip())))
        self.name.connect("entry-activated", self._save)
        grp.add(self.name)
        box.append(grp)
        box.append(label("Colour", css=("heading",)))
        self.picker = SubjectColorPicker(subject["color"] if subject else "#039be5")
        box.append(self.picker)
        tv.set_content(box)
        self.set_child(tv)
        self.save_btn.set_sensitive(bool(self.name.get_text().strip()))
        self.set_focus(self.name)

    def _save(self, *_):
        name = self.name.get_text().strip()
        if not name:
            return
        if self.subject:
            self.store.update_subject(self.subject["id"], name, self.picker.color)
        else:
            s = self.store.add_subject(name, self.picker.color)
            if not self.store.timer:
                self.store.set("last_subject", s["id"])
        self.close()


class StudyPage(Gtk.Box):
    title = "Study"

    def __init__(self, win, store):
        super().__init__()
        self.win, self.store = win, store
        self.today_cache = {}   # key -> seconds today (saved sessions only)
        self.selected = store.get("last_subject")
        self.header_end = []

        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add subject")
        add.connect("clicked", lambda *_: SubjectDialog(store).present(win))
        self.header_start = [add]

        # ---------------- left: subjects
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=300,
                       margin_top=12, margin_bottom=12, margin_start=12, margin_end=6)
        left.append(label("SUBJECTS", css=("section-title", "dim-label"), margin_start=6))
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("boxed-list")
        self.list.connect("row-activated", self._row_activated)
        self.empty = Adw.StatusPage(icon_name="list-add-symbolic", title="No subjects yet",
                                    description="Add a subject to start timing.")
        self.empty.add_css_class("compact")
        b = Gtk.Button(label="Add subject", halign=Gtk.Align.CENTER)
        b.add_css_class("pill")
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda *_: SubjectDialog(store).present(win))
        self.empty.set_child(b)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        lb_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lb_wrap.append(self.list)
        lb_wrap.append(self.empty)
        sc.set_child(lb_wrap)
        left.append(sc)
        self.append(left)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # ---------------- right: timer
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, hexpand=True,
                        valign=Gtk.Align.CENTER, margin_top=24, margin_bottom=24)
        self.date_lbl = label(css=("dim-label",), xalign=0.5)
        self.total_lbl = label(css=("today-total",), xalign=0.5)
        right.append(self.date_lbl)
        tbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER)
        tbox.append(self.total_lbl)
        tbox.append(label("STUDIED TODAY", css=("section-title", "dim-label"), xalign=0.5))
        right.append(tbox)

        ov = Gtk.Overlay(halign=Gtk.Align.CENTER, margin_top=6)
        self.ring = TimerRing()
        ov.set_child(self.ring)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER,
                         valign=Gtk.Align.CENTER)
        subj_box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.subj_dot = ColorDot(size=10)
        self.subj_lbl = label(css=("heading",))
        self.subj_lbl.set_ellipsize(3)
        self.subj_lbl.set_max_width_chars(18)
        subj_box.append(self.subj_dot)
        subj_box.append(self.subj_lbl)
        self.time_lbl = label("00:00:00", css=("timer-big",), xalign=0.5)
        self.mode_lbl = label(css=("timer-sub", "dim-label"), xalign=0.5)
        center.append(subj_box)
        center.append(self.time_lbl)
        center.append(self.mode_lbl)
        ov.add_overlay(center)
        right.append(ov)

        self.controls = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, halign=Gtk.Align.CENTER,
                                  margin_top=8)
        idle = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        self.start_btn = Gtk.Button(tooltip_text="Start counting up")
        self.start_btn.set_child(Adw.ButtonContent(icon_name="media-playback-start-symbolic", label="Start"))
        for c in ("pill", "suggested-action", "big-pill"):
            self.start_btn.add_css_class(c)
        self.start_btn.connect("clicked", lambda *_: self._start("up"))
        idle.append(self.start_btn)
        cd = Gtk.Box(valign=Gtk.Align.CENTER)
        cd.add_css_class("linked")
        self.cd_btn = Gtk.Button(tooltip_text="Start a countdown of this many minutes")
        self.cd_btn.set_child(Adw.ButtonContent(icon_name="preferences-system-time-symbolic", label="Countdown"))
        self.cd_btn.connect("clicked", lambda *_: self._start("down"))
        self.cd_spin = Gtk.SpinButton.new_with_range(1, 600, 5)
        self._cd_default = store.get("countdown_minutes")
        self.cd_spin.set_value(self._cd_default)
        self.cd_spin.set_tooltip_text("Countdown length (minutes)")
        self.cd_spin.connect("activate", lambda *_: self._start("down"))
        cd.append(self.cd_btn)
        cd.append(self.cd_spin)
        cd_wrap = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        cd_wrap.append(cd)
        cd_wrap.append(label("min", css=("dim-label",)))
        idle.append(cd_wrap)
        self.controls.add_named(idle, "idle")

        running = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.pause_btn = Gtk.Button()
        for c in ("pill", "big-pill"):
            self.pause_btn.add_css_class(c)
        self.pause_btn.connect("clicked", lambda *_: self.toggle_pause())
        stop = Gtk.Button(tooltip_text="Stop and save this session")
        stop.set_child(Adw.ButtonContent(icon_name="media-playback-stop-symbolic", label="Stop"))
        for c in ("pill", "destructive-action", "big-pill"):
            stop.add_css_class(c)
        stop.connect("clicked", lambda *_: self.win.app.stop_session())
        discard = Gtk.Button(label="Discard", tooltip_text="End without saving", valign=Gtk.Align.CENTER)
        discard.add_css_class("flat")
        discard.connect("clicked", self._discard)
        running.append(self.pause_btn)
        running.append(stop)
        running.append(discard)
        self.controls.add_named(running, "running")
        right.append(self.controls)
        self.hint = label(css=("dim-label", "caption"), xalign=0.5)
        right.append(self.hint)
        self.append(right)

        store.connect("changed", self._changed)
        self.rebuild()

    # ------------------------------------------------------------ data
    def _today_range(self):
        d = tu.study_day(tu.now(), self.store.get("day_start"))
        return d, *tu.day_bounds(d, self.store.get("day_start"))

    def _recompute_today(self):
        _d, a, b = self._today_range()
        self.today_cache = {}
        for s in self.store.sessions:
            if a <= s["_start"] < b:
                k = self.store.session_key(s)
                self.today_cache[k] = self.today_cache.get(k, 0) + s["study_seconds"]
        self._today_day = _d

    def _changed(self, _s, kind):
        if kind in ("subjects", "sessions", "timer", "settings"):
            if kind == "settings" and not self.store.timer and self.store.get("countdown_minutes") != self._cd_default:
                self._cd_default = self.store.get("countdown_minutes")
                self.cd_spin.set_value(self._cd_default)
            self.rebuild()

    def rebuild(self):
        st = self.store
        self._recompute_today()
        if st.timer:
            self.selected = st.timer["subject_id"]
        if not st.subject(self.selected):
            self.selected = st.subjects[0]["id"] if st.subjects else None
        clear(self.list)
        self.row_time = {}
        for s in st.subjects:
            row = Gtk.ListBoxRow()
            row.sid = s["id"]
            box = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=12, margin_end=6)
            box.append(ColorDot(s["color"], 14))
            nm = label(s["name"], hexpand=True)
            nm.set_ellipsize(3)
            box.append(nm)
            t = label(tu.clock(self.today_cache.get(s["id"], 0)), css=("tnum", "dim-label"))
            self.row_time[s["id"]] = t
            box.append(t)
            running = st.timer and st.timer["subject_id"] == s["id"]
            items = [("Edit…", lambda s=s: SubjectDialog(st, s).present(self.win), False),
                     ("Move up", lambda s=s: st.move_subject(s["id"], -1), False),
                     ("Move down", lambda s=s: st.move_subject(s["id"], 1), False)]
            if not running:
                items.append(("Erase subject…", lambda s=s: self._erase(s), True))
            box.append(popover_menu(items))
            row.set_child(box)
            if running:
                row.add_css_class("subject-row-running")
            self.list.append(row)
            if s["id"] == self.selected:
                self.list.select_row(row)
        self.list.set_visible(bool(st.subjects))
        self.empty.set_visible(not st.subjects)
        self.controls.set_visible_child_name("running" if st.timer else "idle")
        self.tick()

    def _erase(self, s):
        n = sum(1 for x in self.store.sessions if x.get("subject_id") == s["id"])
        confirm(self.win, f"Erase “{s['name']}”?",
                f"The subject is removed from this list. Its {n} past session{'s' if n != 1 else ''} "
                "stay in your history exactly as they are.", "Erase",
                lambda: self.store.erase_subject(s["id"]))

    def _row_activated(self, _lb, row):
        if self.store.timer:
            if row.sid != self.store.timer["subject_id"]:
                self.win.toast("Stop the current session to switch subjects")
            self.rebuild()
            return
        self.selected = row.sid
        self.store.set("last_subject", row.sid)
        self.tick()

    # ------------------------------------------------------------ actions
    def _start(self, mode):
        if not self.store.subject(self.selected):
            self.win.toast("Add or pick a subject first")
            return
        target = int(self.cd_spin.get_value()) * 60 if mode == "down" else None
        self.store.start_timer(self.selected, mode, target)

    def toggle_pause(self):
        if self.store.timer_running():
            self.store.pause_timer()
        else:
            self.store.resume_timer()

    def _discard(self, *_):
        confirm(self.win, "Discard this session?", "The time of this session will not be saved.", "Discard",
                lambda: self.store.stop_timer(save=False))

    # ------------------------------------------------------------ ticking
    def tick(self):
        st = self.store
        n = tu.now()
        d, _a, _b = self._today_range()
        if getattr(self, "_today_day", None) != d:
            self._recompute_today()
        t = st.timer
        elapsed = st.timer_elapsed()
        live = int(elapsed) if t else 0
        total = sum(self.today_cache.values()) + live
        self.date_lbl.set_label(f"{tu.WEEKDAYS_LONG[n.weekday()]} · {tu.ddmmyy(d)}")
        self.total_lbl.set_label(tu.clock(total))
        self.total_lbl.set_tooltip_text("Studied today")
        if t:
            sid = t["subject_id"]
            if sid in self.row_time:
                self.row_time[sid].set_label(tu.clock(self.today_cache.get(sid, 0) + live))
            sub = st.subject(sid)
            color = sub["color"] if sub else t["color"]
            self.subj_dot.set_color(color)
            self.subj_lbl.set_label(sub["name"] if sub else t["subject"])
            paused = not st.timer_running()
            if t["mode"] == "down":
                rem = max(0, t["target"] - elapsed)
                self.time_lbl.set_label(tu.clock(rem))
                self.mode_lbl.set_label(("Paused · " if paused else "") + f"Countdown · {tu.dur(t['target'])}"
                                        + f" · {tu.dur(elapsed)} done")
                self.ring.update(rem / t["target"] if t["target"] else 0, color, paused)
            else:
                self.time_lbl.set_label(tu.clock(elapsed))
                self.mode_lbl.set_label(("Paused · " if paused else "") + "Since "
                                        + tu.hhmm(tu.from_ts(t["started_at"])))
                self.ring.update((elapsed % 3600) / 3600 or (0.0001 if elapsed else 0), color, paused)
            self.pause_btn.set_child(Adw.ButtonContent(
                icon_name="media-playback-start-symbolic" if paused else "media-playback-pause-symbolic",
                label="Resume" if paused else "Pause"))
            self.time_lbl.set_opacity(0.55 if paused else 1)
            self.hint.set_label("The ring fills once per hour" if t["mode"] == "up" else "")
        else:
            sub = st.subject(self.selected)
            self.subj_dot.set_color(sub["color"] if sub else "#888888")
            self.subj_lbl.set_label(sub["name"] if sub else "No subject")
            self.time_lbl.set_label("00:00:00")
            self.time_lbl.set_opacity(1)
            self.mode_lbl.set_label("Ready")
            self.ring.update(0, "#888888", False)
            self.start_btn.set_sensitive(bool(sub))
            self.cd_btn.set_sensitive(bool(sub))
            self.hint.set_label("Start counts up · Countdown uses the minutes beside it")
