"""App themes (accent + tinted surfaces for light and dark) and the base stylesheet."""
from gi.repository import Adw, Gdk, Gtk

from .colors import GCAL, mix

# name -> (label, accent, light tint, dark tint). Tints of None = stock Adwaita surfaces.
THEMES = {
    "classic":  ("Classic",  "#3584e4", None,      None),
    "ocean":    ("Ocean",    "#0e8aa8", "#e6f2f5", "#0f1b20"),
    "forest":   ("Forest",   "#2e8b57", "#e9f3ec", "#121b16"),
    "rose":     ("Rose",     "#d1497b", "#f9ebf0", "#1f1519"),
    "sunset":   ("Sunset",   "#e0662c", "#fbefe7", "#1f1712"),
    "lavender": ("Lavender", "#7b5fd3", "#f0ecfa", "#17141f"),
    "mocha":    ("Mocha",    "#9c6b45", "#f4eee8", "#1b1714"),
    "graphite": ("Graphite", "#5f6b7a", "#eef0f2", "#151618"),
    "midnight": ("Midnight", "#6c8cff", "#e9edf9", "#0d1020"),
}

BASE_CSS = """
.timer-big { font-size: 64px; font-weight: 300; font-feature-settings: "tnum"; letter-spacing: 1px; }
.timer-sub { font-size: 15px; }
.today-total { font-size: 28px; font-weight: 600; font-feature-settings: "tnum"; }
.tnum { font-feature-settings: "tnum"; }
.big-pill { padding: 10px 28px; font-size: 16px; font-weight: 600; }
.section-title { font-size: 13px; font-weight: 700; letter-spacing: 0.04em; }
.stat-value { font-size: 24px; font-weight: 600; font-feature-settings: "tnum"; }
.stat-label { font-size: 12px; }
.chart-card { padding: 16px; }
.left-soon { color: var(--warning-color); font-weight: 600; }
.left-over { color: var(--error-color); font-weight: 600; }
.done-title { text-decoration-line: line-through; opacity: 0.6; }
.tick { min-width: 22px; min-height: 22px; padding: 0; border-radius: 999px; }
.swatch { min-width: 26px; min-height: 26px; padding: 0; border-radius: 999px; border: 2px solid transparent; }
.swatch:checked { border-color: var(--window-fg-color); }
.cal-cell { padding: 4px; border-radius: 10px; min-height: 84px; }
.cal-cell.selected-day { background: color-mix(in srgb, var(--accent-bg-color) 16%, transparent); }
.cal-cell.other-month { opacity: 0.45; }
.cal-daynum { font-weight: 600; font-feature-settings: "tnum"; min-width: 24px; min-height: 24px; border-radius: 999px; }
.cal-today { background: var(--accent-bg-color); color: var(--accent-fg-color); }
.cal-chip { font-size: 11px; border-radius: 5px; padding: 1px 5px; color: white; }
.cal-head { font-size: 12px; font-weight: 700; opacity: 0.6; }
.sidebar-timer { padding: 10px 12px; border-radius: 12px; background: color-mix(in srgb, var(--accent-bg-color) 14%, transparent); }
.subject-row-running { background: color-mix(in srgb, var(--accent-bg-color) 12%, transparent); }
.theme-card { padding: 8px; border-radius: 14px; }
.theme-card:checked { background: color-mix(in srgb, var(--accent-bg-color) 18%, transparent); }
.month-head { font-size: 12px; font-weight: 700; letter-spacing: 0.05em; opacity: 0.65; margin-top: 12px; }
"""


def _gcal_css():
    out = []
    for name, hx in GCAL:
        out.append(f".gc-{name} {{ background-color: {hx}; }}")
        out.append(f".tick.gc-ring-{name} {{ border: 2px solid {hx}; background: transparent; }}")
        out.append(f".tick.gc-ring-{name}:hover {{ background: color-mix(in srgb, {hx} 22%, transparent); }}")
        out.append(f".tick.gc-ring-{name}.ticked {{ background: {hx}; color: white; }}")
        out.append(f".stripe-{name} {{ border-left: 4px solid {hx}; }}")
    out.append(".cal-chip.gc-Banana { color: #3b2f00; }")
    return "\n".join(out)


def _theme_css(name: str, dark: bool) -> str:
    _, accent, light, darkt = THEMES.get(name, THEMES["classic"])
    lines = [f"--accent-bg-color: {accent};",
             f"--accent-color: {mix(accent, '#ffffff', 0.35) if dark else mix(accent, '#000000', 0.12)};",
             "--accent-fg-color: #ffffff;"]
    tint = darkt if dark else light
    if tint:
        if dark:
            surf = {"window": tint, "view": mix(tint, "#ffffff", 0.03), "headerbar": mix(tint, "#ffffff", 0.05),
                    "sidebar": mix(tint, "#ffffff", 0.06), "card": mix(tint, "#ffffff", 0.07),
                    "popover": mix(tint, "#ffffff", 0.09), "dialog": mix(tint, "#ffffff", 0.07)}
        else:
            surf = {"window": tint, "view": mix(tint, "#ffffff", 0.6), "headerbar": tint,
                    "sidebar": mix(tint, accent, 0.06), "card": mix(tint, "#ffffff", 0.75),
                    "popover": mix(tint, "#ffffff", 0.8), "dialog": mix(tint, "#ffffff", 0.5)}
        lines += [f"--window-bg-color: {surf['window']};", f"--view-bg-color: {surf['view']};",
                  f"--headerbar-bg-color: {surf['headerbar']};", f"--sidebar-bg-color: {surf['sidebar']};",
                  f"--secondary-sidebar-bg-color: {surf['sidebar']};", f"--card-bg-color: {surf['card']};",
                  f"--popover-bg-color: {surf['popover']};", f"--dialog-bg-color: {surf['dialog']};",
                  f"--overview-bg-color: {surf['window']};"]
    return ":root { " + " ".join(lines) + " }"


class ThemeManager:
    def __init__(self, store):
        self.store = store
        display = Gdk.Display.get_default()
        base = Gtk.CssProvider()
        base.load_from_string(BASE_CSS + _gcal_css())
        Gtk.StyleContext.add_provider_for_display(display, base, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.theme_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, self.theme_provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.sm = Adw.StyleManager.get_default()
        self.sm.connect("notify::dark", lambda *_: self.apply_theme())
        store.connect("changed", lambda _s, kind: kind == "settings" and self.apply())
        self.apply()

    def apply(self):
        scheme = self.store.get("scheme")
        self.sm.set_color_scheme({"light": Adw.ColorScheme.FORCE_LIGHT,
                                  "dark": Adw.ColorScheme.FORCE_DARK}.get(scheme, Adw.ColorScheme.DEFAULT))
        self.apply_theme()

    def apply_theme(self):
        self.theme_provider.load_from_string(_theme_css(self.store.get("theme"), self.sm.get_dark()))
