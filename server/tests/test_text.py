from pino.text import Splitter, sentences


def test_in_pieces_sounds_like_all_at_once():
    whole = "Ciao. Oggi piove a Milano! Domani? Sole, forse; vedremo: dipende."
    s = Splitter()
    out = []
    for i in range(0, len(whole), 3):
        out += s.feed(whole[i : i + 3])
    out += s.flush()
    assert out == sentences(whole)


def test_no_markdown_spoken():
    assert sentences("**Pronto**: ecco.\n- uno\n- due") == ["Pronto:", "ecco.", "uno", "due"]


def test_a_sentence_without_an_end_is_not_lost():
    s = Splitter(max_chars=20)
    assert s.feed("parola " * 10)


def test_the_first_piece_may_stop_at_a_comma():
    s = Splitter(eager_first=True)
    assert s.feed("Domani hai tre impegni in agenda, il primo") == ["Domani hai tre impegni in agenda,"]
    assert s.feed(" alle sette, poi") == []  # only the first piece is eager
    assert s.feed(" il resto. ") == ["il primo alle sette, poi il resto."]
