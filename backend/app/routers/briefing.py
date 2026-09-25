"""GET /briefing — the morning briefing as data.

The same `gather_briefing` the 07:00 Slack message is built from, for the
signed-in user and for today in BRIEFING_TIMEZONE. The dashboard renders this
instead of assembling "today" from the list endpoints, which have no due-date
or confirmation filters and would need their own idea of where today starts.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.briefing import Briefing, DayWindow, gather_briefing
from app.config import settings
from app.db import get_session
from app.models import Capture, Interaction, Task, Watch
from app.schemas.briefing import (
    BriefingCapture,
    BriefingInteraction,
    BriefingRead,
    BriefingTask,
    BriefingWatch,
)

router = APIRouter(prefix="/briefing", tags=["briefing"])


def current_time() -> datetime:
    """The clock, as a dependency so a test can pin it."""
    return datetime.now(UTC)


def _task(task: Task, window: DayWindow) -> BriefingTask:
    return BriefingTask(
        id=task.id,
        title=task.title,
        due_date=task.due_date,
        priority=task.priority,
        contact_name=task.contact_name,
        deal_title=task.deal_title,
        repeats=task.recurrence_rule is not None,
        days_late=window.days_late(task.due_date) if task.due_date is not None else 0,
    )


def _interaction(interaction: Interaction, window: DayWindow) -> BriefingInteraction:
    names = [c.name for c in interaction.contacts] or [o.name for o in interaction.organizations]
    return BriefingInteraction(
        id=interaction.id,
        kind=interaction.kind,
        subject=interaction.subject,
        occurred_at=interaction.occurred_at,
        duration_minutes=interaction.duration_minutes,
        with_names=names,
        days_late=window.days_late(interaction.occurred_at),
    )


def _watch(watch: Watch, window: DayWindow) -> BriefingWatch:
    return BriefingWatch(
        id=watch.id,
        name=watch.name,
        url=watch.url,
        organization_name=watch.organization_name,
        next_due_at=watch.next_due_at,
        never_swept=watch.last_checked_at is None,
        days_late=window.days_late(watch.next_due_at),
    )


def _capture(capture: Capture, window: DayWindow) -> BriefingCapture:
    return BriefingCapture(
        id=capture.id,
        display_name=capture.display_name,
        url=capture.url,
        note=capture.note,
        created_at=capture.created_at,
        # `days_late` measures calendar days before today, which is the same
        # question asked of a creation date — as the Slack line does.
        days_waiting=window.days_late(capture.created_at),
    )


def to_read(briefing: Briefing) -> BriefingRead:
    window = briefing.window
    return BriefingRead(
        date=window.today,
        timezone=window.tz.key,
        overdue_tasks=[_task(t, window) for t in briefing.overdue_tasks],
        tasks_today=[_task(t, window) for t in briefing.tasks_today],
        interactions_today=[_interaction(i, window) for i in briefing.interactions_today],
        unconfirmed_interactions=[
            _interaction(i, window) for i in briefing.unconfirmed_interactions
        ],
        watches_due=[_watch(w, window) for w in briefing.watches_due],
        captures_waiting=[_capture(c, window) for c in briefing.captures_waiting],
    )


@router.get("/", response_model=BriefingRead)
async def get_briefing(
    now: datetime = Depends(current_time),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> BriefingRead:
    """What wants attention today: the morning briefing, as data.

    Every list is complete — the Slack message caps its sections, this does
    not, so the client decides how much to show and can say how much it left
    out.
    """
    window = DayWindow.containing(now, ZoneInfo(settings.briefing_timezone))
    return to_read(await gather_briefing(session, user, window))
