# AI usage declaration

StudyRoom was built with substantial help from generative AI. This file explains how, so that users and
contributors can judge the code accordingly.

## Tool and model

- **Claude Code**, Anthropic's agentic coding tool, running the **Claude Opus 5.5** model
  (`claude-opus-5-5`).
- Built in November 2026.

## What the AI did

- Proposed the architecture (native GTK4/libadwaita app plus an optional GNOME Shell extension).
- Wrote essentially **all of the source code**: the Python app, the GNOME Shell extension, the install and
  uninstall scripts, the icon (SVG), and the documentation (README, DESIGN.md, this file).
- Made most visual and interaction design decisions (layout, themes, charts, wording).
- Tested the app in an isolated, headless GNOME Shell session with made-up sample data, inspected the
  rendered screenshots, and fixed the problems it found. The screenshots in `docs/` come from that process.

## What the human did

- Defined the requirements and priorities: which features to include, how the timer, subjects, history,
  to-do list and calendar should behave, date/time conventions, and the safety constraints.
- Answered the AI's clarifying questions, made the final decisions (including the name), and asked for
  the project to be published.

## Review status

- The code was produced by the AI and checked by running it (see *Testing approach* in
  [DESIGN.md](DESIGN.md)). It has **not** been through a line-by-line human code review or a security audit.
- There is no automated test suite in the repository yet.
- It is provided as-is under the MIT License, with no warranty. Please report bugs through GitHub issues.

## Commit attribution

Commits written with AI help carry a `Co-Authored-By: Claude …` trailer.
