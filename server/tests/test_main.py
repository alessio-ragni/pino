import logging

from pino.__main__ import HideToken


def test_token_is_hidden_in_logs():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("100.1.2.3:1", "/ws?token=segreto123&device=tablet"),
        None,
    )
    assert HideToken().filter(record)
    assert "segreto123" not in record.getMessage()
    assert "token=***&device=tablet" in record.getMessage()
