"""Whether a deal has a next step: an open task, or a planned interaction.

An open deal with neither is invisible. Nothing in the app would mention it
again — no task comes due, no meeting lands on the calendar — so it simply
stops existing until someone scrolls past it. This is the question that finds
those.

*Computed per query, never stored.* A cached flag would have to be invalidated
from the task router, the interaction router and every completion, and would be
wrong the first time one of them was missed. An EXISTS per deal row costs
nothing at one operator's volume and cannot drift.

Its own module because it needs `Task` and `Interaction`, and both of those
import `Deal`: the expression cannot be written inside the class it describes.
It is attached from here instead, and `app/models/__init__.py` imports this
module, so every entry point — which always goes through that package — sees
`Deal.has_next_step` before its first query.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, exists, func, or_
from sqlalchemy.orm import column_property

from app.archive import live
from app.models.deal import Deal
from app.models.interaction import Interaction, interaction_deals
from app.models.task import Task


def next_step_exists(after: datetime | ColumnElement[datetime]) -> ColumnElement[bool]:
    """True for a deal with an open task, or a planned interaction from `after` on.

    Correlated against `deals`, so it works both as a column and in a WHERE.

    `after` is a parameter because the briefing asks from the start of the
    operator's day, not from this instant: a meeting at 10:00 that is still
    unconfirmed at 11:00 is on today's calendar, and the deal it is about has
    not been forgotten.

    An open task counts whatever its due date — overdue or undated — because
    either one still names the next thing to do; overdue tasks already have a
    briefing section of their own. A planned interaction is one not yet marked
    as happened, matching the briefing's own idea of "planned".

    Neither counts once archived. A task that no list shows will never come
    due in front of anyone, so the deal it belongs to is as forgotten as one
    with no task at all.
    """
    open_task = (
        exists()
        .where(Task.deal_id == Deal.id, Task.done.is_(False), live(Task))
        .correlate_except(Task)
    )
    planned = (
        exists()
        .where(
            interaction_deals.c.deal_id == Deal.id,
            interaction_deals.c.interaction_id == Interaction.id,
            Interaction.done.is_(False),
            Interaction.occurred_at >= after,
            live(Interaction),
        )
        .correlate_except(Interaction, interaction_deals)
    )
    return or_(open_task, planned)


# Loaded with every Deal, so DealRead stays a plain model_validate and the
# single-deal endpoints, the capture conversion and the list all carry it
# without each remembering to ask. `now()` is the transaction's clock.
setattr(Deal, "has_next_step", column_property(next_step_exists(func.now())))
