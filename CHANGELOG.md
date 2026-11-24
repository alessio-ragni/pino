# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version numbers follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Frankino is now Pino.** One personal assistant, one memory, many bodies: today the tablet,
  tomorrow WhatsApp and a small holographic screen. You call it «Pino», «ehi Pino», «ciao Pino»,
  «hey Pino»; words that sound like it (vino, fino, pinoli, Pinocchio, pieno) do not wake it. The
  old names no longer answer.
- **A new face**: the app icon is Pino, a bright green drop with big eyes.
- **The app has a new identity on Android**: the old Frankino app has to be uninstalled and the new
  one installed, then given the server address and the token again.
- **Kinder words**: Pino's character is warmer and calmer.

### Added

- **Pino remembers.** It quietly writes down what lasts about you and your people (tastes, habits,
  family, places) and uses it without being asked: a carbonara suggested the way someone likes it.
  «Ricordati che…» works too. «Cosa sai di me?» opens a card with everything it knows; say what is
  wrong or what to forget and it corrects it. Nothing is ever deleted: a forgotten memory ends with
  the date and the reason.
- **iampino.com**, Pino's site in English, Italian and Spanish: who Pino is, the story from Franco
  to Franchino to Pino, all its bodies, and how to plant your own (install it on your server).
- **Pino installs on any always-on Linux server** with one command (`deploy/vps/installa.sh`),
  and now runs on a small VPS. The AWS machine Frankino lived on is gone with its account: Pino
  starts with an empty agenda, empty lists and no cards.
- **The site shows Pino's faces**: eight expressions, and the first try with a little tree on its
  head.

- **A gallery of every kind of card the tablet can draw**: text styles, icons and buttons, a recipe
  with a photo, tabs, a row that scrolls sideways, a form with a text box, choices, date and slider,
  and a pop-up window. It runs on the tablet alone, to see what the screen can do before asking
  for it.
- **«Basta», «stop», «zitto» on their own stop Pino at once** while it speaks, thinks or rings,
  without saying its name and without any answer.

### Changed

- **The conversation stays open longer.** After an answer it keeps listening without the name for
  20 seconds instead of 5, and after something that was not for it, it keeps listening instead of
  closing. It also waits for a longer pause (1.2 seconds) before deciding you have finished.
- **The thinking sound is rarer and softer**: one note every few seconds instead of two notes every
  second.
- **Cards follow the tablet's colours and use larger text**, easier to read from across the room.

### Fixed

- **It no longer gets stuck on «thinking».** When the server decided a sentence was not for
  Pino, the tablet stayed on the thinking circle for good. And if no answer comes within 45
  seconds, it now gives up and goes back to listening.
- **A question asked right when the conversation was starting afresh** waits for it instead of
  failing.
- **Pictures from sites that refuse anonymous requests now load**, Wikimedia for one.

## [2.0.0] - 2026-11-15

Frankino now shows what it is doing and has one button, keeps each topic on its own card that
follows the conversation, and can set alarms, timers, reminders and lists. It answers sooner and
shorter, and every question leaves a record of what it did and how long it took. The whole project
is now written in English. Tried on the real tablet with written questions; spoken use is still to
be tried at home.

### Added

- **One circle that shows the state and is the only button.** Off (red ring), waiting for its name
  (it breathes), listening (blue, it moves with your voice), thinking (four dots turning), speaking
  (moving bars), ringing. Tapping it does the obvious thing: listen without the name, finish,
  stop. The «Parla» and «Zitto» buttons are gone.
- **Sounds that say it heard you.** A short note when it hears its name and a soft two-note pulse
  while it thinks, from the moment you stop talking. If nothing has been said after three seconds
  it says «un attimo».
- **Cards, one per topic, swiped left and right.** A recipe, tomorrow's events, the shopping list,
  the alarms: each is a card that updates in place as you talk. «Prossimo passo» moves the recipe
  on, with the step you are on large at the top; «quanto pecorino?» is answered on the same card.
  Under each card are the last answers on that topic, with your question small above each. Close a
  card with its ✕. Cards come back after a restart.
- **Recipes by phase and events by day.** Recipes come with the ingredients in two columns and the
  steps grouped in phases; the calendar comes as one row per event with time and place.
- **Alarms, timers, reminders and lists.** Alarms go on the tablet's Clock app, so they ring even
  if Frankino is off (Android lets no app delete them: to cancel one, Frankino opens the Clock app).
  Timers and reminders ring from Frankino with a bell and his voice, and wait for a conversation to
  end. Household lists, the shopping list first.
- **«Stop», «basta», «grazie»** end the conversation and send Frankino back to waiting for its name.
- **A journal of everything it does.** Every question is written down with why it started, how long
  each step took, which tools it used, whether they failed and whether it asked for confirmation;
  so are discarded recordings, cards that failed to draw and things it had no tool for. Read it with
  the `registro` command, or ask Claude about it.
- **Releases on GitHub**, with the Android app attached, and automatic checks on every change.

### Changed

- **Shorter answers aloud, the details on the card.** It says the headline and draws the rest.
- **Only the household connectors**: WhatsApp, Gmail, Google Calendar and Google Drive, plus web
  search. Every connector made every question heavier; with the others switched off, and the
  tools of these four that a voice never needs, a question carries about 40 thousand tokens of
  instructions instead of nearly 290 thousand. Measured on the server: a simple question gets its
  first word in about 1.2 seconds and its first sound in about 2.
- **No extended thinking**, and the conversation with Claude starts afresh after ten quiet
  minutes, so it does not grow forever.
- **It stops listening sooner**: a pause of 0.8 seconds, instead of 1.3, means you are done.
- **The voice starts sooner**: the next sentence is prepared while the current one plays, and the
  first one can start at a comma.
- **The app's words are in English, with an Italian translation** that the tablet uses when it is
  set to Italian. What Frankino says follows the language you speak.
- **Everything in the repository is now in English**: code, documentation and this changelog.

### Fixed

- **It no longer stops itself.** It used to hear its own name in its answers and go quiet. Now it
  never says its own name, the tablet's echo canceller is on when the tablet has one, and when it
  thinks it heard its name while speaking it only turns the voice down until the server has read
  the sentence: its own voice, and it carries on.
- **New cards are no longer lost at the bottom of the screen**, and the old carbonara no longer
  stays on top: the screen goes to the card being talked about.
- **A card that cannot be drawn is no longer silent.** The server checks every card before sending
  it, and a drawing error goes back to Claude and into the journal.
- **An unanswered confirmation no longer stays on the screen**, and stopping Frankino counts as a
  «no».
- **A sentence said twice is said once.** The small model sometimes repeated itself before and
  after drawing a card.

## [1.0.0] - 2026-11-14

Frankino no longer wakes up by itself when people talk around the house, and it can be switched
off like Alexa. It answers sooner, understands English too, and there is a plain explanation of
how it works.

### Added

- **A microphone switch, like the one on Alexa.** A big button in the app, an action in the
  notification and a «Frankino» tile in quick settings. Off means the microphone is really closed;
  it stays off even after a restart.
- **Italian and English.** Transcription recognizes the language by itself, and Frankino answers in
  the language you speak to it.
- **How it works, explained without code**: [`docs/how-it-works.md`](docs/how-it-works.md).

### Changed

- **The follow-up without the name is more careful.** After an answer it listens for less time and
  only to a real voice. It throws away its own voice, and if it understands that you are talking to
  each other it does not answer.
- **It thinks with Claude Haiku**, with little reasoning: it answers sooner and uses much less of
  the subscription. Going back to Sonnet or Opus takes one line.
- **Conversations with Claude are not saved to disk** on the server.

### Fixed

- **Never without the name.** Every now and then the tablet thought it heard «Franco» in the middle
  of a conversation. Now the server checks again on the transcribed sentence: if it does not start
  with the name, it is thrown away at once, audio and text, and Frankino stays quiet.
- **Silence no longer sounds like a call.** The names are no longer suggested to the transcription:
  when it heard nothing, the transcriber repeated them and it looked as if someone had called
  Frankino.

## [0.2.0] - 2026-11-14

The tablet has arrived and Frankino answers aloud from it. The brain is no longer on the Mac: it
lives on a server of its own, always on, inside a private network.

### Added

- **The server is on AWS, always on.** A small machine (about $15 a month) that can only be reached
  from your private Tailscale network: no port open to the internet. Every night it copies the
  database to a separate archive.
- **You can also call it with a greeting.** «Ehi Franko», «ciao Franchino», «hey Franco», «hi
  Franco», as well as the name on its own.
- **The side key opens Frankino, not Gemini.** Holding it down opens Frankino already listening;
  «Hey Google» is no longer the assistant either.
- **A step-by-step guide** to redo everything from scratch: [`docs/deployment.md`](docs/deployment.md).

### Changed

- **Secrets are not stored anywhere on disk.** The voice key and the tablet token are read at every
  start from a protected AWS store.
- **It hears you better from a distance.** A faraway voice is boosted before it is transcribed, and
  the app recognizes it as speech even when it arrives faint.

### Fixed

- **The name said in the middle of a sentence no longer wakes it** («ho visto Franco», I saw Franco).
- **It no longer answers itself.** Right after speaking, the tablet still heard its own voice and
  sent it back: that audio is now thrown away.
- **The token no longer ends up in the server logs.**

## [0.1.0] - 2026-11-13

A new project, from scratch, for a voice companion with a screen that you can carry around. On
12 November came the server: it understands, thinks with Claude Code and all the connectors,
answers aloud and draws on the screen. On 13 November Frankino went on GitHub as an open source
project, with the first version of the Android app, ready to install on the tablet as soon as it
arrives.

### Added

- **It thinks with Claude Code and your connectors.** It uses your subscription login, so it sees
  the same services you have already linked (messages, mail, calendar, documents) without setting
  them up a second time.
- **It shows things on the screen.** When an answer is easier to understand by looking at it (a
  recipe, a list) it draws it with A2UI, and says only the gist aloud.
- **It starts speaking at the first sentence.** It does not wait for the end of the answer: each
  complete sentence goes out right away.
- **Voice and transcription can be changed with a setting.** It starts with OpenAI; ElevenLabs is
  already there.
- **It asks before doing anything outward.** It shows what it is about to do and waits for a «sì»,
  a «no» or a «non chiedermelo più» (yes, no, don't ask me again), by voice or with a button. When
  in doubt it asks: only what just reads goes through without questions.
- **Audio is kept for 30 days, text forever.** Long dictations are not lost, and after a month the
  audio deletes itself.
- **A test from the Mac.** While waiting for the tablet, a script acts as the tablet: you speak into
  the Mac's microphone and hear the answer.
- **It keeps listening even with another app on the screen.** A persistent notification shows it
  is there; the microphone stays open as long as the app is running.
- **It wakes up with its name.** It recognizes «Franco», «Franchino», «Frankino» right on the
  tablet, without sending anything to anyone until it hears it.
- **No need to call it again after an answer.** For a few seconds it listens even without the name,
  and when it asks «Lo faccio?» (shall I do it?) it waits for your «sì» or «no».
- **If you talk over it, it goes quiet.** Just call it by name while it is speaking, or tap the
  stop button.
- **The screen shows what Claude sends**: recipes, lists and the confirmation card with its buttons,
  drawn with Google's official A2UI component.
- **It is set up from the tablet.** The server address and the token are entered in the app's
  settings, not written in the code.

[1.0.0]: https://github.com/alessio-ragni/frankino/releases/tag/v1.0.0
[2.0.0]: https://github.com/alessio-ragni/frankino/releases/tag/v2.0.0
