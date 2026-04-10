from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level)
    root_logger.setLevel(level)


def structured_event(event: str, **fields: Any) -> str:
    payload = {"event": event, **fields}
    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
