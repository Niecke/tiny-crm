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


class SearchHit(BaseModel):
    id: UUID
    type: SearchType
    title: str
    # One short line of context: the company, the stage, the date — whatever
    # tells two hits with the same title apart.
    subtitle: str | None = None
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
