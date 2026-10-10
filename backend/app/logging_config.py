from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Shared with uvicorn via `--log-config` so the reloader process logs JSON too.
LOG_CONFIG_PATH = Path(__file__).resolve().parent.parent / "log_config.json"

ACCESS_LOGGER = "uvicorn.access"


def _access_fields(record: logging.LogRecord) -> dict[str, Any] | None:
    """Splits a uvicorn access record into one field per value.

    uvicorn logs every request as '%s - "%s %s HTTP/%s" %d' and passes the client
    address, method, path with query string, HTTP version and status as args, so
    the values are read from there instead of parsed back out of the message.
    Any other shape returns None and the record is rendered flat: a uvicorn
    release that changes the call should cost the fields, not the log line.
    """
    args = record.args
    if record.name != ACCESS_LOGGER or not isinstance(args, tuple) or len(args) != 5:
        return None
    client_addr, method, full_path, http_version, status = args
    if not isinstance(status, int):
        return None

    fields: dict[str, Any] = {}
    # "host:port". An IPv6 host has colons of its own, so split on the last one.
    # Empty when uvicorn has no peer address to report (a unix socket). The host
    # is the real client behind a trusted proxy, see _client_ip in ratelimit.py.
    host, _, port = str(client_addr).rpartition(":")
    if host and port.isdigit():
        fields["source_ip"] = host
        # X-Forwarded-For names a host and no port, so for a proxied request
        # uvicorn reports port 0. That is every request in the cluster.
        if int(port):
            fields["source_port"] = int(port)
    path, _, query = str(full_path).partition("?")
    fields["http_method"] = str(method)
    fields["http_path"] = path
    if query:
        fields["http_query"] = query
    fields["http_version"] = str(http_version)
    fields["http_status"] = status
    return fields


class JsonFormatter(logging.Formatter):
    """Renders each log record as a single-line JSON object with consistent base
    fields so output is machine-parseable. Access records additionally carry the
    request as separate fields, see _access_fields(); records about a queued job
    carry the job's."""

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
        access = _access_fields(record)
        if access is not None:
            # The address and version now have fields of their own; what stays is
            # the part worth reading in `kubectl logs`.
            payload["message"] = (
                f"{access['http_method']} {access['http_path']} {access['http_status']}"
            )
            payload.update(access)
        # procrastinate attaches the job to every record about one, and spells
        # it out in the message with its arguments: `task[12](user_id='…')`.
        # Arguments stay out of the log — today's are ids, a later task's may
        # not be — and the job is identified by fields that can be filtered on.
        job = getattr(record, "job", None)
        if isinstance(job, dict):
            name = f"{job.get('task_name')}[{job.get('id')}]"
            payload["message"] = payload["message"].replace(str(job.get("call_string")), name)
            payload["job_id"] = job.get("id")
            payload["task"] = job.get("task_name")
            payload["queue"] = job.get("queue")
            # How many runs came before this one; 0 on the first.
            payload["attempts"] = job.get("attempts")
        # What happened, as a stable word: start_job, job_success, job_error_retry, …
        action = getattr(record, "action", None)
        if isinstance(action, str):
            payload["action"] = action
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
