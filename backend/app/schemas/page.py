from pydantic import BaseModel


class Page[T](BaseModel):
    """One slice of a list endpoint, plus the size of the whole result set.

    `total` is what the client needs to know that more rows exist: without it a
    short page and the last page look identical, so the UI silently stops at the
    limit instead of offering the rest.
    """

    items: list[T]
    total: int
    skip: int
    limit: int
