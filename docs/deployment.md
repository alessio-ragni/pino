# Deployment — from a new tablet to Pino answering

This is the path taken the first time, step by step, with a Galaxy Tab A11 (Android 16, One UI
8.5, menus in English) and the server on a small Linux VPS. It works for any Android 11+ tablet and
any Linux machine that stays on: only the menu names change.

How Pino behaves once it is running is explained in [`how-it-works.md`](how-it-works.md); the
messages between tablet and server are in [`protocol.md`](protocol.md).

## How it is built

```
Tablet ──Tailscale (private network)──► Linux server that stays on (a VPS, a mini PC at home)
  Android app                              Python server + Claude Code (subscription login)
  - wake word on the tablet                - SQLite and audio on disk
  - streaming voice                        - settings and secrets in ~/.config/pino/env
  - A2UI cards                                     │
                                                   ▼
                     OpenAI (understanding and speaking) · Claude (thinking) · claude.ai connectors
```

- **No port open to the internet.** The tablet reaches the server only inside the Tailscale
  network.
- **Secrets are not in the repo:** the OpenAI key and the tablet token live in one file on the
  server, readable only by the user Pino runs as.
- **The database is a SQLite file.** Everything goes through `server/pino/store.py`: to move to
  Postgres (Supabase or other) you rewrite that file and nothing else.
- **Cost:** whatever the server costs you (ours is a VPS already used for other jobs); OpenAI a few
  cents a day; Claude is part of the subscription.

## What it can do (v3)

- You call it by name, «Pino», also with a greeting in front
  («ehi», «hey», «ciao»). The tablet recognizes the name by itself: until it hears it, nothing goes
  to the server, and if the tablet gets it wrong the server checks again on the transcript.
- One circle shows the state (off, waiting for the name, listening, thinking, speaking, ringing) and
  is the only button. A short note when it hears you, a soft sound while it thinks.
- A microphone switch (chip in the app, notification, quick settings tile), like the one on Alexa.
- Italian and English. Holding the side key opens Pino already listening, instead of Gemini.
- Short spoken answers, details on cards: one card per topic, swiped left and right, updated as
  the conversation goes on (a recipe step by step, tomorrow's events, the shopping list).
- Alarms on the tablet's Clock app, timers and reminders rung by Pino, household lists.
- It remembers what lasts about you and your people, quietly; «cosa sai di me?» shows it on a card.
- «Stop», «basta», «grazie» end the conversation. Calling it while it speaks turns its voice down
  until the server knows whether someone really called.
- Before any outward action (messages, mail, events) it shows what it is about to do and waits for
  a «sì», a «no» or a «non chiedermelo più» (yes, no, don't ask me again).
- Every question is written in a journal with its timings and tools (`remoto.sh registro`).

## 1. The server

On the server (Ubuntu, reachable over Tailscale), as the user Pino will run as:

```bash
loginctl enable-linger "$USER"                        # services keep running after you log out
curl -fsSL https://claude.ai/install.sh | bash        # Claude Code, then: claude → /login → /exit
curl -fsSL https://raw.githubusercontent.com/alessio-ragni/pino/main/deploy/vps/installa.sh | bash
```

The first run clones the repo in `~/pino`, prepares Python, and writes `~/.config/pino/env` with a
fresh token and an empty OpenAI key. Put the key in, run `bash ~/pino/deploy/vps/installa.sh` again,
and Pino starts as a user service that restarts by itself. Never set `ANTHROPIC_API_KEY`: the
installer refuses to start if it finds one, because Claude would bill per use.

Everyday commands (ours: `ssh alessio@vps-alessio`):

```bash
bash ~/pino/deploy/vps/installa.sh                             # update: git pull + restart
systemctl --user restart pino                                  # after changing ~/.config/pino/env
journalctl --user -u pino -n 50 --no-pager                     # log
cd ~/pino/server && .venv/bin/python -m pino.journal --db ~/.local/share/pino/pino.db --hours 6
```

`~/.config/pino/env` holds model, effort, language, `PINO_CONNECTORS` (the claude.ai connectors
Pino keeps; the others are switched off for it) and the rest of `.env.example`.

Test without a tablet, from a Mac on the same Tailscale network:

```bash
cd server && .venv/bin/python ../tools/prova_mac.py --url ws://vps-alessio:4390/ws --token <gettone> --scrivi
```

**On AWS instead:** `deploy/aws/` creates a dedicated machine (EC2, secrets in SSM, nightly copy to
S3) with `deploy/aws/crea.sh`, and `deploy/aws/remoto.sh` runs commands on it. It is how Pino ran
until November 2026, when that AWS account was closed; the recipe still works on any account.

### The site

`site/` is iampino.com, published by GitHub Pages at every push that touches it
(`.github/workflows/pages.yml`). Once: in the GitHub repository, **Settings → Pages → Source:
GitHub Actions**, custom domain `iampino.com`, enforce HTTPS. At the domain registrar: four `A`
records for `@` (185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153) and a `CNAME`
for `www` pointing at `alessio-ragni.github.io`.

## 2. The tablet (by hand, once)

Android does not let anyone control a tablet from outside until you allow it on the tablet itself.

1. **Settings → Security and privacy → Auto Blocker**: Off (it blocks commands over USB).
2. **Settings → About tablet → Software information**: tap **Build number** 7 times.
3. **Settings → Developer options → USB debugging**: On.
4. Plug in the cable (a data cable: with a charge-only cable the computer sees nothing). For «Use
   USB for», **Transferring files** is fine. At the **Allow USB debugging?** prompt, tick **Always
   allow from this computer** and tap **Allow**.

From here on, the rest is done from the computer.

## 3. The tablet (from the computer, with adb)

```bash
cd android
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew assembleDebug
adb install -r -g app/build/outputs/apk/debug/app-debug.apk

P=dev.pino.app
adb shell pm grant $P android.permission.RECORD_AUDIO
adb shell pm grant $P android.permission.POST_NOTIFICATIONS
adb shell dumpsys deviceidle whitelist +$P                 # no battery saving
adb shell cmd appops set $P RUN_ANY_IN_BACKGROUND allow
adb shell settings put global stay_on_while_plugged_in 7   # screen on while charging

# Pino as default assistant: holding the side key → Pino, and Gemini steps aside
adb shell cmd role add-role-holder android.app.role.ASSISTANT $P

# The «Pino» tile (microphone switch) in quick settings
adb shell cmd statusbar add-tile $P/.MicTile

# Tailscale always on, even after a restart
adb shell settings put secure always_on_vpn_app com.tailscale.ipn
```

Tailscale is installed from the Play Store
(`adb shell am start -a android.intent.action.VIEW -p com.android.vending -d market://details?id=com.tailscale.ipn`);
the owner signs in, on the tablet, with the same account as the server.

The server address and the token go into the app's **settings** (`pino:4390` and the token).
Alternatively, on a debug build, you can put them in the preferences file from adb with
`run-as dev.pino.app` (`shared_prefs/pino.xml`, keys `server` and `token`).

On first launch the app downloads the wake word model once (about 50 MB).

To see and control the tablet's screen from the computer: `brew install scrcpy && scrcpy`.

## 4. The test

- «Ciao Pino, che ore sono?» (what time is it?) with the screen on another app: it answers aloud.
- «Pino, fammi vedere la carbonara per due» (show me carbonara for two): the recipe appears on
  the screen.
- Side key held down: Pino opens already listening.
- «Pino, metti un evento di prova domani alle dieci» (add a test event tomorrow at ten): the
  confirmation card appears; a «no» creates nothing.

## What we learned the first time

- **The wake word** is tuned with `tools/prova_parola.py` on sentences generated with the Mac's
  Italian voices: every test call wakes it, the name said in the middle of a sentence almost never.
  «Pino» is in the model's vocabulary; the words it gets confused with (vino, fino, pinoli, Pinocchio, pieno…) have a box of their own, so they do not wake it.
- **Echo:** right after Pino has spoken, the microphone still hears its voice. The app throws
  away the audio from before and the first instant, otherwise its own sentence goes back to the
  server.
- **From a distance** the voice arrives faint: the server boosts it (up to 8 times) before
  transcribing it, and the app counts a lower level as speech too.
- **The token** travels in the websocket address: the server strips it from the logs.
- **False wake-ups:** on the first day the tablet's recognizer woke up with household chatter, and
  after each answer the follow-up without the name picked up more sentences. Since then the server
  checks the name again on the real transcript, and the follow-up is shorter and stricter.
