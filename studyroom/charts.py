"""Native (cairo) charts for the History page: stacked bars and a 24-hour day timeline."""
import math

from gi.repository import GLib, Gtk, Pango, PangoCairo

from . import timeutil as tu
from .colors import hex_to_rgb

GAP = 2      # surface gap between stacked segments / adjacent bars
RADIUS = 4   # rounded data-end


def _rounded_top(cr, x, y, w, h, r):
    r = min(r, w / 2, h)
    cr.move_to(x, y + h)
    cr.line_to(x, y + r)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.line_to(x + w, y + h)
    cr.close_path()


def _nice_step(max_h):
    for step in (0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 24, 48, 100, 200, 500, 1000):
        if max_h / step <= 5:
            return step
    return 2000


class StackedBars(Gtk.DrawingArea):
    """buckets: list of dicts {label, tip, segs: [(name, color, seconds)]} - segs in fixed subject order."""

    def __init__(self):
        super().__init__(hexpand=True)
        self.set_content_height(240)
        self.buckets = []
        self.geom = []  # (x0, x1, bucket)
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._tooltip)
        self.set_draw_func(self._draw)

    def set_data(self, buckets):
        self.buckets = buckets
        self.queue_draw()

    def _text(self, cr, s, x, y, fg, alpha, align="center", size=9):
        lay = self.create_pango_layout(s)
        fd = Pango.FontDescription.from_string(f"Sans {size}")
        lay.set_font_description(fd)
        w, h = lay.get_pixel_size()
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        cr.set_source_rgba(fg.red, fg.green, fg.blue, alpha)
        cr.move_to(x, y - h / 2)
        PangoCairo.show_layout(cr, lay)
        return w

    def _draw(self, _a, cr, W, H):
        fg = self.get_color()
        left, right, top, bottom = 44, 8, 10, 26
        pw, ph = W - left - right, H - top - bottom
        n = len(self.buckets)
        if n == 0 or pw <= 0:
            return
        totals = [sum(s[2] for s in b["segs"]) for b in self.buckets]
        max_h = max(totals) / 3600 if totals else 0
        step = _nice_step(max(max_h, 1))
        top_h = max(step, math.ceil(max_h / step) * step)
        # recessive grid + hour labels
        cr.set_line_width(1)
        k = 0
        while k * step <= top_h + 1e-9:
            y = top + ph - (k * step / top_h) * ph
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.08 if k else 0.25)
            cr.move_to(left, round(y) + 0.5)
            cr.line_to(W - right, round(y) + 0.5)
            cr.stroke()
            v = k * step
            self._text(cr, (f"{v:g}h"), left - 6, y, fg, 0.55, "right")
            k += 1
        slot = pw / n
        bw = max(3, min(42, slot * 0.62))
        label_every = max(1, math.ceil(n / max(1, pw // 34)))
        self.geom = []
        for i, b in enumerate(self.buckets):
            cx = left + slot * (i + 0.5)
            x0 = cx - bw / 2
            self.geom.append((left + slot * i, left + slot * (i + 1), b))
            y = top + ph
            segs = [s for s in b["segs"] if s[2] > 0]
            for j, (_name, color, secs) in enumerate(segs):
                h = secs / 3600 / top_h * ph
                last = j == len(segs) - 1
                hh = max(h - (0 if last else GAP), 1)
                cr.set_source_rgb(*hex_to_rgb(color))
                if last:
                    _rounded_top(cr, x0, y - hh, bw, hh, RADIUS)
                    cr.fill()
                else:
                    cr.rectangle(x0, y - hh, bw, hh)
                    cr.fill()
                y -= h
            if i % label_every == 0:
                self._text(cr, b["label"], cx, top + ph + 13, fg, 0.6)

    def _tooltip(self, _w, x, _y, _kb, tip):
        for x0, x1, b in self.geom:
            if x0 <= x < x1:
                segs = [s for s in b["segs"] if s[2] > 0]
                total = sum(s[2] for s in segs)
                lines = [f"<b>{b['tip']}</b>   {tu.dur(total)}"]
                for name, _c, secs in sorted(segs, key=lambda s: -s[2]):
                    lines.append(f"{GLib_escape(name)}   {tu.dur(secs)}")
                tip.set_markup("\n".join(lines))
                return True
        return False


def GLib_escape(s):
    return GLib.markup_escape_text(s)


class DayTimeline(Gtk.DrawingArea):
    """Sessions of one study day laid on a 24-hour axis starting at the day-start time."""

    def __init__(self):
        super().__init__(hexpand=True)
        self.set_content_height(96)
        self.blocks = []   # (start_dt, end_dt, name, color, secs)
        self.day_start = None
        self.geom = []
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._tooltip)
        self.set_draw_func(self._draw)

    def set_data(self, day_start_dt, blocks):
        self.day_start, self.blocks = day_start_dt, blocks
        self.queue_draw()

    def _draw(self, _a, cr, W, H):
        if self.day_start is None:
            return
        fg = self.get_color()
        left, right = 8, 8
        lane_y, lane_h = 16, 44
        pw = W - left - right
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
        cr.rectangle(left, lane_y, pw, lane_h)
        cr.fill()
        for hr in range(0, 25, 3):
            x = left + pw * hr / 24
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
            cr.set_line_width(1)
            cr.move_to(round(x) + 0.5, lane_y)
            cr.line_to(round(x) + 0.5, lane_y + lane_h + 4)
            cr.stroke()
            lab = (self.day_start.hour + hr) % 24
            lay = self.create_pango_layout(f"{lab:02d}:{self.day_start.minute:02d}")
            lay.set_font_description(Pango.FontDescription.from_string("Sans 8"))
            w, _h = lay.get_pixel_size()
            tx = min(max(x - w / 2, 0), W - w)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.move_to(tx, lane_y + lane_h + 8)
            PangoCairo.show_layout(cr, lay)
        self.geom = []
        for st, en, name, color, secs in self.blocks:
            a = (st - self.day_start).total_seconds() / 86400
            b = (en - self.day_start).total_seconds() / 86400
            a, b = max(0, a), min(1, b)
            if b <= a:
                continue
            x0, x1 = left + pw * a, left + pw * b
            w = max(3, x1 - x0 - GAP)
            cr.set_source_rgb(*hex_to_rgb(color))
            r = min(RADIUS, w / 2)
            cr.new_sub_path()
            cr.arc(x0 + w - r, lane_y + r, r, -math.pi / 2, 0)
            cr.arc(x0 + w - r, lane_y + lane_h - r, r, 0, math.pi / 2)
            cr.arc(x0 + r, lane_y + lane_h - r, r, math.pi / 2, math.pi)
            cr.arc(x0 + r, lane_y + r, r, math.pi, 1.5 * math.pi)
            cr.close_path()
            cr.fill()
            self.geom.append((x0 - 3, x0 + w + 3, (st, en, name, secs)))

    def _tooltip(self, _w, x, y, _kb, tip):
        for x0, x1, (st, en, name, secs) in self.geom:
            if x0 <= x <= x1:
                tip.set_markup(f"<b>{GLib_escape(name)}</b>\n{tu.hhmm(st)} – {tu.hhmm(en)} · {tu.dur(secs)}")
                return True
        return False


class ShareBar(Gtk.DrawingArea):
    """A single thin proportional bar (subject breakdown)."""

    def __init__(self, fraction, color):
        super().__init__(hexpand=True, valign=Gtk.Align.CENTER)
        self.fraction, self.color = fraction, color
        self.set_content_height(8)
        self.set_draw_func(self._draw)

    def _draw(self, _a, cr, W, H):
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.07)
        self._pill(cr, 0, W, H)
        if self.fraction > 0:
            cr.set_source_rgb(*hex_to_rgb(self.color))
            self._pill(cr, 0, max(H, W * self.fraction), H)

    @staticmethod
    def _pill(cr, x, w, h):
        r = h / 2
        cr.new_sub_path()
        cr.arc(x + w - r, r, r, -math.pi / 2, math.pi / 2)
        cr.arc(x + r, r, r, math.pi / 2, 1.5 * math.pi)
        cr.close_path()
        cr.fill()
