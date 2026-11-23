# Changelog

All notable changes to StudyRoom. Dates are DD/MM/YYYY.

## 1.0.1 – 24/11/2026

### Fixed
- **Crash when opening a task or deadline.** Clicking a task in the To-do list, or a deadline in the
  Calendar's day / Upcoming / Completed lists, could crash the app instead of opening the editor
  (the click handler re-triggered itself in a loop). Clicking an item now opens its editor, where it
  can be rescheduled, edited or deleted.
- **Double-clicking a day in the Calendar did nothing.** The first click redrew the whole month, so the
  second click never registered as a double-click. Double-clicking an empty part of a day now adds a
  deadline on that day.

### Added
- Double-clicking a deadline's coloured chip in the Calendar grid opens that deadline for editing.

## 1.0.0 – 18/11/2026

- First public release: subject-based study timer (count-up and countdown), all-time history with charts,
  to-do list and deadline calendar, themes, optional top-bar timer.
