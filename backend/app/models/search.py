"""What one search box looks at, per table, and the index that makes it cheap.

Each searchable table gets one *search document*: its text columns glued
together into a single string. A query term matches a row when it is a
substring of that document, case-insensitively — the same `ILIKE '%term%'` the
per-panel boxes have always done, just over every column instead of one. That
is the point of the exercise: a contact is found by part of an email address,
a phone number or a sentence in the notes, not only by its name.

Substring rather than full-text (`tsvector`) on purpose. Full-text matches
whole, stemmed words, which is right for prose and wrong for most of what gets
typed here: "niecke@", "0664", "linkedin.com/in/jane". `pg_trgm` serves
`ILIKE '%…%'` from a GIN index, so the substring match does not cost a
sequential scan once the tables grow.

The document is an *expression*, not a stored column: nothing to keep in sync
on write. For Postgres to use the index the query has to repeat the indexed
expression exactly — which is why `document()` is the one place it is built,
for the index and for `/search` alike — and every part of it has to be
IMMUTABLE. Constants are rendered inline (`_const`) for the same reason: a
bound parameter would not match the index expression.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import reduce
from typing import Any

from sqlalchemy import ColumnElement, Connection, Index, String, event, func, literal
from sqlalchemy.orm import InstrumentedAttribute

from app.db import Base
from app.models.capture import Capture
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.document import Document
from app.models.interaction import Interaction
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.watch import Watch

# `array_to_string` is only STABLE (it has to be, for arrays of types whose text
# form depends on settings), so it cannot appear in an index. For a text array
# it is immutable in practice; this wrapper says so. Created by the migration,
# and by the listener below wherever the schema is built from the models.
TAGS_TEXT_FUNCTION = "tinycrm_tags_text"


# The test suite builds its schema with metadata.create_all rather than Alembic,
# and the indexes below need both of these before any table is created.
@event.listens_for(Base.metadata, "before_create")
def _create_search_prerequisites(target: object, connection: Connection, **kw: object) -> None:
    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    connection.exec_driver_sql(
        f"CREATE OR REPLACE FUNCTION {TAGS_TEXT_FUNCTION}(varchar[]) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, ' ') $$"
    )


def _const(value: str) -> ColumnElement[str]:
    """A string written into the SQL itself rather than sent as a parameter.

    Not `literal_column`: a bare column clause in the expression keeps the
    Index below from finding which table it belongs to.
    """
    return literal(value, String, literal_execute=True)


def _text(column: Any) -> ColumnElement[str]:
    return func.coalesce(column, _const(""))


def _digits(column: Any) -> ColumnElement[str]:
    """A phone number with everything but its digits taken out.

    So "664123" finds "+43 664 123 45 67": nobody remembers which spaces and
    dashes a number was saved with.
    """
    return func.regexp_replace(_text(column), _const("[^0-9]"), _const(""), _const("g"))


@dataclass(frozen=True)
class HitDate:
    """A date in a hit's subtitle, kept as a value rather than written out.

    The browser formats it: only it knows where the reader is, and a task due
    at 23:59 in Vienna is already tomorrow in UTC.
    """

    label: str | None = None
    # A moment, shown as the day it falls on for the reader…
    at: datetime | None = None
    # …or a calendar day, which is the same day everywhere.
    day: date | None = None


def _join(*parts: Any) -> str | None:
    text = " · ".join(str(p) for p in parts if p)
    return text or None


@dataclass(frozen=True)
class Searchable:
    """One table as the search box sees it.

    `fields` are the text columns besides the title, each with the label shown
    when a hit matched there rather than in its title — "Email", "Notes" — so a
    result that does not visibly contain what was typed still says why it is
    there.
    """

    key: str
    model: type[Base]
    # What the hit is called in a list, as SQL (for ranking) and as Python
    # (for the response). Two, because a capture's falls back from name to raw.
    title: ColumnElement[str] | InstrumentedAttribute[str]
    title_of: Callable[[Any], str]
    # One line telling two hits with the same title apart. Required, so a new
    # table cannot join the list without saying what its line is.
    subtitle_of: Callable[[Any], str | None]
    # The date that belongs on that line, where there is one.
    date_of: Callable[[Any], HitDate | None] | None = None
    # The relationships `subtitle_of` reads. /search loads these and nothing
    # else: the models' own `lazy="selectin"` would pull in half the tenant
    # for a line of text.
    loads: tuple[InstrumentedAttribute[Any], ...] = ()
    fields: tuple[tuple[str, str], ...] = ()
    tags: bool = False
    phones: tuple[str, ...] = ()
    # Off where the title is itself built from columns already in `fields`.
    title_in_document: bool = True

    @property
    def user_id(self) -> InstrumentedAttribute[Any]:
        column: InstrumentedAttribute[Any] = getattr(self.model, "user_id")
        return column

    @property
    def id(self) -> InstrumentedAttribute[Any]:
        column: InstrumentedAttribute[Any] = getattr(self.model, "id")
        return column

    def document(self) -> ColumnElement[str]:
        parts: list[ColumnElement[str]] = [_text(self.title)] if self.title_in_document else []
        parts += [_text(getattr(self.model, attr)) for attr, _ in self.fields]
        if self.tags:
            tags = getattr(self.model, "tags")
            parts.append(_text(getattr(func, TAGS_TEXT_FUNCTION)(tags)))
        parts += [_digits(getattr(self.model, attr)) for attr in self.phones]
        sep = _const(" ")
        return reduce(lambda a, b: a.op("||")(sep).op("||")(b), parts)


# The order is the order groups are listed in: people and companies first,
# because they are what is searched for most; the inbox last, because it is
# where things wait rather than where they live.
SEARCHABLES: tuple[Searchable, ...] = (
    Searchable(
        key="contacts",
        model=Contact,
        title=Contact.name,
        title_of=lambda c: c.name,
        subtitle_of=lambda c: _join(c.job_title, c.organization_name) or c.email,
        loads=(Contact.organization,),
        fields=(
            ("email", "Email"),
            ("email_secondary", "Email"),
            ("phone", "Phone"),
            ("phone_secondary", "Phone"),
            ("job_title", "Job title"),
            ("website", "Website"),
            ("street", "Address"),
            ("postal_code", "Address"),
            ("city", "Address"),
            ("notes", "Notes"),
        ),
        tags=True,
        phones=("phone", "phone_secondary"),
    ),
    Searchable(
        key="organizations",
        model=Organization,
        title=Organization.name,
        title_of=lambda o: o.name,
        subtitle_of=lambda o: _join(o.domain, o.industry),
        fields=(
            ("domain", "Domain"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("address", "Address"),
            ("industry", "Industry"),
            ("notes", "Notes"),
        ),
        phones=("phone",),
    ),
    Searchable(
        key="deals",
        model=Deal,
        title=Deal.title,
        title_of=lambda d: d.title,
        subtitle_of=lambda d: _join(d.stage.capitalize(), d.organization_name or d.contact_name),
        loads=(Deal.organization, Deal.contact),
        fields=(("notes", "Notes"), ("lost_reason", "Lost reason")),
    ),
    Searchable(
        key="tasks",
        model=Task,
        title=Task.title,
        title_of=lambda t: t.title,
        subtitle_of=lambda t: "Done" if t.done else None,
        date_of=lambda t: (
            HitDate(label="Due", at=t.due_date) if t.due_date and not t.done else None
        ),
        fields=(("description", "Description"),),
        tags=True,
    ),
    Searchable(
        key="interactions",
        model=Interaction,
        title=Interaction.subject,
        title_of=lambda i: i.subject,
        subtitle_of=lambda i: i.kind.capitalize(),
        date_of=lambda i: HitDate(at=i.occurred_at),
        fields=(("notes", "Notes"),),
        tags=True,
    ),
    Searchable(
        key="projects",
        model=Project,
        title=Project.name,
        title_of=lambda p: p.name,
        subtitle_of=lambda p: None,
        date_of=lambda p: HitDate(label="Since", day=p.start_date),
        fields=(("description", "Description"),),
    ),
    Searchable(
        key="documents",
        model=Document,
        title=Document.title,
        title_of=lambda d: d.title,
        subtitle_of=lambda d: str(d.format).upper(),
        fields=(("description", "Description"),),
        tags=True,
    ),
    Searchable(
        key="watches",
        model=Watch,
        title=Watch.name,
        title_of=lambda w: w.name,
        subtitle_of=lambda w: _join(w.kind.replace("_", " ").capitalize(), w.organization_name),
        loads=(Watch.organization,),
        fields=(("url", "URL"), ("query_note", "Search"), ("notes", "Notes")),
    ),
    Searchable(
        key="captures",
        model=Capture,
        # A capture's name is a guess and often missing; `raw` is what was
        # typed, and the only thing half of them can be found by. Both are in
        # the document either way.
        title=func.coalesce(Capture.name, Capture.raw),
        title_of=lambda c: c.display_name,
        # The inbox's own word for a capture still waiting for a decision.
        subtitle_of=lambda c: "Waiting" if c.status == "new" else str(c.status).capitalize(),
        fields=(("name", "Name"), ("raw", "Captured"), ("url", "URL"), ("note", "Note")),
        title_in_document=False,
    ),
)


for _searchable in SEARCHABLES:
    Index(
        f"ix_{getattr(_searchable.model, '__tablename__')}_search",
        _searchable.document().label("search_document"),
        postgresql_using="gin",
        postgresql_ops={"search_document": "gin_trgm_ops"},
    )
