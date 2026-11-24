"""Were they really talking to Pino? The second check, on the real transcript.

The tablet wakes up with a small recognizer that now and then "hears" the name in
the middle of any conversation. Here the transcribed text is checked: if it does
not start with the name (after at most two greetings), nobody was calling him and
the recording is thrown away.

Right after an answer the tablet listens a few seconds without the name: there the
only possible check is that it is not the echo of his own voice.

`stopped()` recognizes "stop", "basta", "grazie" and the like: the conversation is over.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

NAMES = ("pino",)

# How the transcriber sometimes spells it: still the name.
SPELLINGS = frozenset({"pinu", "pinno", "pyno", "peeno", "pineau"})

# Greetings and fillers said before the name: «ehi Pino», «senti Pino», «no, Pino».
GREETINGS = frozenset(
    {
        "ehi",
        "hey",
        "hei",
        "ei",
        "ehy",
        "e",
        "eh",
        "oh",
        "ciao",
        "hi",
        "hello",
        "ok",
        "okay",
        "no",
        "dai",
        "senti",
        "scusa",
        "allora",
        "ascolta",
    }
)

# Real words that look like the name: they are not a call.
NOT_NAMES = frozenset({"pina", "pini", "pine", "pinoli", "pinolo", "pinocchio", "pinot", "spino", "vino", "fino", "pieno"})

MAX_GREETINGS = 2


def words(text: str) -> list[str]:
    """Lowercase words, without accents or punctuation."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.findall(r"[a-z]+", plain)


def is_name(word: str) -> bool:
    """«Pino» is short and close to many words (vino, fino, pina): only the name and its known misspellings count."""
    if word in NOT_NAMES:
        return False
    return word in NAMES or word in SPELLINGS


def called(text: str) -> bool:
    """True if the sentence starts with the name, after at most two greetings («ehi Pino», «ciao Pino»)."""
    ws = words(text)
    i = 0
    while i < len(ws) and i < MAX_GREETINGS and ws[i] in GREETINGS and not is_name(ws[i]):
        i += 1
    return i < len(ws) and is_name(ws[i])


def echo(text: str, said: str) -> bool:
    """True if `text` is nearly what Pino just said (the microphone heard him)."""
    heard = " ".join(words(text))
    spoken = " ".join(words(said))
    if not heard or not spoken:
        return False
    if len(heard) >= 8 and heard in spoken:
        return True
    return SequenceMatcher(None, heard, spoken).ratio() >= 0.8


SILENT = "…"


def silent(answer: str) -> bool:
    """The agreed answer for "they were not talking to me": only dots."""
    return bool(answer.strip()) and not answer.strip().strip(".…").strip()


# «Basta», «stop», «grazie»: the conversation is over, back to waiting for the name.
_STOP_STRONG = frozenset(
    {"stop", "basta", "zitto", "zitta", "fermati", "ferma", "silenzio", "grazie", "thanks", "enough", "quiet", "finito"}
)
_STOP_SOFT = frozenset(
    {
        "ok",
        "okay",
        "va",
        "bene",
        "cosi",
        "per",
        "ora",
        "adesso",
        "ho",
        "e",
        "tutto",
        "mille",
        "thank",
        "you",
        "be",
        "shut",
        "up",
        "that",
        "s",
        "all",
        "lascia",
        "stare",
        "niente",
        "altro",
        "a",
        "posto",
        "apposto",
        "sono",
        "sto",
        "never",
        "mind",
        "please",
    }
)
_STOP_PHRASES = ("lascia stare", "never mind", "niente niente")


def stopped(text: str) -> bool:
    """True if the whole sentence only says "stop" ("basta", "grazie, ok", "Pino stop")."""
    ws = [w for w in words(text) if not is_name(w)]
    if not ws or len(ws) > 6:
        return False
    joined = " ".join(ws)
    if not set(ws) <= _STOP_STRONG | _STOP_SOFT | GREETINGS:
        return False
    return bool(set(ws) & _STOP_STRONG) or any(p in joined for p in _STOP_PHRASES)
