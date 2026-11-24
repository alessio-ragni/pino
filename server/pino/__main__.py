"""`python -m pino`: starts the server."""

from __future__ import annotations

import logging
import re

import uvicorn

from pino.app import create_app
from pino.config import Settings


class HideToken(logging.Filter):
    """The token travels in the websocket address: it must never show in the logs."""

    PATTERN = re.compile(r"token=[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "token=" in message:
            record.msg = self.PATTERN.sub("token=***", message)
            record.args = None
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(HideToken())
    s = Settings.from_env()
    # log_config=None: uvicorn's logs go through ours, filter included.
    uvicorn.run(create_app(s), host=s.host, port=s.port, ws_max_size=16 * 1024 * 1024, log_config=None)


if __name__ == "__main__":
    main()
