<!--
The title is the squash commit on main and must be a conventional commit
(feat:, fix:, chore:, …) — commitlint checks it, and release-please derives the
next version from it.
-->

## What and why



## Checklist

- [ ] No Alembic migration in this pull request, **or** every migration works
      with the previous release still running (expand/contract): add and
      backfill in one release, stop writing the old column in the next, drop it
      in a third. Migrations do not roll back with the image — see
      `deploy/README.md`, "Rolling back".
