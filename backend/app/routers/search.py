"""One search box over everything (#126).

Every term typed has to appear somewhere in a row's search document — "anna
acme" finds the Anna whose notes mention ACME, not every Anna and every ACME.
What a search document holds per table, and the trigram index behind it, is in
app/models/search.py.
"""

import re
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, raiseload

from app.auth import current_active_user
from app.auth.users import User
from app.db import contains, count_rows, escape_like, get_session
from app.models.search import SEARCHABLES, Searchable
from app.schemas.search import (
    SearchDate,
    SearchGroup,
    SearchHit,
    SearchMatch,
    SearchResults,
    SearchType,
)

router = APIRouter(prefix="/search", tags=["search"])

# One character matches most of every table and has no trigram for the index
# to look up, so it is a full scan of all nine for a list nobody can use.
MIN_QUERY_LENGTH = 2
# More terms than this is a pasted paragraph, not a search; each one is another
# ILIKE on every table.
MAX_TERMS = 8
# Characters either side of a match in an excerpt.
EXCERPT_CONTEXT = 30


def _terms(q: str) -> list[str]:
    return q.split()[:MAX_TERMS]


def _digits(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def _excerpt(value: str, start: int, length: int) -> str:
    """The matched text with a little of what surrounds it, on one line."""
    begin = max(0, start - EXCERPT_CONTEXT)
    end = min(len(value), start + length + EXCERPT_CONTEXT)
    text = " ".join(value[begin:end].split())
    return ("…" if begin > 0 else "") + text + ("…" if end < len(value) else "")


def _match(searchable: Searchable, row: Any, title: str, terms: list[str]) -> SearchMatch | None:
    """The first field that explains the hit, unless its title already does.

    A term the title contains needs no explaining; for the first one it does
    not, the first field holding it is shown. Phone numbers are also compared
    digits-only, the same way the search document holds them.
    """
    lowered_title = title.lower()
    for term in terms:
        needle = term.lower()
        if needle in lowered_title:
            continue
        for attr, label in searchable.fields:
            value = getattr(row, attr)
            if not value:
                continue
            at = value.lower().find(needle)
            if at >= 0:
                return SearchMatch(field=label, excerpt=_excerpt(value, at, len(needle)))
            if attr in searchable.phones and needle.isdigit() and needle in _digits(value):
                return SearchMatch(field=label, excerpt=value)
        if searchable.tags:
            for tag in getattr(row, "tags") or []:
                if needle in tag.lower():
                    return SearchMatch(field="Tag", excerpt=tag)
    return None


async def _search_one(
    session: AsyncSession,
    searchable: Searchable,
    user_id: UUID,
    terms: list[str],
    skip: int,
    limit: int,
) -> SearchGroup:
    document = searchable.document()
    q: Select[tuple[Any]] = select(searchable.model).where(
        searchable.user_id == user_id,
        # Archived records are not found, and there is no switch to find them:
        # each list has its own archive, and that is where to look (#140).
        searchable.archived_at.is_(None),
        *(contains(document, term) for term in terms),
    )
    phrase = " ".join(terms)
    # Titles that start with what was typed first, then by how close the title
    # is to it, then alphabetically — so "Anna" ranks Anna Berger above
    # Johanna, and both above a contact whose notes merely mention an Anna.
    starts = case((searchable.title.ilike(f"{escape_like(terms[0])}%", escape="\\"), 0), else_=1)
    ranked = q.order_by(
        starts,
        func.word_similarity(phrase, searchable.title).desc(),
        func.lower(searchable.title),
        searchable.id,
    )
    total = await count_rows(session, q)
    # Only what a hit's subtitle reads is loaded along with it; reaching for
    # anything else raises instead of quietly costing a query per row.
    loaded = ranked.options(*(joinedload(r) for r in searchable.loads), raiseload("*"))
    rows = (await session.execute(loaded.offset(skip).limit(limit))).scalars().all()

    items = []
    for row in rows:
        title = searchable.title_of(row)
        date = searchable.date_of(row) if searchable.date_of else None
        items.append(
            SearchHit(
                id=row.id,
                type=cast(SearchType, searchable.key),
                title=title,
                subtitle=searchable.subtitle_of(row),
                date=SearchDate(label=date.label, at=date.at, day=date.day) if date else None,
                match=_match(searchable, row, title, terms),
            )
        )
    return SearchGroup(type=cast(SearchType, searchable.key), total=total, items=items)


@router.get("/", response_model=SearchResults)
async def search(
    q: str = Query(min_length=MIN_QUERY_LENGTH, max_length=200),
    # One type only, for paging through it on the results page. Without it,
    # every type answers with its first `limit` hits.
    type: SearchType | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> SearchResults:
    if "\x00" in q:
        # Postgres text cannot hold a NUL, and the driver refuses to send one.
        raise HTTPException(status_code=422, detail="The search holds a character no record can")
    terms = _terms(q)
    # Counted without the padding: "  a  " is as long as the parameter asks for.
    if len(" ".join(terms)) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"Type at least {MIN_QUERY_LENGTH} characters to search for"
        )
    if skip and type is None:
        # Paging all nine groups at once would page each one by the same
        # offset, which is no list anybody reads.
        raise HTTPException(status_code=422, detail="skip needs a type to page through")

    groups = [
        await _search_one(session, s, user.id, terms, skip, limit)
        for s in SEARCHABLES
        if type is None or s.key == type
    ]
    return SearchResults(q=" ".join(terms), groups=groups)
