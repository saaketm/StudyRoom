"""Colour palettes. Tasks and deadlines use the 11 Google-Calendar-style event colours (by name)."""

GCAL = [
    ("Tomato", "#d50000"), ("Flamingo", "#e67c73"), ("Tangerine", "#f4511e"),
    ("Banana", "#f6bf26"), ("Sage", "#33b679"), ("Basil", "#0b8043"),
    ("Peacock", "#039be5"), ("Blueberry", "#3f51b5"), ("Lavender", "#7986cb"),
    ("Grape", "#8e24aa"), ("Graphite", "#616161"),
]
GCAL_MAP = dict(GCAL)
DEFAULT_GCAL = "Peacock"


def gcal_hex(name: str) -> str:
    return GCAL_MAP.get(name, GCAL_MAP[DEFAULT_GCAL])


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (0.5, 0.5, 0.5)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (0.5, 0.5, 0.5)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    c = lambda v: max(0, min(255, round(v * 255)))
    return f"#{c(r):02x}{c(g):02x}{c(b):02x}"


def mix(a: str, b: str, t: float) -> str:
    """Blend a -> b by t (0..1)."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(*[x + (y - x) * t for x, y in zip(ra, rb)])


def valid_hex(h) -> bool:
    if not isinstance(h, str) or len(h) != 7 or h[0] != "#":
        return False
    try:
        int(h[1:], 16)
        return True
    except ValueError:
        return False
