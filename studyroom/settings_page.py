"""Settings: theme, colour scheme, study-day rollover, timer defaults, top-bar timer, data folder."""
import shutil
import subprocess

from gi.repository import Adw, Gio, Gtk

from . import timeutil as tu
from .theme import THEMES
from .widgets import time_spin_row

EXT_UUID = "studyroom-timer@studyroom.local"


def _ext_state():
    """Return 'missing' | 'enabled' | 'disabled' | 'needs-relogin' for the top-bar extension."""
    if not shutil.which("gnome-extensions"):
        return "missing"
    try:
        out = subprocess.run(["gnome-extensions", "info", EXT_UUID], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return "missing"
    if not out.strip():
        # The shell has not discovered it yet (Wayland needs a log out / log in after installing).
        try:
            listed = EXT_UUID in Gio.Settings.new("org.gnome.shell").get_strv("enabled-extensions")
        except Exception:  # noqa: BLE001
            listed = False
        return "needs-relogin" if listed else "disabled"
    enabled = "Enabled: Yes" in out
    state_line = next((l for l in out.splitlines() if "State:" in l), "")
    if enabled and "ACTIVE" in state_line:
        return "enabled"
    if enabled:
        return "needs-relogin" if "INITIALIZED" in state_line or "UNINSTALLED" in state_line else "enabled"
    return "disabled"


class ThemeSwatch(Gtk.DrawingArea):
    def __init__(self, accent, light, dark):
        super().__init__()
        self.set_content_width(52)
        self.set_content_height(52)
        self.accent, self.light, self.dark = accent, light or "#fafafb", dark or "#222226"
        self.set_draw_func(self._draw)

    def _draw(self, _a, cr, w, h):
        import math
        from .colors import hex_to_rgb
        r = min(w, h) / 2 - 2
        cx, cy = w / 2, h / 2
        cr.set_source_rgb(*hex_to_rgb(self.light))
        cr.move_to(cx, cy)
        cr.arc(cx, cy, r, math.pi / 2, 3 * math.pi / 2)
        cr.fill()
        cr.set_source_rgb(*hex_to_rgb(self.dark))
        cr.move_to(cx, cy)
        cr.arc(cx, cy, r, -math.pi / 2, math.pi / 2)
        cr.fill()
        cr.set_source_rgb(*hex_to_rgb(self.accent))
        cr.arc(cx, cy, r * 0.45, 0, 2 * math.pi)
        cr.fill()
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
        cr.set_line_width(1)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()


class SettingsPage(Gtk.Box):
    title = "Settings"

    def __init__(self, win, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.store = win, store
        self.header_start, self.header_end = [], []
        page = Adw.PreferencesPage(vexpand=True)

        # ---------------- appearance
        ap = Adw.PreferencesGroup(title="Appearance")
        scheme = Adw.ComboRow(title="Light / dark", model=Gtk.StringList.new(["Follow system", "Light", "Dark"]))
        scheme.set_selected({"system": 0, "light": 1, "dark": 2}.get(store.get("scheme"), 0))
        scheme.connect("notify::selected", lambda r, _p: store.set("scheme", ["system", "light", "dark"][r.get_selected()]))
        ap.add(scheme)
        page.add(ap)

        th = Adw.PreferencesGroup(title="Theme", description="Accent colour and tinted backgrounds")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=9, min_children_per_line=3,
                           column_spacing=6, row_spacing=6, homogeneous=True)
        group = None
        for key, (name, accent, light, dark) in THEMES.items():
            b = Gtk.ToggleButton()
            b.add_css_class("flat")
            b.add_css_class("theme-card")
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            vb.append(ThemeSwatch(accent, light, dark))
            vb.append(Gtk.Label(label=name, css_classes=["caption"]))
            b.set_child(vb)
            if group:
                b.set_group(group)
            else:
                group = b
            b.set_active(store.get("theme") == key)
            b.connect("toggled", lambda btn, k=key: btn.get_active() and store.set("theme", k))
            flow.append(b)
        th.add(flow)
        page.add(th)

        # ---------------- study
        sg = Adw.PreferencesGroup(title="Study")
        h, m = tu.parse_hhmm(store.get("day_start"))
        row, self.ds_h, self.ds_m = time_spin_row(
            "New day starts at", h, m,
            subtitle="Sessions started before this time count towards the previous day")
        for s in (self.ds_h, self.ds_m):
            s.connect("value-changed", self._day_start_changed)
        sg.add(row)
        cd = Adw.SpinRow.new_with_range(1, 600, 5)
        cd.set_title("Default countdown (minutes)")
        cd.set_value(store.get("countdown_minutes"))
        cd.connect("notify::value", lambda r, _p: store.set("countdown_minutes", int(r.get_value())))
        sg.add(cd)
        mn = Adw.SpinRow.new_with_range(0, 30, 1)
        mn.set_title("Minimum session to save (minutes)")
        mn.set_subtitle("Shorter sessions are discarded when stopped")
        mn.set_value(store.get("min_session_seconds") // 60)
        mn.connect("notify::value", lambda r, _p: store.set("min_session_seconds", int(r.get_value()) * 60))
        sg.add(mn)
        snd = Adw.SwitchRow(title="Sound when a countdown ends")
        snd.set_active(store.get("countdown_sound"))
        snd.connect("notify::active", lambda r, _p: store.set("countdown_sound", r.get_active()))
        sg.add(snd)
        wk = Adw.ComboRow(title="Week starts on", model=Gtk.StringList.new(["Monday", "Sunday"]))
        wk.set_selected(1 if int(store.get("first_weekday")) == 6 else 0)
        wk.connect("notify::selected", lambda r, _p: store.set("first_weekday", 6 if r.get_selected() else 0))
        sg.add(wk)
        page.add(sg)

        # ---------------- top bar
        tb = Adw.PreferencesGroup(title="Top bar")
        self.ext_row = Adw.SwitchRow(title="Show running timer in the top bar")
        self._ext_lock = True
        st = _ext_state()
        self.ext_row.set_active(st in ("enabled", "needs-relogin"))
        self._ext_subtitle(st)
        self.ext_row.connect("notify::active", self._ext_toggled)
        self._ext_lock = False
        tb.add(self.ext_row)
        page.add(tb)

        # ---------------- data
        dg = Adw.PreferencesGroup(title="Data", description="Everything is stored only on this laptop")
        loc = Adw.ActionRow(title="Data folder", subtitle=str(store.dir))
        loc.set_subtitle_selectable(True)
        ob = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Open folder")
        ob.add_css_class("flat")
        ob.connect("clicked", lambda *_: Gtk.FileLauncher.new(Gio.File.new_for_path(str(store.dir)))
                   .launch(win, None, None, None))
        loc.add_suffix(ob)
        dg.add(loc)
        dg.add(Adw.ActionRow(title="Session log",
                             subtitle="sessions.jsonl — one line per session; format described in SESSIONS-FORMAT.md"))
        dg.add(Adw.ActionRow(title="Backups", subtitle="A daily copy is kept in backups/ (last 30 days)"))
        page.add(dg)
        self.append(page)

    def _day_start_changed(self, *_):
        self.store.set("day_start", f"{int(self.ds_h.get_value()):02d}:{int(self.ds_m.get_value()):02d}")

    def _ext_subtitle(self, st):
        self.ext_row.set_subtitle({
            "enabled": "Shows subject and time while a session runs",
            "disabled": "Off",
            "needs-relogin": "Log out and back in once so GNOME picks up the indicator",
            "missing": "Indicator not installed — run install.sh",
        }[st])

    def _ext_toggled(self, row, _p):
        if self._ext_lock:
            return
        on = row.get_active()
        try:
            subprocess.run(["gnome-extensions", "enable" if on else "disable", EXT_UUID],
                           capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        # If GNOME hasn't discovered the indicator yet, the command above can't act on it.
        # Add/remove only our own id in GNOME's enabled list so it takes effect after the next login.
        try:
            gs = Gio.Settings.new("org.gnome.shell")
            cur = list(gs.get_strv("enabled-extensions"))
            if on and EXT_UUID not in cur:
                gs.set_strv("enabled-extensions", cur + [EXT_UUID])
            elif not on and EXT_UUID in cur:
                gs.set_strv("enabled-extensions", [x for x in cur if x != EXT_UUID])
        except Exception:  # noqa: BLE001 - schema missing on non-GNOME systems
            pass
        st = _ext_state()
        if row.get_active() and st == "needs-relogin":
            self.win.toast("Enabled. Log out and back in once to see it in the top bar.")
        self._ext_subtitle(st if not (row.get_active() and st == "disabled") else "needs-relogin")
