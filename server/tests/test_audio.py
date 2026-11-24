from array import array

from pino.audio import MAX_GAIN, louder


def _pcm(values):
    return array("h", values).tobytes()


def test_quiet_voice_gets_louder_but_capped():
    quiet = _pcm([500, -500] * 1000)
    out = array("h", louder(quiet))
    assert max(out) == int(500 * MAX_GAIN)


def test_normal_voice_is_left_alone():
    normal = _pcm([20_000, -20_000] * 1000)
    assert louder(normal) == normal


def test_silence_and_empty_are_safe():
    assert louder(b"") == b""
    assert louder(_pcm([0] * 100)) == _pcm([0] * 100)
