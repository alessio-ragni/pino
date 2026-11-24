"""From text arriving in pieces to sentences to say.

Claude writes the answer one piece at a time. To start speaking as soon as
possible, everything before the last sentence end is said, and the rest waits
for the next piece. By sentence and not by word: a sentence is the shortest
piece that still has its own intonation.

Taken from the older home assistant Franco, where it already proved itself.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

MAX_CHARS = 240
EAGER_CHARS = 30

END = re.compile(r"(?<=[.!?…;:])\s+|\n+")
_PAUSE = re.compile(r"(?<=[,;:—–])\s+")
_SPACES = re.compile(r"[^\S\n]+")
_AROUND_NEWLINE = re.compile(r"\s*\n\s*")
_LOOSE_PUNCT = re.compile(r"[^\S\n]+(?=[,.;:!?…)\]])")
# Markdown a voice would read aloud: asterisks, hashes, list dashes.
_MARKDOWN = re.compile(r"(\*\*|__|`+|^#+\s*|^\s*[-*•]\s+)", re.MULTILINE)
_DROP = {"Cc", "Cf", "Cs", "Co", "Cn", "So", "Sk"}


def clean(text: str) -> str:
    text = _MARKDOWN.sub("", text)
    kept = []
    for char in unicodedata.normalize("NFKC", text):
        if char == "\n":
            kept.append(char)
        elif unicodedata.category(char) in _DROP:
            kept.append(" ")
        else:
            kept.append(char)
    collapsed = _LOOSE_PUNCT.sub("", _SPACES.sub(" ", "".join(kept)))
    return _AROUND_NEWLINE.sub("\n", collapsed).strip()


def sentences(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    pieces: list[str] = []
    for chunk in END.split(clean(text)):
        stripped = chunk.strip()
        if stripped:
            pieces.extend(shorten(stripped, max_chars))
    return pieces


def shorten(piece: str, limit: int) -> list[str]:
    if len(piece) <= limit:
        return [piece]
    out: list[str] = []
    current = ""
    for bit in _fragments(piece, limit):
        if not current:
            current = bit
        elif len(current) + 1 + len(bit) <= limit:
            current = f"{current} {bit}"
        else:
            out.append(current)
            current = bit
    if current:
        out.append(current)
    return out


def _fragments(piece: str, limit: int) -> Iterator[str]:
    for part in _PAUSE.split(piece):
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit)
            head, part = (part[:cut], part[cut:]) if cut > 0 else (part[:limit], part[limit:])
            if head.strip():
                yield head.strip()
            part = part.strip()
        if part:
            yield part


class Splitter:
    """Takes the pieces as they come and returns the sentences ready to say."""

    def __init__(self, max_chars: int = MAX_CHARS, eager_first: bool = False) -> None:
        self.max_chars = max_chars
        self._buffer = ""
        # The very first piece may stop at a comma: the voice starts a moment sooner.
        self._eager = eager_first

    def feed(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buffer += delta
        out: list[str] = []
        last = None
        for match in END.finditer(self._buffer):
            last = match
        if last is None and self._eager and len(self._buffer) >= EAGER_CHARS:
            for match in _PAUSE.finditer(self._buffer):
                if match.start() >= EAGER_CHARS:
                    last = match
                    break
        if last is not None:
            ready, self._buffer = self._buffer[: last.end()], self._buffer[last.end() :]
            out.extend(sentences(ready, self.max_chars))
            self._eager = False
        while len(self._buffer) > self.max_chars:
            head, self._buffer = self._buffer[: self.max_chars], self._buffer[self.max_chars :]
            out.extend(sentences(head, self.max_chars))
        return out

    def flush(self) -> list[str]:
        rest, self._buffer = self._buffer, ""
        return sentences(rest, self.max_chars)
