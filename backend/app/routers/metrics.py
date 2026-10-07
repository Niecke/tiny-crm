"""GET /metrics/dashboard — aggregated numbers for the dashboard (#138).

One request, one response. A dashboard assembled from a dozen requests is a
dozen chances to render half a page, and numbers fetched at different moments
end up side by side. The arithmetic lives in app/metrics.py; DASHBOARD.md is
the catalogue of what is counted and why.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.config import settings
from app.db import get_session
from app.metrics import (
    Period,
    PeriodKind,
    activity_metrics,
    attention_metrics,
    pipeline_metrics,
    trend_metrics,
    velocity_metrics,
)
from app.routers.briefing import current_time
from app.schemas.metrics import DashboardMetrics, PeriodRead

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    period: PeriodKind = Query(default="quarter"),
    now: datetime = Depends(current_time),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> DashboardMetrics:
    """The dashboard's numbers for the calendar `period` containing today.

    Pipeline, the per-stage ages and the attention counts are as of now; the
    rest covers the period, which is echoed back resolved. `trends` is always
    the last ten weeks. Today is a calendar day in BRIEFING_TIMEZONE, as in
    the morning briefing.
    """
    window = Period.containing(period, now, ZoneInfo(settings.briefing_timezone))
    # One session, so the queries run one after another: an AsyncSession is
    # not safe to share between concurrent tasks, and each query is a single
    # grouped aggregate over one operator's rows.
    return DashboardMetrics(
        period=PeriodRead(
            kind=window.kind,
            start=window.first,
            end=window.after,
            timezone=window.tz.key,
            today=window.day.today,
        ),
        pipeline=await pipeline_metrics(session, user.id),
        velocity=await velocity_metrics(session, user.id, window),
        attention=await attention_metrics(session, user.id, window),
        activity=await activity_metrics(session, user.id, window),
        trends=await trend_metrics(session, user.id, now, window.tz),
    )
