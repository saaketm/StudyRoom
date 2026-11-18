"""Time helpers. Everything uses the local system clock, 24-hour time, DD/MM/YY dates."""
from datetime import datetime, date, timedelta

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTHS_SHORT = [m[:3] for m in MONTHS]


def now() -> datetime:
    """Current local time (system clock, system timezone), timezone-aware."""
    return datetime.now().astimezone()


def from_ts(ts: float) -> datetime:
    return datetime.fromtimestamp(ts).astimezone()


def ddmmyy(d) -> str:
    return d.strftime("%d/%m/%y")


def ddmmyyyy(d) -> str:
    return d.strftime("%d/%m/%Y")


def hhmm(dt) -> str:
    return dt.strftime("%H:%M")


def parse_hhmm(s: str) -> tuple[int, int]:
    try:
        h, m = s.split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except (ValueError, AttributeError):
        pass
    return 0, 0


def study_day(dt: datetime, day_start: str = "00:00") -> date:
    """The 'study day' a moment belongs to. With day_start 05:00, 02:00 on the 19th counts as the 18th."""
    h, m = parse_hhmm(day_start)
    return (dt - timedelta(hours=h, minutes=m)).date()


def day_bounds(d: date, day_start: str = "00:00") -> tuple[datetime, datetime]:
    """Start and end (local, aware) of a study day."""
    h, m = parse_hhmm(day_start)
    start = datetime(d.year, d.month, d.day, h, m).astimezone()
    return start, (start + timedelta(days=1))


def clock(secs: float) -> str:
    """HH:MM:SS"""
    secs = max(0, int(secs))
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def dur(secs: float, short: bool = False) -> str:
    """Human duration: '3h 24m', '24m', '0m'."""
    secs = max(0, int(secs))
    h, m = secs // 3600, secs % 3600 // 60
    if h and m:
        return f"{h}h {m:02d}m" if not short else f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    if m == 0 and secs > 0:
        return f"{secs}s"
    return f"{m}m"


def week_start(d: date, first_weekday: int = 0) -> date:
    """first_weekday: 0 = Monday, 6 = Sunday."""
    return d - timedelta(days=(d.weekday() - first_weekday) % 7)


def time_left(target: datetime, ref: datetime) -> tuple[str, str]:
    """('2d 4h left', css class): compact countdown text for a deadline."""
    ms = (target - ref).total_seconds()
    neg = ms < 0
    a = abs(ms)
    m = int(a // 60)
    h = m // 60
    d = h // 24
    if d >= 1:
        s = f"{d}d" + (f" {h % 24}h" if d < 7 and h % 24 else "")
    elif h >= 1:
        s = f"{h}h" + (f" {m % 60}m" if m % 60 else "")
    else:
        s = f"{m}m"
    if neg:
        return s + " overdue", "over"
    return s + " left", ("soon" if ms < 86400 else "")
