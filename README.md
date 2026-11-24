# Pino

A voice companion with a screen. You call it by name («Pino», «ehi Pino»), talk to
it while you cook or drive, and it gets things done with **Claude Code** and the connectors you
already have (messages, mail, calendar, documents), plus its own alarms, timers, reminders and
lists. What is easier to understand by looking at it (a recipe step by step, tomorrow's events, the
shopping list) goes on a card, one per topic, drawn with **A2UI**, Google's protocol for
agent-generated interfaces.

One Pino, one memory, many bodies: today a tablet, tomorrow WhatsApp and a small holographic screen.
It quietly remembers what lasts about you and your people. Formerly Frankino. Site: [iampino.com](https://iampino.com).

```
Android tablet  ── voice (PCM) ──►  server  ── text ──►  Claude Code (Agent SDK)
  listens,      ◄── voice + A2UI ──  transcribes, speaks,  claude.ai connectors + MCP
  speaks, shows                      asks for confirmation card tools (A2UI), alarms, lists
```

## What you need

- **Your own Claude subscription.** The server runs Claude Code with *your* login: on the server
  you run `claude`, do `/login` once, and that's it. Pino offers no login of its own, does not
  ask for your credentials and never touches them. It is meant for personal use.
- **An OpenAI key** (or ElevenLabs) to transcribe and speak: Claude does not take audio.
- **An Android tablet** and a private network between tablet and server (Tailscale recommended).
  The server must not be exposed to the internet.

## Starting the server

```bash
cd server
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -e ".[dev,mac]"
cp ../.env.example .env        # fill in PINO_TOKEN and OPENAI_API_KEY
.venv/bin/python -m pino   # listens on :4390
.venv/bin/pytest               # tests
```

To try it without a tablet, from the Mac: `.venv/bin/python ../tools/prova_mac.py --token <gettone>`
(by voice) or with `--scrivi` (by text). `<gettone>` is the token, the value of `PINO_TOKEN`.

## The Android app

It lives in `android/`. You need Java 17 and the Android SDK (platform 37.1); on a Mac with
Homebrew: `brew install openjdk@17 android-commandlinetools`, then
`sdkmanager "platform-tools" "platforms;android-37.1" "build-tools;36.0.0"`.

```bash
cd android
echo "sdk.dir=/opt/homebrew/share/android-commandlinetools" > local.properties
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew assembleDebug testDebugUnitTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

On first launch it asks for the microphone and notifications, then for the server address (its
Tailscale name, for example `mio-mac:4390`) and the token. It downloads the small Italian
[Vosk](https://alphacephei.com/vosk/models) model once (about 50 MB) for the wake word.

How it listens:
- **It waits for its name** («Pino», «ehi Pino», «ciao Pino»). It recognizes it on the tablet with
  a closed grammar: until it hears the name, nothing goes to the server.
- **One button**: the circle in the middle shows the state (off, waiting, listening, thinking,
  speaking) and does the obvious thing for it: listen without the name, finish, or stop.
- **Right after an answer** it listens for a few seconds even without the name; «stop», «basta» or
  «grazie» end the conversation.
- **If you call it while it is speaking** it turns its voice down and the server checks the
  sentence: if someone really called, it goes quiet and listens; if it was its own voice, it carries
  on.
- The cards are drawn with the official Compose A2UI renderer (`androidx.a2ui`, alpha).

To try it without a voice, from the computer:
`adb shell am start -a dev.pino.app.ASCOLTA --es text "'Pino, la carbonara per due'"`.

## How it works

The path of a question, what is kept and where, model and costs, connectors, the microphone switch
and how it differs from Claude, explained without code: [`docs/how-it-works.md`](docs/how-it-works.md).

## Deployment

Server on AWS inside a Tailscale network, tablet set up over adb, side key instead of Gemini: every
step is in [`docs/deployment.md`](docs/deployment.md), scripts in `deploy/aws/`.

## Outward actions

Every tool that is not clearly read-only asks for confirmation: the screen shows what it is about
to do, and you say «sì», «no» or «non chiedermelo più» (yes, no, don't ask me again), or use the
buttons. «Don't ask me again» applies to that one tool and can be withdrawn
(`POST /permessi/ritira?tool=…`).

## What stays on the server

The audio of what you say, for 30 days (then it is deleted, the text stays), the transcripts, the
journal of every question (timings, tools, errors), the cards, alarms and lists, and the
permissions. All of it in `PINO_DATA`, never in the repo. Recordings that were not meant for
Pino (it woke up without anyone calling it) are deleted at once, audio and text. Read the
journal with `deploy/aws/remoto.sh registro <hours>` or `python -m pino.journal`.

## Releases

Versions follow [Semantic Versioning](https://semver.org/) and are listed in
[`CHANGELOG.md`](CHANGELOG.md). Each one is a tag `vX.Y.Z` and a
[GitHub release](https://github.com/alessio-ragni/pino/releases) with the Android APK attached.
How a release is cut is in `.claude/skills/release/SKILL.md`.

## Layout

- `server/` — FastAPI + Claude Agent SDK. Protocol with the tablet: [`docs/protocol.md`](docs/protocol.md).
- `android/` — the tablet app (Kotlin + Compose).
- `deploy/aws/` — the AWS machine: creation, first boot, remote commands.
- `tools/` — tools for testing (the Mac acting as a tablet, the wake word).

Changes are listed in [`CHANGELOG.md`](CHANGELOG.md).
