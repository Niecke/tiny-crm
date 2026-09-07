#!/usr/bin/env python3
"""Send today's briefing to Slack. Meant to run from a weekday-morning cron.

Usage:
    python scripts/send_briefing.py            # post to SLACK_WEBHOOK_URL
    python scripts/send_briefing.py --dry-run  # print the message, send nothing

Reads DATABASE_URL, SLACK_WEBHOOK_URL, BRIEFING_TIMEZONE and APP_URL from the
environment (or backend/.env). Exits non-zero when nothing could be sent, so
a CronJob run that fails shows up as failed rather than as a quiet morning.

Weekday-only is the schedule's job, not this script's: run by hand on a
Saturday, it sends Saturday's briefing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Run directly (`python scripts/send_briefing.py`) and Python puts this script's
# directory on sys.path, not the backend root -- so `app` wouldn't import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.briefing import SlackDeliveryError, post_to_slack, send_briefings  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import _session_factory  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402

logger = logging.getLogger("send_briefing")


def _print_instead(webhook_url: str, payload: dict[str, Any]) -> None:
    """The dry-run poster: the notification line, then the blocks as JSON."""
    print(payload["text"])
    print(json.dumps(payload["blocks"], indent=2, ensure_ascii=False))
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send today's briefing to Slack.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be posted instead of posting it",
    )
    args = parser.parse_args(argv)

    try:
        tz = ZoneInfo(settings.briefing_timezone)
    except ZoneInfoNotFoundError:
        print(
            f"BRIEFING_TIMEZONE={settings.briefing_timezone!r} is not a known zone.",
            file=sys.stderr,
        )
        return 2

    # An empty string is what a templated env var leaves behind when the value
    # is missing; treat it the same as unset.
    webhook_url = settings.slack_webhook_url or ""
    if not args.dry_run and not webhook_url:
        print(
            "SLACK_WEBHOOK_URL is not set: there is nowhere to send the briefing.",
            file=sys.stderr,
        )
        return 2

    configure_logging()
    try:
        briefings = asyncio.run(
            send_briefings(
                _session_factory,
                webhook_url=webhook_url,
                tz=tz,
                app_url=settings.app_url,
                post=_print_instead if args.dry_run else post_to_slack,
            )
        )
    except SlackDeliveryError as exc:
        logger.error("Briefing not delivered: %s", exc)
        return 1

    logger.info("%d briefing(s) %s", len(briefings), "rendered" if args.dry_run else "sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
