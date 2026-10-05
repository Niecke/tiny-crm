from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# Spelled out rather than derived from SEARCHABLES so the OpenAPI schema, and
# with it the generated client types, carry the closed set. A test keeps the
# two in step.
SearchType = Literal[
    "contacts",
    "organizations",
    "deals",
    "tasks",
    "interactions",
    "projects",
    "documents",
    "watches",
    "captures",
]


class SearchMatch(BaseModel):
    """Where a hit matched, when it was not in its title.

    A contact found by its phone number shows a name that does not contain
    what was typed; this is the line that says why it is in the list.
    """

    field: str
    excerpt: str


class SearchDate(BaseModel):
    """A date that belongs in a hit's subtitle: "Due …", "Since …".

    Sent as a value, not as text, because only the client knows the reader's
    timezone and locale. Exactly one of `at` and `day` is set.
    """

    label: str | None = None
    # A moment; the day shown is the one it falls on where the reader is.
    at: datetime | None = None
    # A calendar day, the same day everywhere.
    day: date | None = None


class SearchHit(BaseModel):
    id: UUID
    type: SearchType
    title: str
    # One short line of context: the company, the stage — whatever tells two
    # hits with the same title apart. `date` continues it.
    subtitle: str | None = None
    date: SearchDate | None = None
    match: SearchMatch | None = None


class SearchGroup(BaseModel):
    type: SearchType
    # Every match of this type, not only the ones in `items`, so the client
    # can offer "show all 14".
    total: int
    items: list[SearchHit]


class SearchResults(BaseModel):
    q: str
    # One per type, in a fixed order, empty ones included — or only the one
    # asked for with `?type=`.
    groups: list[SearchGroup]
