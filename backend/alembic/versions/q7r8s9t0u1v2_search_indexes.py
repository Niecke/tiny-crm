"""trigram search indexes for the app-wide search box

One GIN index per searchable table, over the same search-document expression
`app/models/search.py` builds for `/search` (#126). The expressions are copied
here as SQL rather than imported: a migration is a snapshot, and a later change
to what is searchable belongs in a migration of its own. If the two ever
disagree the index is simply not used — search still answers, just with a
sequential scan — so a mismatch costs speed, never results.

`pg_trgm` ships with Postgres and is a trusted extension, so the database owner
can create it without superuser rights.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-10-03 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q7r8s9t0u1v2"
down_revision: str | Sequence[str] | None = "p6q7r8s9t0u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _text(column: str) -> str:
    return f"coalesce({column}, '')"


def _tags(column: str) -> str:
    return _text(f"tinycrm_tags_text({column})")


def _digits(column: str) -> str:
    return f"regexp_replace({_text(column)}, '[^0-9]', '', 'g')"


# Each table's search document, part by part, in the order the model lists them.
DOCUMENTS: dict[str, list[str]] = {
    "contacts": [
        *map(
            _text,
            [
                "name",
                "email",
                "email_secondary",
                "phone",
                "phone_secondary",
                "job_title",
                "website",
                "street",
                "postal_code",
                "city",
                "notes",
            ],
        ),
        _tags("tags"),
        _digits("phone"),
        _digits("phone_secondary"),
    ],
    "organizations": [
        *map(_text, ["name", "domain", "email", "phone", "address", "industry", "notes"]),
        _digits("phone"),
    ],
    "deals": [*map(_text, ["title", "notes", "lost_reason"])],
    "tasks": [*map(_text, ["title", "description"]), _tags("tags")],
    "interactions": [*map(_text, ["subject", "notes"]), _tags("tags")],
    "projects": [*map(_text, ["name", "description"])],
    "documents": [*map(_text, ["title", "description"]), _tags("tags")],
    "watches": [*map(_text, ["name", "url", "query_note", "notes"])],
    "captures": [*map(_text, ["name", "raw", "url", "note"])],
}


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # array_to_string is only STABLE, so it cannot appear in an index; for a
    # text array it is immutable in practice, and this wrapper says so.
    op.execute(
        "CREATE OR REPLACE FUNCTION tinycrm_tags_text(varchar[]) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, ' ') $$"
    )
    for table, parts in DOCUMENTS.items():
        document = " || ' ' || ".join(parts)
        op.execute(
            f"CREATE INDEX ix_{table}_search ON {table} USING gin (({document}) gin_trgm_ops)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in DOCUMENTS:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_search")
    op.execute("DROP FUNCTION IF EXISTS tinycrm_tags_text(varchar[])")
    # The extension stays: dropping it would break anything else that came to
    # rely on it, and leaving an unused extension installed costs nothing.
