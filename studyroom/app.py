"""Application + main window."""
import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, timeutil as tu  # noqa: E402
from .deadlines_page import DeadlinesPage  # noqa: E402
from .history_page import HistoryPage  # noqa: E402
from .settings_page import SettingsPage  # noqa: E402
from .store import Store  # noqa: E402
from .study_page import StudyPage  # noqa: E402
from .theme import ThemeManager  # noqa: E402
from .widgets import ColorDot, label  # noqa: E402

SECTIONS = [("study", "Study", "alarm-symbolic"),
            ("deadlines", "Deadlines", "x-office-calendar-symbolic"),
            ("history", "History", "document-open-recent-symbolic"),
            ("settings", "Settings", "emblem-system-symbolic")]
SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME, default_width=1180, default_height=780)
        self.app, self.store = app, app.store
        self.set_size_request(760, 560)

        self.toasts = Adw.ToastOverlay()
        self.split = Adw.NavigationSplitView(min_sidebar_width=210, max_sidebar_width=240)

        # sidebar
        sb_tv = Adw.ToolbarView()
        sb_hb = Adw.HeaderBar()
        sb_hb.set_title_widget(Adw.WindowTitle(title=APP_NAME))
        sb_tv.add_top_bar(sb_hb)
        sb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.nav = Gtk.ListBox(vexpand=True)
        self.nav.add_css_class("navigation-sidebar")
        for key, name, icon in SECTIONS:
            row = Gtk.ListBoxRow()
            row.key = key
            b = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6)
            b.append(Gtk.Image(icon_name=icon))
            b.append(label(name))
            row.set_child(b)
            self.nav.append(row)
        self.nav.connect("row-selected", self._nav_selected)
        sb_box.append(self.nav)

        self.sb_timer = Gtk.Button(margin_start=10, margin_end=10, margin_bottom=10, visible=False,
                                   tooltip_text="Go to the running session")
        self.sb_timer.add_css_class("flat")
        self.sb_timer.add_css_class("sidebar-timer")
        tb = Gtk.Box(spacing=8)
        self.sb_dot = ColorDot(size=10)
        tb.append(self.sb_dot)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sb_subj = label(css=("caption",))
        self.sb_subj.set_ellipsize(3)
        self.sb_time = label(css=("heading", "tnum"))
        vb.append(self.sb_subj)
        vb.append(self.sb_time)
        tb.append(vb)
        self.sb_timer.set_child(tb)
        self.sb_timer.connect("clicked", lambda *_: self.show_section("study"))
        sb_box.append(self.sb_timer)
        sb_tv.set_content(sb_box)
        self.split.set_sidebar(Adw.NavigationPage(title=APP_NAME, child=sb_tv))

        # content pages
        self.pages = {"study": StudyPage(self, self.store), "deadlines": DeadlinesPage(self, self.store),
                      "history": HistoryPage(self, self.store), "settings": SettingsPage(self, self.store)}
        self.nav_pages = {}
        for key, page in self.pages.items():
            tv = Adw.ToolbarView()
            hb = Adw.HeaderBar()
            if getattr(page, "header_title", None):
                hb.set_title_widget(page.header_title)
            else:
                hb.set_title_widget(Adw.WindowTitle(title=page.title))
            for w in page.header_start:
                hb.pack_start(w)
            for w in page.header_end:
                hb.pack_end(w)
            tv.add_top_bar(hb)
            tv.set_content(page)
            self.nav_pages[key] = Adw.NavigationPage(title=page.title, child=tv, tag=key)

        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 820sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        self.show_section("study")
        self.connect("close-request", self._close_request)
        if self.store.load_warning:
            GLib.idle_add(lambda: self.toast(self.store.load_warning, 8) and False)

    def show_section(self, key):
        for row in self._rows():
            if row.key == key:
                self.nav.select_row(row)

    def _rows(self):
        r = self.nav.get_first_child()
        while r:
            yield r
            r = r.get_next_sibling()

    def _nav_selected(self, _lb, row):
        if row is None:
            return
        self.current = row.key
        self.split.set_content(self.nav_pages[row.key])
        self.split.set_show_content(True)
        if row.key == "deadlines":
            self.pages["deadlines"].refresh()

    def toast(self, text, timeout=3):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=timeout))
        return True

    def tick(self):
        st = self.store
        self.pages["study"].tick()
        t = st.timer
        self.sb_timer.set_visible(bool(t))
        if t:
            sub = st.subject(t["subject_id"])
            self.sb_dot.set_color(sub["color"] if sub else t["color"])
            paused = not st.timer_running()
            self.sb_subj.set_label((sub["name"] if sub else t["subject"]) + (" · paused" if paused else ""))
            e = st.timer_elapsed()
            self.sb_time.set_label(tu.clock(t["target"] - e if t["mode"] == "down" else e))

    def _close_request(self, _w):
        if not self.store.timer:
            return False
        d = Adw.AlertDialog(heading="A session is running",
                            body="Keep timing in the background (the timer stays in the top bar and the app "
                                 "reopens from the dock), or stop and save it now?")
        d.add_response("cancel", "Cancel")
        d.add_response("stop", "Stop & save")
        d.add_response("background", "Keep timing")
        d.set_response_appearance("background", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("background")
        d.set_close_response("cancel")

        def resp(_d, r):
            if r == "stop":
                self.app.stop_session()
                self.destroy()
            elif r == "background":
                self.app.keep_in_background()
                self.set_visible(False)
        d.connect("response", resp)
        d.present(self)
        return True


class StudyRoomApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win = None
        self.store = None
        self.held = False
        self._last_minute = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        self.store = Store()
        self.theme = ThemeManager(self.store)
        for name, cb in (("show", self._act_show), ("toggle-pause", self._act_pause),
                         ("stop", self._act_stop), ("quit", self._act_quit)):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.store.connect("changed", self._store_changed)
        GLib.timeout_add(250, self._tick)
        if self.store.timer:
            self.keep_in_background()   # a session was running when the app last closed - keep it alive

    def do_activate(self):
        if not self.win:
            self.win = MainWindow(self)
            self.win.connect("destroy", self._win_destroyed)
        self.win.set_visible(True)
        self.win.present()

    def _win_destroyed(self, *_):
        self.win = None

    # ----------------------------------------------------------- background timing
    def keep_in_background(self):
        if not self.held:
            self.hold()
            self.held = True

    def _store_changed(self, _s, kind):
        if kind == "timer" and not self.store.timer and self.held:
            self.held = False
            self.release()
        if kind == "timer" and self.store.timer:
            self.keep_in_background()

    def _tick(self):
        st = self.store
        t = st.timer
        if t and t["mode"] == "down" and t.get("target") and st.timer_running() \
                and st.timer_elapsed() >= t["target"]:
            self._countdown_done()
        if self.win:
            self.win.tick()
        minute = tu.now().strftime("%Y%m%d%H%M")
        if minute != self._last_minute:
            self._last_minute = minute
            if self.win:
                self.win.pages["deadlines"].minute_tick()
            else:
                st.prune_done()
        return True

    def _countdown_done(self):
        rec, secs = self.store.stop_timer(save=True, completed=True)
        name = rec["subject"] if rec else "Session"
        n = Gio.Notification.new("Countdown finished")
        n.set_body(f"{name} · {tu.dur(secs)} saved" if rec else f"{name} · {tu.dur(secs)} (too short to save)")
        n.set_priority(Gio.NotificationPriority.HIGH)
        n.set_default_action("app.show")
        self.send_notification("countdown", n)
        if self.store.get("countdown_sound"):
            self._play_sound()
        if self.win:
            self.win.toast(f"Countdown finished · {tu.dur(secs)} saved")

    def _play_sound(self):
        try:
            if Path(SOUND).exists():
                player = shutil.which("pw-play") or shutil.which("paplay")
                if player:
                    subprocess.Popen([player, SOUND], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                if shutil.which("canberra-gtk-play"):
                    subprocess.Popen(["canberra-gtk-play", "-i", "complete"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def stop_session(self):
        rec, secs = self.store.stop_timer(save=True)
        if self.win:
            if rec:
                self.win.toast(f"Saved {tu.dur(secs)} of {rec['subject']}")
            else:
                self.win.toast(f"Not saved — shorter than the minimum session length ({tu.dur(secs)})")

    # ----------------------------------------------------------- actions (also used by the top-bar indicator)
    def _act_show(self, *_):
        self.activate()

    def _act_pause(self, *_):
        if self.store.timer_running():
            self.store.pause_timer()
        else:
            self.store.resume_timer()

    def _act_stop(self, *_):
        self.stop_session()

    def _act_quit(self, *_):
        if self.win:
            self.win.close()   # goes through the running-session check
        else:
            self.quit()


def main():
    return StudyRoomApp().run(sys.argv)
