"""The second check: does the sentence start with the name? Is it the echo of his voice?"""

import pytest

from pino.addressed import called, echo, silent, stopped


@pytest.mark.parametrize(
    "text",
    [
        "Pino, che ore sono?",
        "Ehi Pino, mi senti?",
        "Ciao Pino!",
        "Pino, metti un timer",
        "ok Pino",
        "Hey Pino, what time is it?",
        "Pinò, dimmi",
        "No, Pino, non così",
        "Senti Pino, una cosa",
        "Hi Pino, tell me a joke",
    ],
)
def test_called(text):
    assert called(text)


@pytest.mark.parametrize(
    "text",
    [
        "Ho visto Pino ieri al mercato",
        "La partita alle nove e mezza",
        "Pina, vieni a tavola",
        "Fino a domani",
        "Vino rosso, grazie",
        "Pinoli per il pesto",
        "Pinocchio ha il naso lungo",
        "Ehi ehi ehi Pino",  # too many greetings first
        "",
        "Hello",
    ],
)
def test_not_called(text):
    assert not called(text)


def test_echo():
    said = "Ecco la carbonara, sono cinque passaggi. Buon appetito!"
    assert echo("sono cinque passaggi", said)
    assert echo("Ecco la carbonara, sono cinque passaggi.", said)
    assert not echo("e per quattro persone?", said)
    assert not echo("qualcosa", "")


def test_silence():
    assert silent("…") and silent("...") and silent(" … ")
    assert not silent("") and not silent("… ah, ok")


@pytest.mark.parametrize(
    "text", ["Pino, stop", "basta", "grazie", "ok grazie mille", "Pino basta così", "lascia stare"]
)
def test_stopped(text):
    assert stopped(text)


@pytest.mark.parametrize("text", ["basta pasta per stasera", "metti un timer", "grazie, mi dici che ore sono?", "ok"])
def test_not_stopped(text):
    assert not stopped(text)
