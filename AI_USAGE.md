# AI usage declaration

StudyRoom is **entirely AI-generated**. This file explains how, so that users and contributors can judge
the code accordingly.

## Tool and model

- **Claude Code**, Anthropic's agentic coding tool, running the **Claude Opus 5.5** model
  (`claude-opus-5-5`), working from natural-language prompts.
- Built in November 2026.

## What was AI-generated

Everything in this repository:

- the architecture (a native GTK4/libadwaita app plus an optional GNOME Shell extension);
- all of the source code: the Python app, the GNOME Shell extension, and the install and uninstall scripts;
- the visual and interaction design (layout, themes, charts, wording) and the icon (SVG);
- all documentation (README, DESIGN.md, CHANGELOG.md, this file) and the release notes;
- testing: the app was run in an isolated, headless GNOME Shell session with made-up sample data, the
  rendered screenshots were inspected, and the problems found were fixed. The screenshots in `docs/` come
  from that process.

## Review status

- The code was checked by running it (see *Testing approach* in [DESIGN.md](DESIGN.md)). It has **not**
  been through a line-by-line human code review or a security audit.
- There is no automated test suite in the repository yet.
- It is provided as-is under the MIT License, with no warranty. Please report bugs through GitHub issues.

## Commit attribution

Commits carry a `Co-Authored-By: Claude …` trailer.
