"""Dry run of the wake word on the Mac, with the same rules as the app (Wake.kt + Ears.kt).

    python3 -m venv /tmp/vosk && /tmp/vosk/bin/pip install vosk
    # model: https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip (unzipped)
    say -v Alice -o test.wav --data-format=LEI16@16000 "Ciao Pino, che ore sono?"
    /tmp/vosk/bin/python tools/prova_parola.py <model-dir> test.wav[,other.wav] [settle_ms] [confidence]

Prints WAKE (with the milliseconds) or «-» for each file. If you change the word lists here, change
them in Wake.kt too.
"""

import json
import sys
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
NAMES = ["pino"]
GREET = ["ehi", "hey", "hei", "ei", "ciao", "hi"]
DECOYS = [
    "pina",
    "pinoli",
    "pinolo",
    "pinocchio",
    "pinot",
    "spino",
    "spina",
    "vino",
    "fino",
    "pieno",
    "piano",
]
MIN_CONF = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
SETTLE_MS = int(sys.argv[3]) if len(sys.argv) > 3 else 700


def verdict(words, final):
    """words: list of (word, conf). YES / NO / MAYBE"""
    i = 0
    while i < len(words) and words[i][0] in GREET:
        i += 1
    if i >= len(words) or i > 2:
        return "NO"
    w, c = words[i]
    if w not in NAMES or (final and c < MIN_CONF):
        return "NO"
    if i + 1 < len(words):
        return "NO" if words[i + 1][0] in DECOYS else "YES"
    return "YES" if final else "MAYBE"


m = Model(sys.argv[1])
gram = json.dumps(NAMES + GREET + DECOYS + ["[unk]"])
for path in sys.argv[2].split(","):
    r = KaldiRecognizer(m, 16000, gram)
    r.SetWords(True)
    wv = wave.open(path)  # noqa: SIM115 — test script, closed on exit
    hit = None
    maybe = 0
    t = 0
    last = ""
    while True:
        d = wv.readframes(1600)
        if not d:
            break
        t += 100
        if r.AcceptWaveform(d):
            o = json.loads(r.Result())
            v = verdict([(x["word"], x["conf"]) for x in o.get("result", [])], True)
            last = o.get("text", "")
            maybe = 0
        else:
            p = json.loads(r.PartialResult())["partial"]
            v = verdict([(x, 1.0) for x in p.split()], False)
            last = p
            if v == "MAYBE":
                maybe += 100
                if maybe >= SETTLE_MS:
                    v = "YES"
            else:
                maybe = 0
        if v == "YES":
            hit = t
            break
    if hit is None:
        o = json.loads(r.FinalResult())
        if verdict([(x["word"], x["conf"]) for x in o.get("result", [])], True) == "YES":
            hit = t
        last = o.get("text", last)
    print((f"WAKE    {hit:5d} " if hit else "-             ") + path.rsplit("/", 1)[1] + "   " + last)
