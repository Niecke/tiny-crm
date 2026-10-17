---
name: backend-tests
description: Run the tinyCRM backend checks the way CI does — ruff, mypy strict and the pytest suite against the in-memory test Postgres (compose.test.yml, container tinycrm-test-db, port 55433), starting that database if needed. Use after changing anything under backend/, before reporting backend work as done, when the user asks to run, check or verify the backend tests, or invokes /backend-tests. Optional arguments are passed to pytest (a file, a -k expression, a node id).
---

# Backend tests

Runs what the `backend-tests` job in `.github/workflows/ci.yml` runs, in the same
order, against the same kind of database. Paths below are relative to the repo root.

## 1. Test database

```bash
.claude/skills/backend-tests/scripts/ensure-test-db.sh
```

It prints the `TEST_DATABASE_URL` (`postgresql+asyncpg://crm:crm@localhost:55433/postgres`,
also conftest's default) or exits non-zero with the reason. On failure, stop and
report that reason; do not work around it.

Rules:
- Only ever use `tinycrm-test-db` on port 55433. Never point the tests at port 5432:
  that is the dev stack's database or another project's (energy_agent's `pg-test`
  lives there and has other credentials).
- Never stop, remove or restart any other container. Leave `tinycrm-test-db`
  running afterwards; the next run reuses it. It holds nothing worth keeping.
- `InvalidPasswordError`, `connection refused` or `Operation not permitted` from
  asyncpg are infrastructure, not test failures. `Operation not permitted` means the
  sandbox blocks localhost: re-run the command with the sandbox disabled.
- `DiskFullError`, `checkpoint request failed`, `the database system is shutting
  down` or `terminating connection due to administrator command` mean the test
  server itself broke. Recreate it, then re-run only what errored:
  `podman-compose -f compose.test.yml down` and the script above again. That is the
  one container this skill may remove.

## 2. Checks

Run from `backend/`, each as its own command, and go on after a failure so the
report covers all of them:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
```

## 3. Tests

Without arguments, the whole suite in parallel (about 3 minutes on 8 cores; give the
command a 10-minute timeout):

```bash
set -o pipefail; uv run pytest -q -n auto --tb=short 2>&1 | tail -60
```

With arguments, pass them through. Add `-n auto` only if they select several files;
one file or one test runs faster serially:

```bash
set -o pipefail; uv run pytest -q --tb=short $ARGUMENTS 2>&1 | tail -60
```

`pipefail` makes the command exit with pytest's code instead of `tail`'s, which
is always 0. Without it a failed run reports success.

If the tail cuts off a failure you need, re-run only the failing node ids with
`--tb=long`. Do not re-run the whole suite to see more output.

A test that fails under `-n auto` but passes alone is a real bug (shared state
between tests in one worker), not flakiness: report it as such.

## 4. Report

One line per check: passed, or failed with the count. A non-zero exit code is a
failure, even if the visible tail looks clean. For each failing test, give
its node id and the assertion or error line, nothing more. Put infrastructure
problems (step 1) apart from test failures.

Fix failures only when fixing them is part of the task you are on, or the user asks.
Never edit a test just to make it pass.
