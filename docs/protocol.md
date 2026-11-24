# The protocol between tablet and server

One websocket: `ws://<server>:4390/ws?token=<PINO_TOKEN>&device=<name>`.
Wrong token → the server closes with code 4401.

Text messages are JSON with a `type` field. Audio travels in binary frames:
**16-bit PCM, mono, little-endian**. From the tablet at **16 kHz**; from the server at the `rate`
declared in the `say` that comes before it (24 kHz with OpenAI and ElevenLabs).

How the whole thing behaves, without code, is in [`how-it-works.md`](how-it-works.md).

## From the tablet to the server

| type | fields | what it means |
|---|---|---|
| `start` | `rate` (default 16000), `why` | I am about to send voice. If Pino was speaking, it goes quiet (except with `barge`). `why` says why the tablet is listening: `name` (it heard the name; also the value when missing), `follow` (right after an answer, without the name), `button` (the circle), `key` (side key), `barge` (it heard the name while Pino was speaking: the voice is only turned down until the server decides) |
| *(binary)* | PCM | pieces of voice, between `start` and `end` |
| `end` | `rate` | I have finished speaking: transcribe and answer |
| `text` | `text` | a written sentence, instead of voice |
| `action` | `name`, `surfaceId`, `sourceComponentId`, `context` | a tap on an A2UI component (the A2UI `action` message) |
| `stop` | — | quiet: stops both voice and thinking; an open confirmation counts as no |
| `closed` | `surfaceId` | the person closed that card (its ✕) |
| `front` | `surfaceId` | the card now in front: «this» in a question means this one |
| `render_error` | `surfaceId`, `message` | the renderer could not draw something; it goes to the journal and to Claude |
| `device_result` | `id`, `ok` | the answer to a `device` request |
| `ring_stop` | `id` | the person stopped a ringing timer or reminder |

The actions `confirm_yes`, `confirm_always` and `confirm_no` answer the confirmation card. The
others reach Claude as a sentence.

## From the server to the tablet

| type | fields | what it means |
|---|---|---|
| `ready` | `voice`, `ears`, `rate`, `a2ui` | connected. `voice`/`ears` false = server without voice or transcription |
| `heard` | `text`, `recording` | what it understood |
| `thinking` | — | it is thinking (show something) |
| `say` | `text`, `rate` | it is about to say this sentence; the binary audio frames follow |
| `say_end` | — | end of the audio for that sentence |
| `a2ui` | `messages` | A2UI messages to pass to the renderer, in order |
| `card` | `id`, `title`, `thread` | a card (a topic) was created or changed: its title and its short thread of `{q, a}`. Its body is the A2UI surface with the same id, if there is one |
| `card_closed` | `id` | that card is gone |
| `cards_reset` | — | sent right after `ready`: forget your cards, the server sends them all again |
| `focus` | `id` | bring that card in front |
| `ring` | `id`, `kind`, `label` | a timer, reminder or Pino-rung alarm is due: ring until the person stops it |
| `device` | `id`, `action`, … | do something on the device and answer with `device_result`. `set_alarm` (`hour`, `minute`, `days` ISO 1-7, `label`) puts an alarm on the Clock app; `show_alarms` opens its list |
| `done` | `ms` | end of the turn, after the last sentence: listening can start again |
| `ignored` | `reason` | no answer is coming: go back to waiting for the name, with no follow-up. Reasons below; `stop` means the person said «stop», «basta» or «grazie» |
| `error` | `text` | something is wrong on the server side |

## Cards

The screen is a row of cards, one per topic. A card has an id (`carbonara`, `list-spesa`,
`agenda`, `chat`), a title, an optional A2UI surface with the same id for its body, and a thread
of the last questions and answers on it. Cards are kept on the server (`cards` table) and survive
restarts: after every `ready` the server sends `cards_reset` and then every open card again.
Claude names the card each answer belongs to; the server sends `card` with the new thread and
`focus`, and the tablet moves there. `chat` has no surface: it holds what has nothing to show.

## Confirmations

When Claude wants to use a tool that is not read-only, the server sends an A2UI surface with
`surfaceId: "conferma"` and says «Lo faccio?» (shall I do it?). The answer can come by voice («sì»,
«no», «non chiedermelo più»: yes, no, don't ask me again) or with the buttons (`confirm_*`). After
the answer the surface is removed with `deleteSurface`. No answer within
`PINO_CONFIRM_TIMEOUT_S` counts as no.

## Not meant for Pino

The tablet wakes up with its own recognizer, which can be wrong. The server checks again on the
real transcript:

- `why: name` and the sentence does not start with the name (at most after two greetings such as
  «ehi», «ciao», «senti»): `ignored` with `reason: "non chiamato"` (not called);
- `why: follow` and the sentence is the echo of what Pino has just said: `ignored`, `"eco"`
  (echo);
- `why: barge` and the sentence does not start with the name, or is his own echo: `ignored`,
  `"eco"`. The tablet turns the voice back up and Pino carries on;
- `why: follow` and Claude judges that people were talking to each other (it answers only «…»):
  `ignored`, `"non per me"` (not for me).

In all three cases Claude does not answer aloud and all that is left of the recording is the row
with date, length and reason: audio and text are deleted at once. With `button` and `key` nothing
is checked: the intent is explicit.
