"""procrastinate's schema

The job queue of the background worker (#206, app/jobs/): procrastinate's
tables, types, functions and triggers, all named `procrastinate_*`. They live
in the application database so the queue needs no service of its own and is in
the nightly backup with everything else.

The SQL is procrastinate's own and is read from the installed package, which
ships its whole migration history as files. Nothing is copied into this
repository; a revision only names the files it applies. This one applies
everything up to 3.10.0, which is how a database that has followed
procrastinate since its first release got there.

It is applied here rather than with `procrastinate schema --apply` so that
Alembic stays the only path a schema change takes.

**When procrastinate is updated** and brings new files, tests/test_jobs.py
fails and lists them. Add a revision with its own PROCRASTINATE_MIGRATIONS
naming those files, applied the way upgrade() below applies these. Files
called `*_pre_*` are safe while the previous release still runs; `*_post_*`
want every process on the new version first — the release notes say when that
needs a second revision, shipped one release later.

Expand only: the previous release neither reads nor writes any of it.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-10-09 21:10:00.000000

"""

from collections.abc import Sequence
from importlib import resources

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v2w3x4y5z6a7"
down_revision: str | Sequence[str] | None = "u1v2w3x4y5z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Files of the `procrastinate.sql.migrations` package, in the order they are
# applied — which is their order by name. Named one by one rather than "all
# there are": what this revision does must not change when the library does.
PROCRASTINATE_MIGRATIONS = (
    "00.00.00_01_initial.sql",
    "00.05.00_01_drop_started_at_column.sql",
    "00.05.00_02_drop_started_at_column.sql",
    "00.05.00_03_drop_procrastinate_version_table.sql",
    "00.06.00_01_fix_procrastinate_fetch_job.sql",
    "00.07.01_01_fix_trigger_status_events_insert.sql",
    "00.08.01_01_add_queueing_lock_column.sql",
    "00.10.00_01_close_fetch_job_race_condition.sql",
    "00.10.00_02_add_defer_job_function.sql",
    "00.11.00_03_add_procrastinate_periodic_defers.sql",
    "00.12.00_01_add_foreign_key_index.sql",
    "00.14.00_01_add_locks_to_periodic_defer.sql",
    "00.15.02_01_fix_procrastinate_defer_periodic_job.sql",
    "00.16.00_01_add_finish_job_and_retry_job_functions.sql",
    "00.17.00_01_add_trigger_on_job_deletion.sql",
    "00.17.00_02_delete_finished_jobs.sql",
    "00.17.00_03_add_checks_to_finish_job.sql",
    "00.17.00_04_add_checks_to_retry_job.sql",
    "00.18.01_01_fix_finish_job_compat_issue.sql",
    "00.19.00_01_add_index_on_procrastinate_jobs.sql",
    "00.22.00_01_add_kwargs_to_defer_periodic_job.sql",
    "00.23.00_01_null_locks_excluded.sql",
    "01.00.00_01_remove_old_finish_job_function.sql",
    "01.01.01_01_job_id_bigint.sql",
    "02.00.03_01_add_job_priority.sql",
    "02.05.00_01_add_periodic_job_priority.sql",
    "02.06.00_01_add_cancel_states.sql",
    "02.08.00_01_add_additional_params_to_retry_job.sql",
    "02.14.01_01_add_indexes_for_fetch_job.sql",
    "03.00.00_01_pre_cancel_notification.sql",
    "03.00.00_50_post_cancel_notification.sql",
    "03.01.00_01_pre_add_heartbeat.sql",
    "03.01.00_50_post_add_heartbeat.sql",
    "03.02.00_01_pre_batch_defer_jobs.sql",
    "03.02.00_50_post_batch_defer_jobs.sql",
    "03.03.00_01_pre_priority_lock_fetch_job.sql",
    "03.04.00_01_pre_add_retry_failed_job_procedure.sql",
    "03.04.00_50_post_add_retry_failed_job_procedure.sql",
)


def upgrade() -> None:
    """Upgrade schema."""
    # Each file is a script of several statements, some of them function bodies
    # full of semicolons. SQLAlchemy's asyncpg dialect prepares what it runs,
    # and a prepared statement holds a single command — so the scripts go to
    # the driver connection itself, whose execute() takes a whole script.
    #
    # Same connection, same transaction: Alembic read alembic_version on it
    # before calling this, so the transaction is already open and a failure
    # half-way rolls all of it back.
    connection = op.get_bind().connection.dbapi_connection
    assert connection is not None
    scripts = resources.files("procrastinate.sql.migrations")
    for name in PROCRASTINATE_MIGRATIONS:
        # A file procrastinate no longer ships fails here, loudly, on the next
        # empty database — which is every run of ci/smoke.sh.
        script = scripts.joinpath(name).read_text(encoding="utf-8")
        connection.run_async(lambda driver, script=script: driver.execute(script))


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
