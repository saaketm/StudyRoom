"""Small reusable widgets and helpers."""
import math

from gi.repository import Adw, Gdk, Gtk

from .colors import GCAL, GCAL_MAP, hex_to_rgb, rgb_to_hex


def clear(box):
    child = box.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


def label(text="", css=(), xalign=0.0, **kw):
    lb = Gtk.Label(label=text, xalign=xalign, **kw)
    for c in css:
        lb.add_css_class(c)
    return lb


class ColorDot(Gtk.DrawingArea):
    def __init__(self, color="#888888", size=12):
        super().__init__()
        self.color = color
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_valign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def set_color(self, color):
        self.color = color
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        cr.set_source_rgb(*hex_to_rgb(self.color))
        cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 2 * math.pi)
        cr.fill()


def confirm(parent, heading, body, action, callback, destructive=True):
    d = Adw.AlertDialog(heading=heading, body=body)
    d.add_response("cancel", "Cancel")
    d.add_response("ok", action)
    d.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE if destructive
                              else Adw.ResponseAppearance.SUGGESTED)
    d.set_default_response("cancel")
    d.set_close_response("cancel")
    d.connect("response", lambda _d, r: r == "ok" and callback())
    d.present(parent)


class GcalSwatches(Gtk.Box):
    """Row of the 11 Google Calendar colours. .selected is the colour name."""

    def __init__(self, selected="Peacock", on_change=None):
        super().__init__(spacing=8)
        self.selected = selected
        self.on_change = on_change
        self.buttons = {}
        group = None
        for name, _hx in GCAL:
            b = Gtk.ToggleButton(tooltip_text=name, valign=Gtk.Align.CENTER)
            b.add_css_class("swatch")
            b.add_css_class(f"gc-{name}")
            if group:
                b.set_group(group)
            else:
                group = b
            b.set_active(name == selected)
            b.connect("toggled", self._toggled, name)
            self.buttons[name] = b
            self.append(b)

    def _toggled(self, b, name):
        if b.get_active():
            self.selected = name
            if self.on_change:
                self.on_change(name)


class SubjectColorPicker(Gtk.Box):
    """GCal swatches plus a custom colour button. .color is a hex string."""

    def __init__(self, color="#039be5"):
        super().__init__(spacing=8)
        self.color = color
        named = next((n for n, hx in GCAL if hx.lower() == color.lower()), None)
        self.sw = GcalSwatches(named or "", on_change=self._picked)
        if not named:
            for b in self.sw.buttons.values():
                b.set_active(False)
        self.append(self.sw)
        self.custom = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False),
                                            tooltip_text="Custom colour", valign=Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse(color)
        self.custom.set_rgba(rgba)
        self.custom.connect("notify::rgba", self._custom)
        self.append(self.custom)
        self._lock = False

    def _picked(self, name):
        self.color = GCAL_MAP[name]
        self._lock = True
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        self.custom.set_rgba(rgba)
        self._lock = False

    def _custom(self, btn, _p):
        if self._lock:
            return
        c = btn.get_rgba()
        self.color = rgb_to_hex(c.red, c.green, c.blue)
        for b in self.sw.buttons.values():
            if b.get_active() and GCAL_MAP.get(b.get_tooltip_text(), "").lower() != self.color.lower():
                b.set_active(False)


class Tick(Gtk.Button):
    """Round tick-box in a GCal colour."""

    def __init__(self, color_name, done, on_toggle, tooltip=None):
        super().__init__(valign=Gtk.Align.CENTER)
        self.add_css_class("tick")
        self.add_css_class(f"gc-ring-{color_name}")
        if done:
            self.add_css_class("ticked")
            self.set_icon_name("object-select-symbolic")
        self.set_tooltip_text(tooltip or ("Mark not done" if done else "Mark done"))
        self.connect("clicked", lambda *_: on_toggle())


def popover_menu(items):
    """items: list of (label, callback, destructive). Returns a MenuButton with a simple popover."""
    mb = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.CENTER)
    mb.add_css_class("flat")
    pop = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for text, cb, destructive in items:
        b = Gtk.Button(label=text)
        b.add_css_class("flat")
        b.get_child().set_xalign(0)
        if destructive:
            b.add_css_class("error")

        def run(_b, cb=cb):
            pop.popdown()
            cb()
        b.connect("clicked", run)
        box.append(b)
    pop.set_child(box)
    mb.set_popover(pop)
    return mb


def time_spin_row(title, h, m, subtitle=None):
    """An Adw.ActionRow with two spin buttons HH : MM (24-hour). Returns (row, hour_spin, min_spin)."""
    row = Adw.ActionRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    hs = Gtk.SpinButton.new_with_range(0, 23, 1)
    ms = Gtk.SpinButton.new_with_range(0, 59, 1)
    for s, v in ((hs, h), (ms, m)):
        s.set_value(v)
        s.set_valign(Gtk.Align.CENTER)
        s.set_numeric(True)
        s.connect("output", _two_digit)
    box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
    box.append(hs)
    box.append(Gtk.Label(label=":"))
    box.append(ms)
    row.add_suffix(box)
    return row, hs, ms


def _two_digit(spin):
    spin.set_text(f"{int(spin.get_adjustment().get_value()):02d}")
    return True
