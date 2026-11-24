# Pino — guide for Claude

A personal assistant with a voice and a screen: one Pino, one memory, many bodies (today an Android
tablet), a Python server behind, Claude Code (Agent SDK, logged in with the subscription of whoever
hosts it) as the brain, A2UI for the screen. Formerly Frankino; the site is `site/` (iampino.com).
Start simple and add things as they are needed: no architecture ahead of time.

## Rules

- **Public repo.** Never secrets, audio, transcripts, real names or real numbers: not in the code,
  not in the tests, not in the examples. `.env` and `PINO_DATA` stay outside the repo.
- **Never `ANTHROPIC_API_KEY`.** The server uses the subscription login; if the key is set, the CLI
  prefers it and bills per use.
- **Pino offers no Claude.ai login and never touches credentials.** Everyone does `/login`
  themselves.
- **Outward actions go through the gate** (`server/pino/confirm.py`, PreToolUse hook). Cautious
  by design: it asks about everything except what is clearly read-only. Do not replace it with
  `can_use_tool`: with user settings in «auto» mode, it is never called.
- **Voice and transcription are interchangeable** (`server/pino/speech/`): a new service is one
  file and one line in the dictionaries, never a scattered `if`.
- **The screen speaks A2UI** (`server/pino/a2ui.py`), version from `PINO_A2UI_VERSION`.
  Everything that reaches the tablet is checked against the renderer's catalog (`validate`): the
  alpha renderer crashes the whole app on some mistakes (a zero `weight`), so nothing unchecked
  goes through. Common cards are templates filled with plain data; prefer adding a template to
  asking Claude for long A2UI.
- **Pino's own tools** (`server/pino/home.py`: alarms, timers, reminders, lists,
  memory, `report_missing`) never go through the gate. Nothing in the agenda, the lists or the memory
  is deleted: items end with a date and a reason. The memory belongs to one person and is written
  silently.
- **Every turn is journaled** (`turns`, `tool_calls`, `events`, `missing_tools` in `store.py`). A
  new step that can be slow or fail writes its timing or its error there.
- **Only the household connectors** reach Claude (`PINO_CONNECTORS`, `UNUSED_TOOLS` in
  `agent.py`): every tool description is sent with every request and costs time.
- The protocol with the tablet is in `docs/protocol.md`: if you change it, change the document.
- How Pino works, for people who do not read code, is in `docs/how-it-works.md`; the setup
  steps are in `docs/deployment.md`. Keep them in line with what the code does.

## Language

- **Everything in the repo is written in English**: names in the code, comments, docstrings, docs,
  changelog, commit messages.
- **The Android app's on-screen strings** have English defaults in `res/values/strings.xml` and an
  Italian translation in `res/values-it/strings.xml`. A new string goes in both.
- **What Pino says aloud follows the language the person speaks.**

## Commands

```bash
cd server
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pino
.venv/bin/python ../tools/prova_mac.py --token <gettone> [--scrivi]
```

Server on AWS (the owner's account, profile and region from the environment; steps in
`docs/deployment.md`):

```bash
AWS_PROFILE=<profile> deploy/aws/remoto.sh aggiorna          # after the push: git pull + restart
AWS_PROFILE=<profile> deploy/aws/remoto.sh registro 6        # the journal: last 6 hours
AWS_PROFILE=<profile> deploy/aws/remoto.sh 'journalctl -u pino -n 50 --no-pager'
```

Android app (Java 17 from Homebrew, SDK in `/opt/homebrew/share/android-commandlinetools`):

```bash
cd android
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew assembleDebug testDebugUnitTest lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
# ask a written question from the tablet's own session, then look at the screen
adb shell am start -a dev.pino.app.ASCOLTA --es text "'Pino, la carbonara per due'"
adb exec-out screencap -p > screen.png
```

Testing on the real tablet speaks aloud in someone's home and may read their calendar: keep test
questions few and harmless, and remove anything a test created (an alarm on the Clock app, a list
item).

## Versions and releases

One version for the whole project: `server/pino/__init__.py` (`__version__`),
`server/pyproject.toml`, and `versionName`/`versionCode` in `android/app/build.gradle.kts`
(`versionCode` = major×10000 + minor×100 + patch). `server/tests/test_version.py` fails when they
disagree. A release is cut only when asked, with the `release` skill (`.claude/skills/release/`):
changelog, tests, commit, push, tag `vX.Y.Z`, GitHub release with the APK, server update, install on
the tablet.

## Changelog

`CHANGELOG.md` at the repo root, updated at every commit (the `changelog` skill says how). Format:
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). New entries go under `## [Unreleased]`
until a version is cut. Written in English for a reader who does not read code: say what changes
for the person using Pino, not which functions changed.
