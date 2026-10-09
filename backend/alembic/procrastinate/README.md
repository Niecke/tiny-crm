# procrastinate's schema, vendored

The background worker's job queue (`app/jobs/`, #206) keeps its tables in the
application database. Their definition is procrastinate's, not ours, and it
changes with the library — so the SQL is copied here and applied by Alembic,
which stays the only way the schema of this database ever changes.

| File | Applied by |
|---|---|
| `schema_3.10.0.sql` | `versions/v2w3x4y5z6a7_procrastinate_schema.py` |

`schema_<version>.sql` is the output of `procrastinate schema --read` for that
version: the complete schema, for a database that has none of it yet.

## Upgrading procrastinate

`pyproject.toml` pins the exact version, and Renovate opens its update without
automerge. `tests/test_jobs.py` compares the installed version's schema with the
newest `schema_*.sql` here, so an update that changes the schema fails the suite
until this directory has caught up:

1. List the migrations the new version brings:

       ls .venv/lib/python*/site-packages/procrastinate/sql/migrations/

   Every file sorting after the newest version in the table above is new. Copy
   them here unchanged, keeping their names.
2. Write one Alembic revision that runs them in name order, the way
   `v2w3x4y5z6a7` runs the full schema. Files named `*_pre_*` are safe while
   the old code still runs; `*_post_*` want every process on the new version
   first — the release notes say when that needs a second revision, shipped one
   release later.
3. Add the new `procrastinate schema --read` as `schema_<version>.sql` and a row
   to the table. It is the reference the test compares against; no revision
   applies it.

`schema_3.10.0.sql` stays as it is: the first revision creates a database from
it, and the later revisions bring that database up to date. Never edit a
vendored file.
