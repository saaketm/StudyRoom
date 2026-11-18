"""Deadline tracker: a colour-coded to-do list and a calendar of deadlines."""
import calendar as pycal
from datetime import date, timedelta

from gi.repository import Adw, GLib, Gtk

from . import timeutil as tu
from .colors import DEFAULT_GCAL, gcal_hex
from .widgets import ColorDot, GcalSwatches, Tick, clear, confirm, label, time_spin_row


def _expires_text(store, it, ref):
    exp = store.done_expires(it)
    if not exp:
        return ""
    days = max(0, (exp - ref).total_seconds()) / 86400
    return "Clears today" if days < 1 else f"Clears in {int(days + 0.999)}d"


class ItemDialog(Adw.Dialog):
    """Create/edit a task (kind='tasks') or a deadline (kind='deadlines')."""

    def __init__(self, win, store, kind, item=None, day: date | None = None, color=None):
        is_dl = kind == "deadlines"
        noun = "deadline" if is_dl else "task"
        super().__init__(title=("Edit " if item else "New ") + noun, content_width=520)
        self.win, self.store, self.kind, self.item = win, store, kind, item
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
        self.title = Adw.EntryRow(title="Title")
        self.title.set_text(item["title"] if item else "")
        self.title.connect("changed", lambda *_: self.save_btn.set_sensitive(bool(self.title.get_text().strip())))
        self.title.connect("entry-activated", self._save)
        grp.add(self.title)

        if is_dl:
            self.date = date.fromisoformat(item["date"]) if item else (day or date.today())
            drow = Adw.ActionRow(title="Date")
            self.date_btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
            self.cal = Gtk.Calendar()
            self._set_cal(self.date)
            self.cal.connect("day-selected", self._day_selected)
            pop = Gtk.Popover()
            pop.set_child(self.cal)
            self.date_btn.set_popover(pop)
            self.date_btn.set_label(tu.ddmmyyyy(self.date))
            drow.add_suffix(self.date_btn)
            drow.set_activatable_widget(self.date_btn)
            grp.add(drow)
            has_time = bool(item and item.get("time"))
            self.time_switch = Adw.SwitchRow(title="Specific time", subtitle="Otherwise due by end of day (23:59)")
            self.time_switch.set_active(has_time)
            grp.add(self.time_switch)
            h, m = tu.parse_hhmm(item["time"]) if has_time else (23, 59)
            self.time_row, self.hs, self.ms = time_spin_row("Time (24-hour)", h, m)
            self.time_switch.bind_property("active", self.time_row, "sensitive", 2)  # SYNC_CREATE
            grp.add(self.time_row)
        box.append(grp)

        box.append(label("Colour", css=("heading",)))
        sel = (item or {}).get("color") or color or DEFAULT_GCAL
        self.swatches = GcalSwatches(sel)
        box.append(self.swatches)

        box.append(label("Notes", css=("heading",)))
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8,
                                  left_margin=10, right_margin=10)
        self.notes.add_css_class("card")
        self.notes.get_buffer().set_text((item or {}).get("notes", ""))
        nsc = Gtk.ScrolledWindow(min_content_height=80, max_content_height=200, propagate_natural_height=True)
        nsc.set_child(self.notes)
        box.append(nsc)

        if item:
            del_btn = Gtk.Button(label=f"Delete {noun}", halign=Gtk.Align.START)
            del_btn.add_css_class("destructive-action")
            del_btn.connect("clicked", self._delete)
            box.append(del_btn)

        tv.set_content(box)
        self.set_child(tv)
        self.save_btn.set_sensitive(bool(self.title.get_text().strip()))
        self.set_focus(self.title)

    def _set_cal(self, d):
        dt = GLib.DateTime.new_local(d.year, d.month, d.day, 0, 0, 0)
        if hasattr(self.cal, "set_date"):
            self.cal.set_date(dt)
        else:
            self.cal.select_day(dt)

    def _day_selected(self, cal):
        dt = cal.get_date()
        self.date = date(dt.get_year(), dt.get_month(), dt.get_day_of_month())
        self.date_btn.set_label(tu.ddmmyyyy(self.date))
        self.date_btn.popdown()

    def _save(self, *_):
        title = self.title.get_text().strip()
        if not title:
            return
        b = self.notes.get_buffer()
        d = {"title": title, "color": self.swatches.selected,
             "notes": b.get_text(b.get_start_iter(), b.get_end_iter(), False)}
        if self.kind == "deadlines":
            d["date"] = self.date.isoformat()
            d["time"] = (f"{int(self.hs.get_value()):02d}:{int(self.ms.get_value()):02d}"
                         if self.time_switch.get_active() else "")
        if self.item:
            self.store.update_item(self.kind, self.item["id"], d)
        else:
            self.store.add_item(self.kind, d)
        self.close()

    def _delete(self, *_):
        def do():
            self.store.delete_item(self.kind, self.item["id"])
            self.close()
        confirm(self.win, "Delete permanently?", f"“{self.item['title']}” will be removed.", "Delete", do)


class DeadlinesPage(Gtk.Box):
    title = "Deadlines"

    def __init__(self, win, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.store = win, store
        self.quick_color = DEFAULT_GCAL
        today = date.today()
        self.month = date(today.year, today.month, 1)
        self.sel_day = today

        self.toggle = Adw.ToggleGroup()
        self.toggle.add(Adw.Toggle(name="todo", label="To-do"))
        self.toggle.add(Adw.Toggle(name="calendar", label="Calendar"))
        self.toggle.set_active_name("todo")
        self.toggle.connect("notify::active-name", lambda *_: self.stack.set_visible_child_name(
            self.toggle.get_active_name()))
        self.header_title = self.toggle
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add task / deadline")
        add.connect("clicked", self._add)
        self.header_start = [add]
        self.header_end = []

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.stack.add_named(self._build_todo(), "todo")
        self.stack.add_named(self._build_calendar(), "calendar")
        self.append(self.stack)
        store.connect("changed", lambda _s, k: k in ("tasks", "deadlines") and self.refresh())
        self.refresh()

    def _add(self, *_):
        if self.toggle.get_active_name() == "todo":
            ItemDialog(self.win, self.store, "tasks", color=self.quick_color).present(self.win)
        else:
            ItemDialog(self.win, self.store, "deadlines", day=self.sel_day).present(self.win)

    # ================================================================ To-do
    def _build_todo(self):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=760, margin_top=18, margin_bottom=24, margin_start=18, margin_end=18)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        qa = Gtk.Box(spacing=8)
        self.quick = Gtk.Entry(placeholder_text="Add a task and press Enter…", hexpand=True)
        self.quick.connect("activate", self._quick_add)
        cbtn = Gtk.MenuButton(tooltip_text="Colour for new tasks")
        self.quick_dot = ColorDot(gcal_hex(self.quick_color), 16)
        cbtn.set_child(self.quick_dot)
        pop = Gtk.Popover()

        def picked(name):
            self.quick_color = name
            self.quick_dot.set_color(gcal_hex(name))
            pop.popdown()
        sw = GcalSwatches(self.quick_color, on_change=picked)
        sw.set_margin_top(6)
        sw.set_margin_bottom(6)
        sw.set_margin_start(6)
        sw.set_margin_end(6)
        pop.set_child(sw)
        cbtn.set_popover(pop)
        qa.append(self.quick)
        qa.append(cbtn)
        box.append(qa)

        self.todo_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.todo_body)
        clamp.set_child(box)
        sc.set_child(clamp)
        return sc

    def _quick_add(self, entry):
        t = entry.get_text().strip()
        if t:
            self.store.add_item("tasks", {"title": t, "color": self.quick_color})
            entry.set_text("")

    def _item_row(self, kind, it, ref, show_left=False, show_date=False):
        row = Gtk.ListBoxRow(activatable=True)
        row.connect("activate", lambda *_: ItemDialog(self.win, self.store, kind, it).present(self.win))
        box = Gtk.Box(spacing=12, margin_top=9, margin_bottom=9, margin_start=10, margin_end=12)
        box.append(Tick(it["color"], it["done"],
                        lambda: self.store.set_done(kind, it["id"], not it["done"])))
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        t = label(it["title"], wrap=True)
        t.set_wrap_mode(2)
        if it["done"]:
            t.add_css_class("done-title")
        vb.append(t)
        meta = []
        if kind == "deadlines":
            d = date.fromisoformat(it["date"])
            if show_date:
                meta.append(f"{tu.WEEKDAYS[d.weekday()]}, {tu.ddmmyyyy(d)}")
            meta.append(it["time"] or "End of day")
            if not show_date:
                meta.insert(0, "Deadline")
        if it["done"]:
            meta.append(_expires_text(self.store, it, ref))
        if meta:
            vb.append(label(" · ".join(m for m in meta if m), css=("caption", "dim-label")))
        if it.get("notes"):
            n = label(it["notes"], css=("caption", "dim-label"), wrap=True)
            n.set_wrap_mode(2)
            vb.append(n)
        box.append(vb)
        if kind == "deadlines" and not it["done"] and show_left:
            txt, cls = tu.time_left(self.store.deadline_dt(it), ref)
            box.append(label(txt, css=("caption", "tnum") + ((f"left-{cls}",) if cls else ("dim-label",))))
        row.set_child(box)
        row.add_css_class(f"stripe-{it['color']}")
        return row

    def _list(self, rows):
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.connect("row-activated", lambda _l, r: r.emit("activate"))
        for r in rows:
            lb.append(r)
        return lb

    def _refresh_todo(self, ref):
        clear(self.todo_body)
        today = ref.date()
        due_today = sorted((d for d in self.store.deadlines if d["date"] == today.isoformat()),
                           key=lambda d: (d["done"], d["time"] or "23:59"))
        if due_today:
            self.todo_body.append(label(f"DUE TODAY · {tu.ddmmyy(today)}", css=("section-title", "dim-label"),
                                        margin_top=8))
            self.todo_body.append(self._list([self._item_row("deadlines", d, ref, show_left=True)
                                              for d in due_today]))
        open_tasks = [t for t in self.store.tasks if not t["done"]]
        done_tasks = sorted((t for t in self.store.tasks if t["done"]), key=lambda t: t.get("done_at") or "",
                            reverse=True)
        self.todo_body.append(label(f"TASKS · {len(open_tasks)}", css=("section-title", "dim-label"),
                                    margin_top=8))
        if open_tasks:
            self.todo_body.append(self._list([self._item_row("tasks", t, ref) for t in open_tasks]))
        else:
            self.todo_body.append(label("Nothing pending. Nice." if self.store.tasks else "No tasks yet.",
                                        css=("dim-label",), xalign=0.5, margin_top=24, margin_bottom=24))
        if done_tasks:
            exp = Gtk.Expander(label=f"Completed · {len(done_tasks)}  (cleared 14 days after ticking)",
                               margin_top=12, expanded=getattr(self, "_todo_done_open", False))
            exp.connect("notify::expanded", lambda e, _p: setattr(self, "_todo_done_open", e.get_expanded()))
            exp.set_child(self._list([self._item_row("tasks", t, ref) for t in done_tasks]))
            exp.get_child().set_margin_top(8)
            self.todo_body.append(exp)

    # ================================================================ Calendar
    def _build_calendar(self):
        outer = Gtk.Box()
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True,
                       margin_top=12, margin_bottom=12, margin_start=16, margin_end=12)
        nav = Gtk.Box(spacing=6)
        prev = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous month")
        prev.connect("clicked", lambda *_: self._shift_month(-1))
        nxt = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next month")
        nxt.connect("clicked", lambda *_: self._shift_month(1))
        self.month_lbl = label(css=("title-3",), hexpand=True, margin_start=6)
        today_btn = Gtk.Button(label="Today")
        today_btn.connect("clicked", self._goto_today)
        for w in (prev, nxt):
            w.add_css_class("flat")
        nav.append(self.month_lbl)
        nav.append(today_btn)
        nav.append(prev)
        nav.append(nxt)
        left.append(nav)
        self.grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=False, column_spacing=4, row_spacing=4,
                             vexpand=True)
        left.append(self.grid)
        outer.append(left)
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=360)
        self.side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=24,
                            margin_start=14, margin_end=14)
        sc.set_child(self.side)
        outer.append(sc)
        return outer

    def _shift_month(self, delta):
        y, m = self.month.year, self.month.month + delta
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        self.month = date(y, m, 1)
        self.refresh()

    def _goto_today(self, *_):
        t = date.today()
        self.month, self.sel_day = date(t.year, t.month, 1), t
        self.refresh()

    def _select(self, d):
        self.sel_day = d
        if d.month != self.month.month or d.year != self.month.year:
            self.month = date(d.year, d.month, 1)
        self.refresh()

    def _refresh_grid(self, ref):
        clear(self.grid)
        self.month_lbl.set_label(f"{tu.MONTHS[self.month.month - 1]} {self.month.year}")
        fw = int(self.store.get("first_weekday"))
        for i in range(7):
            self.grid.attach(label(tu.WEEKDAYS[(fw + i) % 7].upper(), css=("cal-head",), xalign=0.5), i, 0, 1, 1)
        start = tu.week_start(self.month, fw)
        by_day = {}
        for d in self.store.deadlines:
            by_day.setdefault(d["date"], []).append(d)
        today = ref.date()
        for i in range(42):
            d = start + timedelta(days=i)
            items = sorted(by_day.get(d.isoformat(), []), key=lambda x: (x["done"], x["time"] or "23:59"))
            btn = Gtk.Button(vexpand=True)
            btn.add_css_class("flat")
            btn.add_css_class("cal-cell")
            if d.month != self.month.month:
                btn.add_css_class("other-month")
            if d == self.sel_day:
                btn.add_css_class("selected-day")
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.START)
            num = label(str(d.day), css=("cal-daynum",), xalign=0.5, halign=Gtk.Align.START)
            if d == today:
                num.add_css_class("cal-today")
            vb.append(num)
            for it in items[:3]:
                chip = label(it["title"], css=("cal-chip", f"gc-{it['color']}"))
                chip.set_ellipsize(3)
                chip.set_max_width_chars(1)
                chip.set_hexpand(True)
                if it["done"]:
                    chip.add_css_class("done-title")
                vb.append(chip)
            if len(items) > 3:
                vb.append(label(f"+{len(items) - 3} more", css=("caption", "dim-label")))
            btn.set_child(vb)
            btn.set_tooltip_text(tu.ddmmyyyy(d) + "".join(
                f"\n• {x['title']}" + (f" ({x['time']})" if x["time"] else "") for x in items))
            btn.connect("clicked", lambda _b, d=d: self._select(d))
            g = Gtk.GestureClick()
            g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            g.connect("pressed", lambda _g, n, _x, _y, d=d: n == 2 and ItemDialog(
                self.win, self.store, "deadlines", day=d).present(self.win))
            btn.add_controller(g)
            self.grid.attach(btn, i % 7, 1 + i // 7, 1, 1)

    def _refresh_side(self, ref):
        clear(self.side)
        d = self.sel_day
        head = Gtk.Box(spacing=6)
        head.append(label(f"{tu.WEEKDAYS_LONG[d.weekday()]}, {tu.ddmmyyyy(d)}", css=("title-4",), hexpand=True))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add deadline on this day")
        add.add_css_class("flat")
        add.connect("clicked", lambda *_: ItemDialog(self.win, self.store, "deadlines", day=d).present(self.win))
        head.append(add)
        self.side.append(head)
        day_items = sorted((x for x in self.store.deadlines if x["date"] == d.isoformat()),
                           key=lambda x: (x["done"], x["time"] or "23:59"))
        if day_items:
            self.side.append(self._list([self._item_row("deadlines", x, ref, show_left=True)
                                         for x in day_items]))
        else:
            self.side.append(label("No deadlines. Double-click a day or press + to add one.",
                                   css=("dim-label", "caption"), wrap=True))

        active = sorted((x for x in self.store.deadlines if not x["done"]), key=self.store.deadline_dt)
        self.side.append(label(f"UPCOMING · {len(active)}", css=("section-title", "dim-label"), margin_top=18))
        if not active:
            self.side.append(label("Nothing pending.", css=("dim-label", "caption")))
        cur, rows = None, []

        def flush():
            if cur:
                self.side.append(label(f"{tu.MONTHS[cur[1] - 1].upper()} {cur[0]} · {len(rows)}",
                                       css=("month-head",)))
                self.side.append(self._list(rows))
        for x in active:
            dt = self.store.deadline_dt(x)
            k = (dt.year, dt.month)
            if k != cur:
                flush()
                cur, rows = k, []
            rows.append(self._item_row("deadlines", x, ref, show_left=True, show_date=True))
        flush()

        done = sorted((x for x in self.store.deadlines if x["done"]), key=lambda x: x.get("done_at") or "",
                      reverse=True)
        if done:
            exp = Gtk.Expander(label=f"Completed · {len(done)}", margin_top=16,
                               expanded=getattr(self, "_cal_done_open", False))
            exp.connect("notify::expanded", lambda e, _p: setattr(self, "_cal_done_open", e.get_expanded()))
            lb = self._list([self._item_row("deadlines", x, ref, show_date=True) for x in done])
            lb.set_margin_top(8)
            exp.set_child(lb)
            self.side.append(exp)

    # ================================================================ refresh
    def refresh(self):
        ref = tu.now()
        self._refresh_todo(ref)
        self._refresh_grid(ref)
        self._refresh_side(ref)

    def minute_tick(self):
        self.store.prune_done()
        self.refresh()
