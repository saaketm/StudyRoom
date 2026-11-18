"""Session history: day / week / month / year / all-time views, subject-wise."""
from datetime import date, datetime, timedelta

from gi.repository import Adw, GLib, Gtk

from . import timeutil as tu
from .charts import DayTimeline, ShareBar, StackedBars
from .widgets import ColorDot, clear, confirm, label, popover_menu, time_spin_row

MAX_LISTED = 200


class AddSessionDialog(Adw.Dialog):
    """Log a session after the fact (e.g. forgot to start the timer)."""

    def __init__(self, win, store, day: date):
        super().__init__(title="Add session", content_width=460)
        self.win, self.store = win, store
        self.day = min(day, date.today())
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label="Add")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        hb.pack_start(cancel)
        hb.pack_end(save)
        tv.add_top_bar(hb)
        grp = Adw.PreferencesGroup(margin_top=12, margin_bottom=24, margin_start=18, margin_end=18)
        self.subjects = list(store.subjects)
        self.combo = Adw.ComboRow(title="Subject", model=Gtk.StringList.new([s["name"] for s in self.subjects]))
        last = store.get("last_subject")
        for i, s in enumerate(self.subjects):
            if s["id"] == last:
                self.combo.set_selected(i)
        grp.add(self.combo)
        drow = Adw.ActionRow(title="Date")
        self.date_btn = Gtk.MenuButton(valign=Gtk.Align.CENTER, label=tu.ddmmyy(self.day))
        cal = Gtk.Calendar()
        dt = GLib.DateTime.new_local(self.day.year, self.day.month, self.day.day, 0, 0, 0)
        cal.set_date(dt) if hasattr(cal, "set_date") else cal.select_day(dt)
        pop = Gtk.Popover()
        pop.set_child(cal)
        self.date_btn.set_popover(pop)

        def picked(c):
            g = c.get_date()
            self.day = date(g.get_year(), g.get_month(), g.get_day_of_month())
            self.date_btn.set_label(tu.ddmmyy(self.day))
            pop.popdown()
        cal.connect("day-selected", picked)
        drow.add_suffix(self.date_btn)
        grp.add(drow)
        n = tu.now()
        row, self.sh, self.sm = time_spin_row("Start time (24-hour)", max(0, n.hour - 1), 0)
        grp.add(row)
        drow2, self.dh, self.dm = time_spin_row("Duration (hours : minutes)", 1, 0)
        self.dh.set_range(0, 16)
        grp.add(drow2)
        tv.set_content(grp)
        self.set_child(tv)

    def _save(self, *_):
        if not self.subjects:
            self.win.toast("Add a subject first")
            return
        s = self.subjects[self.combo.get_selected()]
        start = datetime(self.day.year, self.day.month, self.day.day,
                         int(self.sh.get_value()), int(self.sm.get_value())).astimezone()
        secs = int(self.dh.get_value()) * 3600 + int(self.dm.get_value()) * 60
        if secs <= 0:
            self.win.toast("Duration must be more than 0")
            return
        end = start + timedelta(seconds=secs)
        if end > tu.now():
            self.win.toast("That session would end in the future")
            return
        self.store.add_session(self.store.make_session(s["id"], s["name"], s["color"], start, end, secs,
                                                       manual=True))
        self.win.toast(f"Added {tu.dur(secs)} of {s['name']}")
        self.close()


class HistoryPage(Gtk.Box):
    title = "History"

    def __init__(self, win, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.store = win, store
        self.mode = "week"
        self.anchor = self._today()

        self.toggle = Adw.ToggleGroup()
        for name, lab in (("day", "Day"), ("week", "Week"), ("month", "Month"), ("year", "Year"), ("all", "All time")):
            self.toggle.add(Adw.Toggle(name=name, label=lab))
        self.toggle.set_active_name(self.mode)
        self.toggle.connect("notify::active-name", self._mode_changed)
        self.header_title = self.toggle
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add a session manually")
        add.connect("clicked", lambda *_: AddSessionDialog(win, store, self._range()[0]).present(win))
        self.header_start = [add]
        self.header_end = []

        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        clamp = Adw.Clamp(maximum_size=920, margin_top=16, margin_bottom=32, margin_start=18, margin_end=18)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        nav = Gtk.Box(spacing=6)
        self.prev = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous")
        self.prev.connect("clicked", lambda *_: self._shift(-1))
        self.next = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next")
        self.next.connect("clicked", lambda *_: self._shift(1))
        for b in (self.prev, self.next):
            b.add_css_class("flat")
        self.range_lbl = label(css=("title-3",), hexpand=True)
        self.today_btn = Gtk.Button(label="Today")
        self.today_btn.connect("clicked", lambda *_: self._goto_today())
        nav.append(self.range_lbl)
        nav.append(self.today_btn)
        nav.append(self.prev)
        nav.append(self.next)
        box.append(nav)

        self.stats = Gtk.Box(spacing=10, homogeneous=True)
        self.stat_vals, self.stat_labels = {}, {}
        for key, lab in (("total", "Total"), ("avg", "Daily average"), ("count", "Sessions"), ("longest", "Longest")):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.add_css_class("card")
            card.add_css_class("chart-card")
            v = label("–", css=("stat-value",))
            card.append(v)
            card.append(label(lab, css=("stat-label", "dim-label")))
            self.stat_vals[key] = v
            self.stat_labels[key] = card.get_last_child()
            self.stats.append(card)
        box.append(self.stats)

        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        chart_card.add_css_class("card")
        chart_card.add_css_class("chart-card")
        self.chart_title = label(css=("heading",))
        chart_card.append(self.chart_title)
        self.chart_stack = Gtk.Stack(vhomogeneous=False, interpolate_size=True)
        self.bars = StackedBars()
        self.timeline = DayTimeline()
        self.chart_stack.add_named(self.bars, "bars")
        self.chart_stack.add_named(self.timeline, "timeline")
        chart_card.append(self.chart_stack)
        self.legend = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8,
                                  column_spacing=14, row_spacing=4)
        chart_card.append(self.legend)
        box.append(chart_card)

        box.append(label("SUBJECTS", css=("section-title", "dim-label"), margin_top=6))
        self.breakdown = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.breakdown.add_css_class("boxed-list")
        box.append(self.breakdown)

        box.append(label("SESSIONS", css=("section-title", "dim-label"), margin_top=6))
        self.sessions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.sessions_box)

        clamp.set_child(box)
        sc.set_child(clamp)
        self.append(sc)
        store.connect("changed", lambda _s, k: k in ("sessions", "subjects", "settings") and self.refresh())
        self.refresh()

    # ------------------------------------------------------------ range logic
    def _today(self):
        return tu.study_day(tu.now(), self.store.get("day_start"))

    def _range(self):
        """[first_day, last_day_exclusive) in study days."""
        a = self.anchor
        if self.mode == "day":
            return a, a + timedelta(days=1)
        if self.mode == "week":
            s = tu.week_start(a, int(self.store.get("first_weekday")))
            return s, s + timedelta(days=7)
        if self.mode == "month":
            s = date(a.year, a.month, 1)
            e = date(a.year + (a.month // 12), a.month % 12 + 1, 1)
            return s, e
        if self.mode == "year":
            return date(a.year, 1, 1), date(a.year + 1, 1, 1)
        first = min((tu.study_day(s["_start"], self.store.get("day_start")) for s in self.store.sessions),
                    default=self._today())
        return first, self._today() + timedelta(days=1)

    def _range_label(self, s, e):
        last = e - timedelta(days=1)
        if self.mode == "day":
            return f"{tu.WEEKDAYS_LONG[s.weekday()]}, {tu.ddmmyy(s)}"
        if self.mode == "week":
            return f"{tu.ddmmyy(s)} – {tu.ddmmyy(last)}"
        if self.mode == "month":
            return f"{tu.MONTHS[s.month - 1]} {s.year}"
        if self.mode == "year":
            return str(s.year)
        return f"All time · since {tu.ddmmyy(s)}"

    def _mode_changed(self, *_):
        self.mode = self.toggle.get_active_name()
        self.refresh()

    def _shift(self, d):
        a = self.anchor
        if self.mode == "day":
            self.anchor = a + timedelta(days=d)
        elif self.mode == "week":
            self.anchor = a + timedelta(days=7 * d)
        elif self.mode == "month":
            m = a.month - 1 + d
            self.anchor = date(a.year + m // 12, m % 12 + 1, 1)
        elif self.mode == "year":
            self.anchor = date(a.year + d, 1, 1)
        self.refresh()

    def _goto_today(self):
        self.anchor = self._today()
        self.refresh()

    # ------------------------------------------------------------ refresh
    def refresh(self):
        st = self.store
        ds = st.get("day_start")
        s_day, e_day = self._range()
        today = self._today()
        self.range_lbl.set_label(self._range_label(s_day, e_day))
        nav = self.mode != "all"
        self.prev.set_visible(nav)
        self.next.set_visible(nav)
        self.today_btn.set_visible(nav)
        self.next.set_sensitive(e_day <= today)

        sess = []
        for s in st.sessions:
            d = tu.study_day(s["_start"], ds)
            if s_day <= d < e_day:
                sess.append((d, s))

        # stable subject order: live subjects in list order, then erased ones by name
        order = {sub["id"]: i for i, sub in enumerate(st.subjects)}
        per_key = {}
        for _d, s in sess:
            k = st.session_key(s)
            name, color = st.session_display(s)
            e = per_key.setdefault(k, {"name": name, "color": color, "secs": 0})
            e["secs"] += s["study_seconds"]
        keys = sorted(per_key, key=lambda k: (order.get(k, 10_000), per_key[k]["name"].lower()))

        total = sum(s["study_seconds"] for _d, s in sess)
        days_counted = max(1, (min(e_day, today + timedelta(days=1)) - s_day).days)
        self.stat_vals["total"].set_label(tu.dur(total))
        if self.mode == "day":
            first = min((s["_start"] for _d, s in sess), default=None)
            self.stat_labels["avg"].set_label("First session")
            self.stat_vals["avg"].set_label(tu.hhmm(first) if first else "–")
        else:
            self.stat_labels["avg"].set_label("Daily average")
            self.stat_vals["avg"].set_label(tu.dur(total / days_counted))
        self.stat_vals["count"].set_label(str(len(sess)))
        self.stat_vals["longest"].set_label(tu.dur(max((s["study_seconds"] for _d, s in sess), default=0)))

        # chart
        if self.mode == "day":
            start_dt, _ = tu.day_bounds(s_day, ds)
            blocks = []
            for _d, s in sess:
                name, color = st.session_display(s)
                blocks.append((s["_start"], s["_end"], name, color, s["study_seconds"]))
            self.timeline.set_data(start_dt, blocks)
            self.chart_stack.set_visible_child_name("timeline")
            self.chart_title.set_label("Timeline")
        else:
            buckets = self._buckets(sess, keys, s_day, e_day)
            self.bars.set_data(buckets)
            self.chart_stack.set_visible_child_name("bars")
            self.chart_title.set_label({"week": "Daily study", "month": "Daily study",
                                        "year": "Monthly study"}.get(self.mode, self._all_title))
        clear(self.legend)
        for k in keys:
            item = Gtk.Box(spacing=6)
            item.append(ColorDot(per_key[k]["color"], 10))
            item.append(label(per_key[k]["name"], css=("caption",)))
            self.legend.append(item)
        self.legend.set_visible(bool(keys))

        # breakdown
        clear(self.breakdown)
        for k in sorted(keys, key=lambda k: -per_key[k]["secs"]):
            e = per_key[k]
            row = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
            row.append(ColorDot(e["color"], 12))
            nm = label(e["name"], width_chars=14, max_width_chars=22)
            nm.set_ellipsize(3)
            row.append(nm)
            row.append(ShareBar(e["secs"] / total if total else 0, e["color"]))
            row.append(label(tu.dur(e["secs"]), css=("tnum",), width_chars=8, xalign=1))
            pct = 100 * e["secs"] / total if total else 0
            row.append(label("<1%" if 0 < pct < 0.5 else f"{round(pct)}%", css=("tnum", "dim-label"),
                             width_chars=4, xalign=1))
            self.breakdown.append(row)
        if not keys:
            self.breakdown.append(label("No sessions in this period.", css=("dim-label",), xalign=0.5,
                                        margin_top=18, margin_bottom=18))

        # session list grouped by study day, newest first
        clear(self.sessions_box)
        shown = sorted(sess, key=lambda x: x[1]["_start"], reverse=True)[:MAX_LISTED]
        by_day = {}
        for d, s in shown:
            by_day.setdefault(d, []).append(s)
        day_tot = {}
        for d, s in sess:
            day_tot[d] = day_tot.get(d, 0) + s["study_seconds"]
        for d, items in by_day.items():
            head = Gtk.Box(margin_top=4)
            head.append(label(f"{tu.WEEKDAYS[d.weekday()]}, {tu.ddmmyy(d)}", css=("heading",), hexpand=True))
            head.append(label(tu.dur(day_tot[d]), css=("tnum", "dim-label")))
            self.sessions_box.append(head)
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            for s in items:
                lb.append(self._session_row(s))
            self.sessions_box.append(lb)
        if len(sess) > MAX_LISTED:
            self.sessions_box.append(label(f"Showing the latest {MAX_LISTED} of {len(sess)} sessions.",
                                           css=("dim-label", "caption"), xalign=0.5))

    def _session_row(self, s):
        name, color = self.store.session_display(s)
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=12, margin_end=6)
        box.append(ColorDot(color, 12))
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        vb.append(label(name))
        meta = f"{tu.hhmm(s['_start'])} – {tu.hhmm(s['_end'])}"
        if s.get("mode") == "countdown" and s.get("target_minutes"):
            meta += f" · Countdown {tu.dur(s['target_minutes'] * 60)}"
        if s.get("paused_seconds", 0) >= 60:
            meta += f" · paused {tu.dur(s['paused_seconds'])}"
        if s.get("manual"):
            meta += " · added manually"
        vb.append(label(meta, css=("caption", "dim-label", "tnum")))
        box.append(vb)
        box.append(label(tu.dur(s["study_seconds"]), css=("tnum",)))

        def delete():
            confirm(self.win, "Delete this session?",
                    f"{name}, {tu.ddmmyy(s['_start'])} {tu.hhmm(s['_start'])} ({tu.dur(s['study_seconds'])}) "
                    "will be removed from your history.", "Delete", lambda: self.store.delete_session(s["id"]))
        box.append(popover_menu([("Delete session…", delete, True)]))
        return box

    def _buckets(self, sess, keys, s_day, e_day):
        st = self.store
        segs_of = lambda acc: [(acc_name(k), acc_color(k), acc.get(k, 0)) for k in keys]
        info = {}
        for _d, s in sess:
            info[st.session_key(s)] = st.session_display(s)
        acc_name = lambda k: info[k][0]
        acc_color = lambda k: info[k][1]
        buckets = []
        if self.mode in ("week", "month"):
            idx = {}
            d = s_day
            while d < e_day:
                idx[d] = {}
                lab = f"{tu.WEEKDAYS[d.weekday()]} {d.day}" if self.mode == "week" else str(d.day)
                buckets.append({"label": lab, "tip": f"{tu.WEEKDAYS[d.weekday()]}, {tu.ddmmyy(d)}", "acc": idx[d]})
                d += timedelta(days=1)
            for d, s in sess:
                a = idx[d]
                k = st.session_key(s)
                a[k] = a.get(k, 0) + s["study_seconds"]
        else:
            months = []
            y, m = s_day.year, s_day.month
            while (y, m) < (e_day.year, e_day.month) or (self.mode == "year" and len(months) < 12):
                months.append((y, m))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
                if self.mode == "year" and len(months) == 12:
                    break
            if self.mode == "all" and (y, m) == (e_day.year, e_day.month) and e_day.day > 1:
                months.append((y, m))
            by_year = self.mode == "all" and len(months) > 36
            self._all_title = "Yearly study" if by_year else "Monthly study"
            idx = {}
            for (y, m) in months:
                key = y if by_year else (y, m)
                if key in idx:
                    continue
                idx[key] = {}
                if by_year:
                    buckets.append({"label": str(y), "tip": str(y), "acc": idx[key]})
                else:
                    lab = tu.MONTHS_SHORT[m - 1] + ("" if self.mode == "year" else f" {str(y)[2:]}")
                    buckets.append({"label": lab, "tip": f"{tu.MONTHS[m - 1]} {y}", "acc": idx[key]})
            for d, s in sess:
                key = d.year if by_year else (d.year, d.month)
                if key in idx:
                    a = idx[key]
                    k = st.session_key(s)
                    a[k] = a.get(k, 0) + s["study_seconds"]
        for b in buckets:
            b["segs"] = segs_of(b.pop("acc"))
        return buckets

    _all_title = "Monthly study"
