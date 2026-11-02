from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        content = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, key):
                content[key] = getattr(record, key)
        return json.dumps(content, ensure_ascii=False)


def configure_logging(path: str, max_bytes: int, backup_count: int) -> None:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("abel")
    logger.setLevel(logging.INFO)
    if not any(
        isinstance(item, RotatingFileHandler)
        and Path(item.baseFilename).resolve() == log_path.resolve()
        for item in logger.handlers
    ):
        logger.addHandler(handler)
    logger.propagate = False
