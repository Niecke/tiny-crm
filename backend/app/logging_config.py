from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Shared with uvicorn via `--log-config` so the reloader process logs JSON too.
LOG_CONFIG_PATH = Path(__file__).resolve().parent.parent / "log_config.json"


class JsonFormatter(logging.Formatter):
    """Renders each log record as a single-line JSON object with consistent base
    fields so output is machine-parseable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            # record.created is epoch seconds (float); int() -> whole seconds
            "timestamp": int(record.created),
            "timestamp_str": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "log_level": record.levelname,
            "logger": record.name,
            # getMessage() applies %-style args (e.g. logger.error("... %s", x))
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Routes all logging (app + uvicorn) through the JSON formatter on stdout.

    Applies the same config file uvicorn loads via `--log-config`, so logging is
    consistent whether the app is started by uvicorn or imported directly (scripts,
    tests). When uvicorn runs with `--log-config log_config.json`, this re-applies
    the identical config in the worker process (idempotent)."""
    with LOG_CONFIG_PATH.open(encoding="utf-8") as fh:
        logging.config.dictConfig(json.load(fh))
