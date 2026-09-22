# Security audit — tinyCRM backend

**Date:** 2026-09-22
**Scope:** `backend/` (FastAPI app, scripts, Dockerfile) and the deployment that
serves it (`charts/tinycrm/`, `.github/workflows/`). The Flutter frontend is out
of scope at the operator's request.
**Method:** full manual read of every module under `backend/app`, plus the
schemas, models, migrations, chart templates and CI workflows. Every finding
below marked *Verified* was reproduced against the running application on a
throwaway Postgres; the reproduction is given with it. The existing suite
(282 tests) passes unchanged — nothing here is a regression, and none of the
findings is caught by a current test.

## Summary

| # | Severity | Finding |
|---|----------|---------|
| 1 | **High** | `PATCH /users/me` changes the password and the email with no re-authentication, bypassing the deliberate old-password check |
| 2 | **High** | Tokens live 270 days, cannot be revoked, and survive a password change |
| 3 | **High** | Unauthenticated callers can spool unbounded uploads to disk before the 25 MB check or auth runs |
| 4 | Medium | No length or cardinality limit on any request field, and no JSON body cap |
| 5 | Medium | The backend holds MinIO **root** credentials instead of a bucket-scoped key |
| 6 | Medium | The container runs as root; no pod `securityContext`, no `NetworkPolicy` |
| 7 | Low | `Content-Disposition` is built from the raw document title |
| 8 | Low | `tags` is `json.loads`ed outside the error handler and never type-checked |
| 9 | Low | Login throttle is per-IP, in-process, and resets on every redeploy |
| 10 | Low | Watch URLs are unvalidated and rendered as links in the Slack briefing |
| 11 | Low | `/docs`, `/openapi.json` and `/version` are unauthenticated |
| 12 | Low | `create_admin.py` takes the password as a command-line argument |

---

## 1. `PATCH /users/me` rewrites the password and email with no re-authentication — **High**

`app/routers/users.py` implements a careful password change: it verifies
`old_password`, runs `validate_password`, and stamps `password_changed_at`. The
schema enforces `min_length=8`.

`app/main.py:111-115` then also mounts the stock fastapi-users router:

```python
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
```

`UserUpdate` extends `fu_schemas.BaseUserUpdate`, which carries `password` and
`email`. That router's `PATCH /users/me` calls `user_manager.update(..., safe=True)`,
which only strips `is_superuser`, `is_active` and `is_verified` — `password` and
`email` go straight through. So the custom endpoint is not the only way to change
a password; it is the only *checked* way.

**Verified.** Against the real app:

```
PATCH /users/me {"password": "x"}      -> 200
login with the OLD password            -> 400   (password really was changed)
login with the 1-character password    -> 200   (min_length=8 not applied)
GET /users/me -> password_changed_at   -> null  (audit field never stamped)

PATCH /users/me {"email": "attacker@evil.example"} -> 200
login as attacker@evil.example with the old password -> 200
```

**Impact.** Anyone holding a token — see finding 2 for how long that is — takes
the account over permanently without ever knowing the current password: set a new
password, move the email to one you control, and the operator is locked out of
their own CRM. It also silently defeats the password policy and leaves
`password_changed_at` lying, so the one signal that would show the takeover reads
`null`.

**Fix.** Narrow the stock router to the routes actually wanted. Either mount only
`GET /users/me` (`fastapi_users.get_users_router(...)` is all-or-nothing, so the
practical move is to hand-write the two-line `GET /users/me` alongside the
existing password endpoint and drop the stock router entirely), or override
`UserManager.update` to reject `password` and `email` when `safe=True`. The
superuser routes it also mounts (`GET|PATCH|DELETE /users/{id}`, where
`create_update_dict_superuser` *does* allow `is_superuser`) are unused surface on
a single-operator app and should go with it.

## 2. Tokens live 270 days, cannot be revoked, and survive a password change — **High**

`app/config.py:35` sets `jwt_lifetime_seconds = 60 * 60 * 24 * 270`, and
`app/auth/users.py:44-45` issues a plain stateless `JWTStrategy` — no `jti`, no
deny list, no server-side session record. `POST /auth/jwt/logout` therefore does
nothing to the token; it only tells the client to forget it.

`password_changed_at` is written by the password endpoint and returned by
`UserRead`, but `grep` finds no other reader: nothing compares a token's `iat`
against it.

**Verified.**

```
POST /users/me/password (correct old password) -> 204
GET /users/me with the token issued BEFORE the change -> 200
```

**Impact.** A token that leaks — from a browser's storage on a shared machine, a
proxy log, a copied `curl` command — is a working key to the whole CRM for up to
nine months, and the one remediation a user would reach for (change the password)
does not close it. Combined with finding 1, the holder of that token does not need
the password at all.

**Fix.** The data to close this is already on the row. Reject a token whose `iat`
predates `password_changed_at` — a custom `JWTStrategy.read_token` that loads the
user and compares is ~10 lines, and turns the existing password change into a real
"sign out everywhere". Independently, cut `jwt_lifetime_seconds` to hours or days
and add a refresh token; 270 days is the value that makes every other token
weakness nine months long.

## 3. Unauthenticated unbounded upload spools to disk before auth — **High**

`app/routers/documents.py:75-88` checks the upload size, with a comment
explaining that Starlette "has already received the body — spooling it to a temp
file past 1 MB — and recorded its length, so this reads a counter rather than the
file." That is accurate, and it is the problem: the check runs *after* the bytes
have landed.

Two things make it reachable without a token. FastAPI parses the form body
(`fastapi/routing.py:430`) *before* it resolves dependencies
(`fastapi/routing.py:481`), so `current_active_user` never gets a chance to reject
the request first. And Starlette's `max_part_size` (1 MB) applies only to
non-file parts — file parts go to a `SpooledTemporaryFile` with no ceiling
(`starlette/formparsers.py:184`, `:230`).

**Verified.** Against the real app, with no `Authorization` header:

```
curl -X POST -F file=@300MB.bin -F title=x http://…/documents/
status=401  uploaded=314573113  time=2.7s
```

All 300 MB were accepted and written to the container's filesystem, and only then
was the request refused. Nothing in the chain caps it: `charts/tinycrm/templates/ingress.yaml`
sets no Traefik `buffering` middleware, and `charts/tinycrm/templates/backend.yaml`
sets no `ephemeral-storage` limit. The node's 40 GB boot disk is shared with
Postgres and MinIO.

**Impact.** An unauthenticated attacker fills the node's disk in a few minutes of
looping, taking the database and the object store down with the API. `PUT /documents/{id}/content`
has the same shape.

**Fix.** Cap the body before it reaches the app, at the ingress
(`traefik.io/v1alpha1 Middleware` with `buffering.maxRequestBodyBytes: 26214400`)
— that is the only layer that can refuse it before the bytes are written. Add
`resources.limits.ephemeral-storage` on the backend pod so a miss is contained to
one pod rather than the node. In the app, an ASGI middleware that rejects a
`Content-Length` over the limit before the route runs closes the direct-to-pod
path.

## 4. No length or cardinality limits on any request field — **Medium**

No schema in `app/schemas/` sets `max_length` on a string or `max_length` on a
list: `name: str`, `notes: str | None`, `tags: list[str] = []`, `title: str` are
all unbounded. The columns behind them are `Mapped[str]`, i.e. Postgres `TEXT`,
also unbounded. Starlette reads a JSON body fully into memory with no cap.

**Verified.**

```
POST /contacts/ {"name": "A" * 5_242_880}   -> 201
POST /contacts/ {"tags": ["x"] * 100_000}   -> 201
```

**Impact.** Storage growth and memory pressure that no quota catches, on the same
10 GB volume the database lives on. Lower than finding 3 because it needs a valid
token, and this is a single-operator instance — but it is the same disk.

**Fix.** `Field(max_length=...)` on every user-supplied string (a few hundred
characters for names and titles, a few thousand for notes), and `max_length` on
every list field including the link-id lists. Mirror the caps in the columns
(`String(255)`) so the database is the backstop rather than the app.

## 5. The backend holds MinIO root credentials — **Medium**

`charts/tinycrm/templates/backend.yaml` fills `S3_ACCESS_KEY` / `S3_SECRET_KEY`
from `.Values.minio.rootUser` / `.rootPassword` — the same credentials MinIO's
`StatefulSet` gets as `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

**Impact.** The API process can do anything to the object store, including
deleting buckets and purging the object versions that the chart deliberately
enables (`mc version enable`) as the last line of defence for documents. Any RCE
or SSRF in the backend — `pymupdf` parses attacker-supplied PDFs in-process
(`documents.py:102-115`) — escalates straight to "delete every document and every
version of it". The backup CronJob shares the same key.

**Fix.** Create a MinIO service account scoped to `tinycrm-documents` with
`s3:GetObject`/`PutObject`/`DeleteObject` and no `DeleteObjectVersion` or admin
actions, and give the backend that. Keep root in the chart only for the bucket-init
Job. Give the backup job a separate read-only key.

## 6. The container runs as root, with no pod hardening — **Medium**

`backend/Dockerfile` has no `USER` directive, so uvicorn runs as uid 0.
`charts/tinycrm/templates/backend.yaml` sets no `securityContext` at all — no
`runAsNonRoot`, no `readOnlyRootFilesystem`, no `allowPrivilegeEscalation: false`,
no `capabilities.drop`. (The MinIO StatefulSet does at least set `fsGroup`.) There
is no `NetworkPolicy` anywhere in the chart, so any pod in the cluster can reach
Postgres, MinIO and the backend directly.

**Impact.** Removes the second line of defence behind everything else in this
report: a bug in `pymupdf` or any dependency lands as root in a writable container
with unrestricted egress.

**Fix.** Add a non-root user in the Dockerfile and run as it. On the pod: `runAsNonRoot: true`,
`runAsUser`, `allowPrivilegeEscalation: false`, `capabilities: {drop: [ALL]}`,
`seccompProfile: {type: RuntimeDefault}`, and `readOnlyRootFilesystem: true` with
an `emptyDir` for `/tmp` (needed for the upload spool). Add NetworkPolicies so
only the backend reaches Postgres and MinIO.

## 7. `Content-Disposition` is built from the raw document title — **Low**

`app/routers/documents.py:257-263`:

```python
safe_title = doc.title.replace('"', "").replace("\\", "")
... headers={"Content-Disposition": f'attachment; filename="{safe_title}.{ext}"'}
```

Quotes and backslashes are stripped; CR, LF and non-Latin-1 characters are not.

**Verified.** Against real uvicorn:

- A title containing CRLF produces `RuntimeError: Invalid HTTP header value` and
  the connection is dropped with no response. uvicorn's own header validation is
  what stops this from being response splitting — the sanitiser does not.
- A title with any non-Latin-1 character raises
  `UnicodeEncodeError: 'latin-1' codec can't encode …` inside Starlette. The
  upload succeeds (201); the download then returns 500 **every time**:

```
POST /documents/ title="日本語レポート"      -> 201
GET  /documents/{id}/content                -> 500
```

**Impact.** The header-injection half is defence-in-depth only on this stack, but
it depends on a server behaviour rather than on the code. The Unicode half is a
live availability bug: any document titled in Japanese, Chinese, Cyrillic, Greek
or with an emoji can be uploaded and then never downloaded.

**Fix.** Use RFC 6266: an ASCII-only `filename` fallback plus
`filename*=UTF-8''<percent-encoded>`. Starlette will build both correctly if the
value is encoded first; strip control characters rather than only quotes.

## 8. `tags` is parsed outside the error handler and never type-checked — **Low**

`app/routers/documents.py:178`:

```python
parsed_tags: list[str] = json.loads(tags) if tags else []
```

The `try/except (ValueError, TypeError)` on the following line covers the link
lists, not this. And the annotation is a claim, not a check — nothing verifies the
parsed value is a list of strings.

**Verified.**

```
tags='{'            -> uncaught JSONDecodeError  -> 500
tags='[{"a": 1}]'   -> uncaught asyncpg DataError -> 500
tags='"notalist"'   -> 201, a bare string written into the text[] column
```

**Impact.** 500s where a 422 belongs, with stack traces in the logs, and one path
that quietly corrupts the row. Not a privilege issue; it is the only place in the
backend where caller input reaches the database without validation.

**Fix.** Move the `json.loads` inside the existing `try`, and validate the result
with a Pydantic `TypeAdapter(list[str])` (with a `max_length`, per finding 4).

## 9. Login throttling is per-IP, in-process, and resets on redeploy — **Low**

`app/ratelimit.py` is honest about its own limits in the module docstring, and
they are real: a module-level dict that only works because the Dockerfile runs a
single worker, a window that resets on every redeploy, and no per-account backoff
(tracked as T34 in `PLAN.md`). An attacker rotating source addresses walks
through it.

One related note: `FORWARDED_ALLOW_IPS` is set to the whole pod CIDR
(`10.42.0.0/16`). That is correct for reading Traefik's `X-Forwarded-For`, and I
confirmed that uvicorn 0.52's middleware walks the header right-to-left and
returns the rightmost *untrusted* entry — so an external client **cannot** spoof
its way into another bucket by prepending a value. A pod inside the cluster can,
which is one more reason for the NetworkPolicy in finding 6.

**Fix.** The durable per-account backoff already planned (T34), stored in
Postgres so it survives a redeploy and covers every worker.

## 10. Watch URLs are unvalidated and become links in the Slack briefing — **Low**

`app/schemas/watch.py:17` types the field as a bare `str` with no scheme check,
and `app/briefing.py:193-196` renders it as a Slack link. `_link` escapes `|` and
`>`, so the link cannot break out of the `<url|label>` syntax, but the scheme
itself is whatever was stored.

**Impact.** Small on a single-operator instance — the operator is the only one who
can store a URL and the only one who reads the briefing. It becomes a stored
phishing vector the moment a second user or a shared channel exists.

**Fix.** Validate with `HttpUrl` (or a scheme allowlist of `http`/`https`) on
`WatchCreate.url` and `WatchUpdate.url`.

## 11. `/docs`, `/openapi.json` and `/version` are unauthenticated — **Low**

`FastAPI(...)` in `app/main.py:74` leaves the doc routes on their defaults, so
`/docs`, `/redoc` and `/openapi.json` are public. `/version` returns the exact git
commit of the running build, and `/health` reports database state.

**Impact.** Information disclosure only: a complete map of the API, and a commit
SHA that pins exactly which dependency versions are deployed. Useful to an
attacker, harmless on its own.

**Fix.** `docs_url=None, redoc_url=None, openapi_url=None` when
`settings.environment is Environment.production`, or put them behind the same
auth dependency. Consider dropping the commit from `/version`'s public response
(the liveness probe does not read the body).

## 12. `create_admin.py` takes the password as an argument — **Low**

`backend/scripts/create_admin.py:50` reads the password from `sys.argv[2]`, so it
lands in shell history and is visible in `ps` to every user on the machine for the
lifetime of the process.

**Fix.** Read it from `getpass.getpass()` or an environment variable.

---

## What holds up well

Worth recording, because these are the parts that would have produced the serious
findings in a codebase of this shape:

- **Tenant isolation is systematic and tested.** Every router re-checks
  `user_id` on every read, write and delete; every many-to-many id list goes
  through `app/links.py:load_scoped`, which 404s on an id the caller does not own
  rather than silently dropping it; and `tests/test_cross_user_isolation.py`
  walks every resource through the same Alice/Bob script. I found no IDOR, and no
  route that trusts a foreign key without checking ownership first.
- **No SQL injection.** Every query is SQLAlchemy Core/ORM with bound parameters.
  The single `text()` call is a literal `SELECT 1`. No `eval`, `exec`,
  `subprocess`, `pickle` or `yaml.load` anywhere in the app.
- **The insecure-default guard is the right design.** `Settings.insecure_defaults()`
  plus `check_secure_defaults()` refuses to boot in production on the placeholder
  JWT secret, wildcard CORS or the `minioadmin` demo credentials — and the chart
  fails rendering on them too. That is a whole class of deployment mistake closed
  at two layers.
- **No secrets in the repository.** Credentials come from the cluster Secret;
  `.env.example` ships placeholders only; `DB_ECHO` defaults off with a comment
  explaining that it would log contact data.
- **Supply chain.** Images are digest-pinned, GitHub Actions are pinned to
  commit SHAs, `uv sync --frozen` builds from the lockfile, workflow permissions
  are least-privilege per job, the trigger is `pull_request` (not
  `pull_request_target`), and image pushes are gated on
  `head.repo.full_name == github.repository` so a fork PR cannot publish.
- **Proxy headers are handled correctly**, as confirmed above — the rate-limit
  bucket cannot be spoofed from outside the cluster.

## Suggested order of work

1. Finding 1 and 2 together — they are one attack chain, and both are small
   changes in `app/main.py` and `app/auth/users.py`.
2. Finding 3 — the ingress body cap is a few lines of chart and is the only
   unauthenticated finding here.
3. Findings 5 and 6 — deployment hardening, no application changes.
4. Findings 4, 7 and 8 — input validation and the download header; findings 7
   and 8 are also live 500s, so they pay for themselves outside of security.
5. Findings 9-12 as they fit.
