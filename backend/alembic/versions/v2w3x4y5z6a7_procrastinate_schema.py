"""procrastinate's schema

The job queue of the background worker (#206, app/jobs/): procrastinate's
tables, types, functions and triggers, all named `procrastinate_*`. They live
in the application database so the queue needs no service of its own and is in
the nightly backup with everything else.

The SQL is procrastinate's own, vendored as alembic/procrastinate/ — see the
README there for what an upgrade of the library needs. It is applied here
rather than with `procrastinate schema --apply` so that this migration stays
the only path a schema change takes.

Expand only: the previous release neither reads nor writes any of it.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-10-09 21:10:00.000000

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v2w3x4y5z6a7"
down_revision: str | Sequence[str] | None = "u1v2w3x4y5z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = Path(__file__).resolve().parent.parent / "procrastinate" / "schema_3.10.0.sql"


def upgrade() -> None:
    """Upgrade schema."""
    # The file is one script of many statements, some of them function bodies
    # full of semicolons. SQLAlchemy's asyncpg dialect prepares what it runs,
    # and a prepared statement holds a single command — so the script goes to
    # the driver connection itself, whose execute() takes a whole script.
    #
    # Same connection, same transaction: Alembic read alembic_version on it
    # before calling this, so the transaction is already open and a failure
    # half-way rolls all of it back.
    connection = op.get_bind().connection.dbapi_connection
    assert connection is not None
    script = SCHEMA.read_text(encoding="utf-8")
    connection.run_async(lambda driver: driver.execute(script))


def downgrade() -> None:
    """Downgrade schema.

    Every job goes with it, pending ones included: a reset mail that was
    queued and not yet sent is never sent.
    """
    # CASCADE takes the triggers and the indexes along.
    op.execute(
        "DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, "
        "procrastinate_jobs, procrastinate_workers CASCADE"
    )
    # By name pattern rather than one by one: the signatures are procrastinate's
    # to change, and they must all be gone before the types they use.
    op.execute(
        r"""
        DO $$
        DECLARE
            fn regprocedure;
        BEGIN
            FOR fn IN
                SELECT oid::regprocedure
                  FROM pg_proc
                 WHERE proname LIKE 'procrastinate\_%'
                   AND pronamespace = current_schema()::regnamespace
            LOOP
                EXECUTE 'DROP FUNCTION ' || fn || ' CASCADE';
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        "DROP TYPE IF EXISTS procrastinate_job_to_defer_v1, procrastinate_job_event_type, "
        "procrastinate_job_status"
    )
