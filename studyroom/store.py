"""All persistent state.

Files (in ~/.local/share/ypt-study/ unless STUDYROOM_DATA_DIR is set):
  data.json          subjects, tasks, deadlines, settings
  sessions.jsonl     one study session per line (append-only log, LLM friendly)
  timer.json         the running timer (also read by the top-bar extension)
  SESSIONS-FORMAT.md describes sessions.jsonl for future analysis
  backups/YYYY-MM-DD/ one copy of data.json + sessions.jsonl per day (last 30 kept)
"""
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from gi.repository import GLib, GObject

from . import timeutil as tu
from .colors import GCAL_MAP, DEFAULT_GCAL, valid_hex

DONE_RETENTION_DAYS = 14
BACKUPS_KEPT = 30

DEFAULT_SETTINGS = {
    "theme": "classic",
    "scheme": "system",          # system | light | dark
    "day_start": "00:00",        # study day rollover
    "first_weekday": 0,          # 0 Monday, 6 Sunday
    "countdown_minutes": 60,
    "min_session_seconds": 60,   # shorter sessions are not saved
    "countdown_sound": True,
    "last_subject": None,
}

FORMAT_DOC = """# StudyRoom session log format

`sessions.jsonl` holds one JSON object per line, one line per completed study session,
in the order they were recorded. Times are the computer's local time (system clock and
timezone), 24-hour.

| field | meaning |
|---|---|
| id | unique id of the session |
| subject | subject name at the time of the session |
| subject_id | stable id of the subject (a later rename keeps the id; an erased subject keeps its sessions) |
| color | subject colour (hex) at the time |
| mode | "countup" (stopwatch) or "countdown" (timer with target) |
| target_minutes | countdown target, null for countup |
| start / end | ISO 8601 local timestamps with UTC offset, e.g. 2026-01-18T22:40:05+00:00 |
| study_seconds | time actually studied (pauses excluded) - this is the number to analyse |
| paused_seconds | time spent paused inside the session |
| study_day | ISO date the session counts towards (sessions are attributed to the day they started; a "day" begins at the configured rollover time, default 00:00) |
| date | same study_day as DD/MM/YY (day/month/year) |
| start_time / end_time | HH:MM, 24-hour |
| manual | true if the session was added by hand afterwards instead of being timed |

Useful aggregations: total study_seconds per subject, per study_day, per ISO week; streaks of
consecutive study_days; distribution of start_time; average session length.
"""


def _uid() -> str:
    return uuid.uuid4().hex[:16]


def data_dir() -> Path:
    override = os.environ.get("STUDYROOM_DATA_DIR")
    base = Path(override) if override else Path(GLib.get_user_data_dir()) / "ypt-study"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _atomic_write(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Store(GObject.Object):
    """Emits 'changed' with a kind: subjects | sessions | tasks | deadlines | settings | timer."""

    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.dir = data_dir()
        self.data_path = self.dir / "data.json"
        self.sessions_path = self.dir / "sessions.jsonl"
        self.timer_path = self.dir / "timer.json"
        self.load_warning = None
        self._load()
        self.sessions = self._load_sessions()
        self.timer = self._load_timer()
        self._backup()
        _atomic_write(self.dir / "SESSIONS-FORMAT.md", FORMAT_DOC)
        self.prune_done()

    # ------------------------------------------------------------------ load/save
    def _load(self):
        raw = None
        if self.data_path.exists():
            try:
                raw = json.loads(self.data_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Keep the unreadable file (never delete user data), fall back to the newest backup.
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                keep = self.data_path.with_name(f"data.json.unreadable-{stamp}")
                shutil.copy2(self.data_path, keep)
                raw = self._newest_backup_data()
                self.load_warning = f"data.json could not be read. A copy was kept as {keep.name}; restored the latest backup."
        raw = raw if isinstance(raw, dict) else {}
        self.subjects = [s for s in raw.get("subjects", []) if isinstance(s, dict) and s.get("id")]
        self.tasks = [t for t in raw.get("tasks", []) if isinstance(t, dict) and t.get("id")]
        self.deadlines = [d for d in raw.get("deadlines", []) if isinstance(d, dict) and d.get("id")]
        self.settings = dict(DEFAULT_SETTINGS)
        self.settings.update({k: v for k, v in raw.get("settings", {}).items() if k in DEFAULT_SETTINGS})

    def _newest_backup_data(self):
        bdir = self.dir / "backups"
        if not bdir.exists():
            return None
        for d in sorted(bdir.iterdir(), reverse=True):
            p = d / "data.json"
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
        return None

    def save(self, kind: str):
        payload = {"version": 1, "subjects": self.subjects, "tasks": self.tasks,
                   "deadlines": self.deadlines, "settings": self.settings}
        _atomic_write(self.data_path, json.dumps(payload, indent=1, ensure_ascii=False))
        self.emit("changed", kind)

    def _backup(self):
        bdir = self.dir / "backups"
        today = datetime.now().strftime("%Y-%m-%d")
        target = bdir / today
        if not target.exists():
            target.mkdir(parents=True)
            for p in (self.data_path, self.sessions_path):
                if p.exists():
                    shutil.copy2(p, target / p.name)
        # Only ever prune folders this app created (named YYYY-MM-DD inside its own backups dir).
        dated = sorted(d for d in bdir.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name))
        for old in dated[:-BACKUPS_KEPT]:
            shutil.rmtree(old)

    # ------------------------------------------------------------------ settings
    def get(self, key):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self.save("settings")

    # ------------------------------------------------------------------ subjects
    def subject(self, sid):
        return next((s for s in self.subjects if s["id"] == sid), None)

    def add_subject(self, name: str, color: str):
        s = {"id": _uid(), "name": name.strip()[:60], "color": color if valid_hex(color) else "#039be5",
             "created": tu.now().isoformat(timespec="seconds")}
        self.subjects.append(s)
        self.save("subjects")
        return s

    def update_subject(self, sid, name: str, color: str):
        s = self.subject(sid)
        if s:
            s["name"] = name.strip()[:60] or s["name"]
            if valid_hex(color):
                s["color"] = color
            self.save("subjects")
            if self.timer and self.timer["subject_id"] == sid:
                self._write_timer()

    def erase_subject(self, sid):
        """Removes the subject from the list. Its past sessions stay in history unchanged."""
        self.subjects = [s for s in self.subjects if s["id"] != sid]
        if self.settings.get("last_subject") == sid:
            self.settings["last_subject"] = None
        self.save("subjects")

    def move_subject(self, sid, delta):
        i = next((n for n, s in enumerate(self.subjects) if s["id"] == sid), None)
        j = (i if i is not None else 0) + delta
        if i is None or not 0 <= j < len(self.subjects):
            return
        self.subjects[i], self.subjects[j] = self.subjects[j], self.subjects[i]
        self.save("subjects")

    # ------------------------------------------------------------------ sessions
    def _load_sessions(self):
        out = []
        if not self.sessions_path.exists():
            return out
        with open(self.sessions_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    s["_start"] = datetime.fromisoformat(s["start"])
                    s["_end"] = datetime.fromisoformat(s["end"])
                    out.append(s)
                except (ValueError, KeyError, TypeError):
                    continue  # a damaged line is skipped, never removed from the file
        out.sort(key=lambda s: s["_start"])
        return out

    @staticmethod
    def _public(s):
        return {k: v for k, v in s.items() if not k.startswith("_")}

    def make_session(self, subject_id, name, color, start: datetime, end: datetime,
                     study_seconds: int, mode="countup", target_minutes=None, manual=False):
        sd = tu.study_day(start, self.get("day_start"))
        return {
            "id": _uid(), "subject": name, "subject_id": subject_id, "color": color,
            "mode": mode, "target_minutes": target_minutes,
            "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
            "study_seconds": int(study_seconds),
            "paused_seconds": max(0, int((end - start).total_seconds() - study_seconds)),
            "study_day": sd.isoformat(), "date": tu.ddmmyy(sd),
            "start_time": tu.hhmm(start), "end_time": tu.hhmm(end), "manual": manual,
        }

    def add_session(self, rec: dict):
        with open(self.sessions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        rec = dict(rec)
        rec["_start"] = datetime.fromisoformat(rec["start"])
        rec["_end"] = datetime.fromisoformat(rec["end"])
        self.sessions.append(rec)
        self.sessions.sort(key=lambda s: s["_start"])
        self.emit("changed", "sessions")

    def delete_session(self, sid):
        self.sessions = [s for s in self.sessions if s["id"] != sid]
        text = "".join(json.dumps(self._public(s), ensure_ascii=False) + "\n" for s in self.sessions)
        _atomic_write(self.sessions_path, text)
        self.emit("changed", "sessions")

    def session_key(self, s):
        """Grouping key for history: live subjects by id, erased subjects by their recorded name+colour."""
        if self.subject(s.get("subject_id")):
            return s["subject_id"]
        return f"~{s.get('subject', '?')}|{s.get('color', '')}"

    def session_display(self, s):
        """(name, colour) to show for a session - current subject look if it still exists."""
        sub = self.subject(s.get("subject_id"))
        if sub:
            return sub["name"], sub["color"]
        return s.get("subject", "?"), s.get("color", "#888888")

    def seconds_between(self, start: datetime, end: datetime, key=None):
        """Studied seconds of sessions whose start falls in [start, end)."""
        total = 0
        for s in self.sessions:
            if start <= s["_start"] < end and (key is None or self.session_key(s) == key):
                total += s["study_seconds"]
        return total

    # ------------------------------------------------------------------ tasks / deadlines
    def _clean_item(self, d, kind):
        out = {"title": str(d.get("title", "")).strip()[:200],
               "color": d.get("color") if d.get("color") in GCAL_MAP else DEFAULT_GCAL,
               "notes": str(d.get("notes", "")).strip()[:2000]}
        if kind == "deadlines":
            out["date"] = d["date"]
            out["time"] = d.get("time") or ""
        return out

    def _items(self, kind):
        return self.tasks if kind == "tasks" else self.deadlines

    def add_item(self, kind, d):
        it = self._clean_item(d, kind)
        it.update({"id": _uid(), "done": False, "done_at": None,
                   "created": tu.now().isoformat(timespec="seconds")})
        self._items(kind).append(it)
        self.save(kind)
        return it

    def update_item(self, kind, iid, d):
        for it in self._items(kind):
            if it["id"] == iid:
                it.update(self._clean_item(d, kind))
        self.save(kind)

    def set_done(self, kind, iid, done: bool):
        for it in self._items(kind):
            if it["id"] == iid:
                it["done"] = done
                it["done_at"] = tu.now().isoformat(timespec="seconds") if done else None
        self.save(kind)

    def delete_item(self, kind, iid):
        if kind == "tasks":
            self.tasks = [t for t in self.tasks if t["id"] != iid]
        else:
            self.deadlines = [t for t in self.deadlines if t["id"] != iid]
        self.save(kind)

    @staticmethod
    def done_expires(it) -> datetime | None:
        if not it.get("done") or not it.get("done_at"):
            return None
        try:
            return datetime.fromisoformat(it["done_at"]) + timedelta(days=DONE_RETENTION_DAYS)
        except ValueError:
            return None

    def prune_done(self):
        """Completed tasks/deadlines disappear 14 days after being ticked off."""
        n = tu.now()
        changed = []
        for kind in ("tasks", "deadlines"):
            items = self._items(kind)
            keep = [it for it in items if not (self.done_expires(it) and self.done_expires(it) <= n)]
            if len(keep) != len(items):
                if kind == "tasks":
                    self.tasks = keep
                else:
                    self.deadlines = keep
                changed.append(kind)
        for kind in changed:
            self.save(kind)

    @staticmethod
    def deadline_dt(it) -> datetime:
        h, m = tu.parse_hhmm(it.get("time") or "23:59")
        d = datetime.fromisoformat(it["date"])
        return d.replace(hour=h, minute=m).astimezone()

    # ------------------------------------------------------------------ timer
    # timer = {subject_id, subject, color, mode: up|down, target (s)|None,
    #          started_at (epoch), accum (s), run_start (epoch)|None}
    def _load_timer(self):
        try:
            t = json.loads(self.timer_path.read_text(encoding="utf-8"))
            if t.get("active") and t.get("subject_id"):
                return t
        except (OSError, ValueError):
            pass
        return None

    def _write_timer(self):
        if self.timer:
            sub = self.subject(self.timer["subject_id"])
            if sub:
                self.timer["subject"], self.timer["color"] = sub["name"], sub["color"]
            self.timer["active"] = True
            _atomic_write(self.timer_path, json.dumps(self.timer))
        else:
            _atomic_write(self.timer_path, json.dumps({"active": False}))
        self.emit("changed", "timer")

    def timer_elapsed(self) -> float:
        t = self.timer
        if not t:
            return 0.0
        e = t["accum"] + ((time.time() - t["run_start"]) if t.get("run_start") else 0)
        if t["mode"] == "down" and t.get("target"):
            e = min(e, t["target"])
        return e

    def timer_running(self) -> bool:
        return bool(self.timer and self.timer.get("run_start"))

    def start_timer(self, subject_id, mode="up", target=None):
        sub = self.subject(subject_id)
        if not sub or self.timer:
            return
        t = time.time()
        self.timer = {"subject_id": subject_id, "subject": sub["name"], "color": sub["color"],
                      "mode": mode, "target": target, "started_at": t, "accum": 0.0, "run_start": t}
        self.settings["last_subject"] = subject_id
        self.save("settings")
        self._write_timer()

    def pause_timer(self):
        if self.timer_running():
            self.timer["accum"] = self.timer_elapsed()
            self.timer["run_start"] = None
            self._write_timer()

    def resume_timer(self):
        if self.timer and not self.timer.get("run_start"):
            self.timer["run_start"] = time.time()
            self._write_timer()

    def stop_timer(self, save=True, completed=False):
        """Ends the session. Returns (saved_record | None, studied_seconds).
        A completed countdown is always saved; otherwise the minimum-length setting applies."""
        t = self.timer
        if not t:
            return None, 0
        studied = int(self.timer_elapsed())
        end_ts = time.time()
        if t["mode"] == "down" and t.get("target") and studied >= t["target"] and t.get("run_start"):
            # Finished countdown: end exactly when the target was reached.
            end_ts = min(end_ts, t["run_start"] + (t["target"] - t["accum"]))
        self.timer = None
        self._write_timer()
        rec = None
        if save and studied > 0 and (completed or studied >= int(self.get("min_session_seconds"))):
            sub = self.subject(t["subject_id"])
            name, color = (sub["name"], sub["color"]) if sub else (t["subject"], t["color"])
            rec = self.make_session(
                t["subject_id"], name, color, tu.from_ts(t["started_at"]), tu.from_ts(end_ts), studied,
                mode="countdown" if t["mode"] == "down" else "countup",
                target_minutes=round(t["target"] / 60) if t.get("target") else None)
            self.add_session(rec)
        return rec, studied
