# tinyCRM — Features

A single-operator CRM for self-employment: contacts, organizations, deals,
tasks, interactions, projects, documents and a watch list of sources to sweep.

FastAPI + PostgreSQL + S3 on the back, Flutter web on the front. Every row is
scoped to a `user_id` and every endpoint checks it — there are no teams, roles
or per-record permissions. Interactive API docs live at `/docs`.

Planned work is in [GitHub Issues](https://github.com/Niecke/tiny-crm/issues);
scope and conventions are in [CONTRIBUTING.md](CONTRIBUTING.md); how to run and
deploy it is in
[README.md](README.md) and [deploy/README.md](deploy/README.md).

---

## Entities at a glance

| Entity | What it is | Links to |
|---|---|---|
| **Contact** | A person. Address book + the fields that decide whether an approach is worth making. | organization (FK), interactions, projects, documents, tasks, deals |
| **Organization** | A company. Where a switchboard number and `office@` address belong. | contacts (FK), deals, interactions, documents, watches |
| **Deal** | An opportunity, from first sniff to finished engagement. | contact + organization (FK), interactions, documents, tasks |
| **Task** | A to-do, optionally repeating. | contact, deal, interaction (FKs), projects |
| **Interaction** | One touchpoint: call, meeting, email, note. Past = log, future = plan. | contacts, organizations, deals, projects |
| **Project** | A named piece of work with a start and end. | contacts, tasks, documents, interactions |
| **Document** | A file in S3 with metadata and a preview. | contacts, organizations, deals, projects |
| **Capture** | A name or a link parked in seconds, waiting to be worked into a lead. | contact + deal (FK, once worked) |
| **Watch** | A source you check on a cadence: job board, careers page, tender portal. | organization (FK), watch checks |
| **WatchCheck** | One append-only sweep of one watch. | watch, created deal / task |

---

## Contacts

`GET|POST /contacts/` · `GET|PATCH|DELETE /contacts/{id}`

**Fields.** name, job_title, organization_id · email, email_secondary, phone,
phone_secondary, website · street, postal_code, city, country · birthday,
preferred_language · lifecycle_status, relation_type, source ·
known_day_rate + rate_currency, works_with_freelancers · tags, notes.

**Two axes, not one.** `relation_type` (`customer` / `partner` /
`subcontracting_target` / `contracting_authority`) is *what this party is to
me*; `lifecycle_status` (`lead` / `prospect` / `customer` / `former`) is *how
far along we are*. They filter together, so "partners we have not approached
yet" is one request — the row a single collapsed column would lose.

**`works_with_freelancers` is tri-state.** `true` / `false` / `null` = never
asked. `?works_with_freelancers=unknown` is the list that produces the next
approach; the UI shows "never asked" as grey, not red.

**Rate is a pair.** `known_day_rate` and `rate_currency` are refused half-way
in either direction, checked against the *merged* row on PATCH. Money is
`Numeric(14,2)` and a decimal string over the wire, never a float.

**Codes are normalised.** `country` is ISO 3166-1 alpha-2 upper-cased,
`preferred_language` ISO 639-1 lower-cased, so a filter cannot split "AT",
"at" and "Austria" into three countries.

**Filters.** `?search` (name) · `?organization_id` · `?lifecycle_status` ·
`?relation_type` · `?source` · `?country` · `?works_with_freelancers=yes|no|unknown`.
An unknown filter value is a 422, never silently ignored.

---

## Organizations

`GET|POST /organizations/` · `GET|PATCH|DELETE /organizations/{id}`

name, domain, email, phone, address, industry, notes. `?search` matches name
**or** domain — an email signature often gives the domain and nothing else.
Reads carry `contact_count`, computed as one correlated subquery on the list
query rather than a request per row.

`email` and `phone` here are the *company's* (`info@`, the switchboard), not a
person's. Deleting an organization is `SET NULL` on its contacts: losing the
company must never delete the people who worked there.

---

## Deals

`GET|POST /deals/` · `GET|PATCH|DELETE /deals/{id}` · `POST /deals/{id}/stage`

**Stages.** `draft → lead → qualified → proposal → negotiation → won →
running → completed`, plus `lost`. Won ≠ finished: a long engagement stays on
the board the day the work starts.

**A draft is open, but not in play** (#255). `draft` is the research and the
letter before anything is sent; moving it to `lead` says it went out, and
starts the clock a lead is chased by. A draft is on the board and in
`?status=open`, and is left out of everything that counts or chases the
pipeline: `?stalled`, `?overdue`, the briefing's stalled and overdue deals, and
the dashboard's pipeline, velocity and attention figures. A new deal still
starts at `lead` unless `draft` is asked for.

**`?status=` is the coarse question** the UI actually asks — `open` (not
decided yet: drafts and what is still being competed for), `active` (on my
plate, the default, includes won and running), `won`, `finished`. `?stage=`
filters one exact column.

**Value is not one number.** `value_type` picks the shape:

| value_type | fields used |
|---|---|
| `fixed` | `fixed_value` |
| `rate_based` / `retainer` | `rate` + `rate_unit`, optional `estimated_volume` + `volume_unit` |

A row priced two ways at once is refused; a quantity with no unit is refused.
Switching `value_type` on a PATCH drops the other shape's fields — that is a
re-pricing, not a contradiction.

**`expected_value` is a stored generated column**, so it cannot drift from what
it derives from. It is **NULL, never 0**, when no total exists: open-ended
deals must not be summed in as zeros. **Units are never converted** — a day
rate against a volume in months derives nothing rather than inventing a factor.

**A stage is not a label.** `apply_stage()` is the one code path (both the
stage endpoint and PATCH route through it): arriving in a decided stage stamps
`closed_at`, pins `probability` to 100 or 0, and decides whether `lost_reason`
may exist. Sending a `lost_reason` with any stage but `lost` is a 422; one
already stored on a deal being won or reopened is cleared. Deals created from a
capture or a watch sweep go through it too.

**Stage history.** `stage_changed_at` is when the deal entered its current
stage, stamped **only when the stage actually changes** — a PATCH of the title
does not reset the clock. Every move, including creation (`from_stage` NULL),
appends a row to `deal_stage_events` (`from_stage`, `to_stage`, `changed_at`,
`lost_reason`); moving back adds a row rather than editing one, and deleting a
deal cascades to its events. Deals that predate this carry `created_at` as
their `stage_changed_at` — a floor, not the real move — and have no events.

**Ordering.** Expected close date ascending, **NULLs last** — an undated deal
is not urgent. `?sort=stage_changed_at` puts the longest-waiting deal first.

**Filters.** `?search` (title) · `?stage` · `?status` · `?contact_id` ·
`?organization_id` · `?stalled=true` (in play, no next step) · `?overdue=true`
(in play, `expected_close_date` before today — today in `BRIEFING_TIMEZONE`, as
the briefing has it).

---

## Tasks

`GET|POST /tasks/` · `GET|PATCH|DELETE /tasks/{id}`

title, description (markdown), due_date, priority 0–2, done, tags. Reads carry
`completed_at`: stamped by the server when `done` turns true, cleared when it
turns back, and left alone by any other edit.

**Three independent links** — `contact_id`, `deal_id`, `interaction_id`, all
nullable and orthogonal. Reads carry `contact_name` / `deal_title` /
`interaction_subject` so a list says what each task is about without a request
per row. `?contact_id=` / `?deal_id=` / `?interaction_id=` answer "what do I
owe this record?". All three are `SET NULL`: deleting the person does not
silently drop the work.

**Recurrence.** `recurrence_rule` (`daily` / `weekly` / `monthly` / `yearly`),
`recurrence_interval`, `recurrence_until` (inclusive), `recurrence_parent_id`.
Deliberately not RRULE — a closed set the UI renders as a dropdown.

Completing a recurring task **creates the next instance and leaves the current
one done**, so "did I actually check in March?" stays answerable. The next due
date is computed from the *completion*, not the missed slot: finishing on time
keeps the cadence, finishing late re-anchors, so an overdue task yields exactly
one instance instead of a backlog. Month steps clamp to short months
(31 Jan + 1 month = 28/29 Feb) and the time of day is preserved. The successor
inherits description, priority, tags, project links and all three record links.

The PATCH response is `TaskCompletionRead` — it carries `next_occurrence` only
when the server actually created one, so the UI never guesses.

**Filters.** `?search` (title) · `?include_done` · the three link filters.
Ordering is due date ascending NULLs last, so overdue floats to the top.

---

## Interactions

`GET|POST /interactions/` · `GET|PATCH|DELETE /interactions/{id}`

kind (`call` / `meeting` / `email` / `note` / `other`), subject, notes,
`occurred_at`, `duration_minutes`, `done`, tags.

**`occurred_at` does double duty**: past = activity log, future = planned mail
or meeting, `done` closes the loop. One table serves both history and calendar.
`?upcoming=true` returns planned entries oldest-first (next appointment on
top); `?upcoming=false` the past log newest-first.

Attaches many-to-many to **contacts, organizations, deals and projects**.

**Filters.** `?search` (subject) · `?kind` · `?upcoming` · `?contact_id` ·
`?organization_id` · `?deal_id` · `?project_id`.

---

## Projects

`GET|POST /projects/` · `GET|PATCH|DELETE /projects/{id}`

name, description, start_date, end_date. M2M with contacts, tasks, documents;
interactions attach to it. `?search` on name.

---

## Documents

`GET|POST /documents/` · `GET|PATCH|DELETE /documents/{id}` ·
`GET /documents/{id}/content` · `PUT /documents/{id}/content` ·
`GET /documents/{id}/preview`

title, description, format (`pdf` / `markdown` / `txt`), size, storage_key,
preview_key, tags. **25 MB cap**, enforced from the recorded content length
*before* anything is read; the body then streams to S3 (multipart past 8 MB),
never one blob in memory. PDFs get a JPEG first-page preview — the one place
the whole file is materialised, because pymupdf needs it, and bounded by the
cap.

**Links are resolved before the body reaches S3.** The other order would leave
an object in the bucket with no row that could ever delete it. Multipart has no
list type, so link lists arrive as JSON arrays in form fields like `tags`; a
malformed one is a 422.

Attaches many-to-many to **contacts, organizations, deals and projects** — one
framework agreement covers two deals, and the same NDA is filed against both
the person and their company without being uploaded twice.

**Filters.** `?search` (title) · `?contact_id` · `?organization_id` ·
`?deal_id` · `?project_id`. Two at once narrow rather than widen.

---

## Captures — the inbox

`GET|POST /captures/` · `GET /captures/count` · `GET|PATCH|DELETE /captures/{id}`
· `POST /captures/{id}/convert` · `POST /captures/{id}/dismiss`

Somewhere to put a person in two seconds, before there is time to decide
anything about them. `raw` (required) is the one line that was typed, pasted or
shared; `name` and `url` are pulled out of it by `app/captures.py`; `note`,
`source` and the triage links are the rest.

**A table of its own, not a half-filled contact.** A `Contact` needs a name and
rewards a dozen more fields, so a bare profile URL could not be filed as one
without inventing a name for it. Worse, the filters that make the contact list
useful — `lifecycle_status`, `works_with_freelancers` — read as "never asked" on
a stub, which is indistinguishable from a real answer.

**`raw` is never rewritten.** That is what makes the parser safe to get wrong:
the name and the link are guesses, editable and occasionally nonsense, but what
was actually in hand at the moment of capture survives all of it. Editing a
capture later does not re-run the parser either — by then the name on the row is
the corrected one.

**What the parser does**, in order: lift the first `http(s)` token out as the
url; whatever text is left becomes the name, in either order; if nothing is
left and the link is a `linkedin.com/in/` or `xing.com/profile/` slug, title-case
it into a suggested name, dropping a trailing id; no link at all and the whole
line is the name. A slug from any other host yields no name — an honest blank
beats a confident guess at a person's name.

**Status is one column** — `new` / `converted` / `dismissed` — and moves only
through `/convert` and `/dismiss`, never through PATCH. The same funnel
`Deal.stage` has, so arriving at an ending always stamps what that ending
implies. `triaged_at` is a timestamp beside it, not a second source of truth.

**`POST /{id}/convert` is one transaction**: the person (a new contact at
`lifecycle_status: lead`, or an existing `contact_id` — exactly one, else 422),
optionally a deal at stage `lead` against them, and optionally the interaction
recording that they were written to. The four belong together: a contact created
without its deal is a name nobody follows up, and a deal created without the
capture being stamped comes straight back in tomorrow's inbox. The response
carries all four so the triage screen can advance without a second request.

**Converting twice is a 409**, not a second deal. That is the quiet duplicate
that only surfaces when you write to someone for the second time. A refused
convert leaves the capture `new`, never half-worked.

**Dismissing keeps the row.** "I looked at this and said no" is an answer, and an
inbox that forgets its own rejections offers them again next month. `DELETE` is
for a typo, which is not a decision — it is what Undo in the quick-add box calls.
A capture still `new` is the one record that can be deleted without archiving it
first (see Archive instead of delete): nothing has been made of it and nothing
points at it. Once worked, it is erased like everything else.

**Oldest first**, always: an inbox is a queue to empty, not a feed to scroll, and
newest-first would bury exactly the captures going stale. `?status=all` widens
the list to what has already been worked; `?search=` matches `raw` as well as
`name`, because half the rows have no name to be found by.

**No unique constraint on anything.** The same person may well be captured twice
from two places, and refusing the second at the moment of capture is the opposite
of frictionless. De-duplication belongs at triage (#141).

---

## Watches — job boards, careers pages, tender portals

`GET|POST /watches/` · `GET|PATCH|DELETE /watches/{id}` ·
`POST /watches/{id}/check` · `GET /watches/{id}/checks`

The recurring sweep that finds work *before* there is a conversation to record.
name, url (required — a source you cannot open is not a source), kind
(`job_board` / `careers_page` / `tender_portal` / `other`), `query_note` (the
saved search in words: keywords, CPV codes, region), notes, active, optional
`organization_id`.

**Cadence reuses the task recurrence engine** (`app/recurrence.py`), not the
task table — one task per watch would put twenty identical "check X" rows in
the dashboard and bury the one real follow-up. `last_checked_at` and
`next_due_at` are stamped together by the check endpoint and nowhere else.

**The anchor differs by caller.** Logging a sweep anchors on the *scheduled*
date, keeping the rhythm; changing the cadence anchors on the *last sweep*,
because `next_due_at` by then holds a date the old rule produced. Editing the
cadence of a never-swept source leaves it due.

**`POST /{id}/check` is one transaction**: it logs the sweep, advances the
cadence, and optionally creates a deal or a task from the find. Outcome is
`nothing` or `found`; `create_deal` / `create_task` with `outcome: "nothing"`
is a 422. A refused find leaves no check, no deal and an unmoved cadence.

**"Nothing found" is a valuable answer** — it is what makes a year of diligence
on a quiet portal provable. `found_count` / `check_count` on every read answer
what a single timestamp cannot: has this source ever produced anything?
Checks CASCADE from the watch; what a find produced is `SET NULL`, so deleting
the deal does not erase the record of having found it.

**Filters.** `?due` · `?active` · `?kind` · `?search` · `?organization_id`.
Ordering is most-overdue-first, paused sources last.

**Paused is not archived.** `active=false` stops a source being due and keeps it
on the list, waiting to be switched back on. Archiving takes it off the list as
well, and an archived source cannot be swept.

---

## Search — one box over everything

`GET /search/?q=` looks through contacts, organizations, deals, tasks,
interactions, projects, documents, watches and captures at once (#126), and
answers with one group per type: the best few hits and how many there are.
`?type=` with `skip`/`limit` pages through one type. A query needs at least
two characters: one matches most of every table and no index helps it look.

- **Every column, not just the name.** Each table has a search document, its
  text columns joined (`app/models/search.py`): a contact by email, phone,
  job title, address, notes or tag; a capture by its raw line, link or note,
  whatever its status. Phone numbers are also held digits-only, so "664123"
  finds "+43 664 123 45 67".
- **Substring, every term.** Each word typed must appear somewhere in the
  row (`ILIKE '%term%'`, wildcards escaped), so "anna acme" narrows rather
  than widens. Titles starting with the query rank first, then by
  `pg_trgm` word similarity.
- **Trigram GIN indexes**, one per table over the same expression the query
  uses, so the match stays an index scan as the tables grow.
- **Why it matched.** A hit whose title does not show the query says where it
  did — `Phone: +43 664 …`, `Notes: …met at the Vienna…`.
- **Nothing archived.** An archived record is not found, and there is no switch
  to find it: each list has its own archive, and that is where to look.

In the app, the box sits above every page. Typing lists the top hits per type;
picking one opens it, and Enter (or "See all results") opens `/search?q=`.

---

## Archive instead of delete

Every record type — contact, organization, deal, task, interaction, project,
document, watch, capture — is put away rather than removed (#140).
`POST /{type}/{id}/archive` stamps `archived_at`; `POST /{type}/{id}/restore`
clears it. Both can be repeated without harm, and archiving twice keeps the
first date.

**What archived means**, the same for all nine (`app/archive.py`):

- **Out of everything that lists or counts.** Every list, the search, the
  morning briefing and every dashboard number leave it out. `?archived=true` on
  a list returns the archive *instead* — never the two mixed, so no row has to
  say which it is.
- **Still there by its id.** `GET /{type}/{id}` answers as before, with
  `archived_at` set. That is the point: an interaction with an archived contact
  still names them, where a delete left it naming nobody.
- **Read-only.** Any change — `PATCH`, a deal's stage, a watch's sweep, working
  a capture, replacing a document's file — is a **409** until it is restored. A
  document's file stays readable and downloadable.
- **Nothing cascades.** Archiving a company leaves its people on the contact
  list, still filed under it; archiving a contact leaves their tasks open.
  Those are separate decisions.

Two consequences worth knowing: an organization's `contact_count` counts only
contacts that are not archived, so the number matches the list it links to; and
an archived task or planned interaction is no longer a deal's next step, so the
deal can show up as stalled.

**Archiving is not erasing.** `DELETE` still removes the row for good, exactly
as before — links become `SET NULL` or lose their join row — and it is the
erase path for #143. It answers **409 unless the record was archived first**:
two steps, because it is the one that cannot be undone. The exception is a
capture nobody has worked yet (Captures, above). There is no automatic purge of
the archive; a retention period is #143's to decide.

In the app, a record page offers **Archive** where Delete used to be. An
archived record shows a notice with **Restore** and **Delete permanently** in
place of its edit controls, and each list has an **Archived** switch (a fourth
tab in the inbox).

---

## Change history

Every record used to keep only `updated_at`: nothing said who changed what, and
two tabs editing the same contact silently kept whichever saved last (#142).

**Every save is recorded.** `audit_events` is append-only: one row per write
that changed something, holding only the fields that differ, as
`{field: {old, new}}`. The diff is taken from the row, not the request — the
edit forms send every field on every save, and a change the server makes
alongside (a won deal pinning its probability, a cleared rate taking its
currency) belongs in the record too. A save that changes nothing leaves no
entry. Archive and restore are entries of their own. Link lists
(`contact_ids`, …) are diffed like fields. Amounts stay strings and dates
ISO 8601, as everywhere else in the API.

**Read it back** with `GET /history/{entity_type}/{entity_id}` — newest first,
paged, 404 for a record that is not the caller's. It feeds the field-change
entries of the unified timeline (T15). Each entry names its `actor_id`; with
one user per tenant that is the owner, and a second user (T25) needs no
migration.

**Stale saves are refused.** Every record carries a `version` that goes up by
one on every write. A PATCH that sends the `version` it was edited from gets
**409** if someone else saved in between, instead of overwriting them. The
check is also in the UPDATE itself (`WHERE version = …`), so two saves racing
each other cannot both win. `version` is optional: a one-field toggle like
"done" sends none, and the newest value wins as before. The edit forms send the
version they were opened from — not the one a background refetch brought in —
and answer a 409 with **Load latest version**, which discards the edits.

**Erasing erases the history.** `DELETE` removes the record's entries with it:
a log that kept every old address of a contact who asked to be forgotten would
be the copy that was not erased (#143). Nothing was backfilled — the past was
never recorded.

---

## Cross-cutting rules

**Tenant scoping.** Every list, read, write and link is filtered by
`user_id`. Every `*_id` a client sends is validated against the caller's own
rows before it is stored — a foreign key alone would accept another tenant's
id, and since reads send the linked record's *name* back out, that would be a
data leak rather than untidy data. A miss is a **404, not a silent drop**.
`tests/test_cross_user_isolation.py` is table-driven; adding a router means
adding one row.

**Pagination.** Every list returns `Page[T]` — `items`, `total`, `skip`,
`limit` — with `limit` validated `1..200`. Every list has a **stable sort with
an `id` tiebreaker**: paging over a non-unique order lets rows repeat or vanish
between pages. The UI shows "1–25 of 213" and hides the bar when everything
fits. Pickers deliberately use `listAll()` (walking pages at `limit=200`)
because a truncated picker is the same silent bug in a smaller box.

**Deletes preserve history — detached.** Every link between records is
`SET NULL` or drops only the join row. Deleting a company keeps its people;
deleting a contact keeps the tasks, documents and sweep logs, with nobody on
them. Keeping the name on them as well is what archiving is for, and a delete
is only allowed after it (Archive instead of delete).

**Money never becomes a float.** `Numeric` in Postgres, a JSON string over the
wire, a string end to end in Dart (`core/money_text.dart`).

**Errors are one actionable sentence.** `core/error_text.dart` maps a failure
to readable text (transport vs. status, `Retry-After` on 429, the server's own
`detail` including FastAPI's validation list). `ErrorInterceptor` in `api.dart`
re-throws anything from 400 up, because `validateStatus` accepts every status
so the 401 handler can see one. Every delete goes through the same
`confirmDelete()` dialog.

---

## Screens

| Route | What it does |
|---|---|
| `/` | Dashboard: four headline numbers from `GET /metrics/dashboard` (open pipeline and committed work per currency with their open-ended counts, deals won this quarter, stalled and overdue deals), each linking to the page that explains it, above today's tasks and plans from `GET /briefing` and the waiting queues; new deals per week for the last ten weeks run across the full width between the two. Task titles and interaction subjects link to their pages. The numbers fail on their own: today's list never waits for them. |
| `/numbers` | The dashboard's aggregates from `GET /metrics/dashboard`, with a Week / Month / Quarter / Year switch (`?period=`). One panel per question in DASHBOARD.md, each marked "Now" or the period. Attention counts link to the list behind them (`/deals` scoped "No next step" or "Past expected close", the inbox, today's briefing). Anything not measurable yet is a dashed skeleton naming the issue it waits on, never a zero. |
| `/search` | Every type's hits for `?q=`, ten each, with "Show all" paging through one type. |
| `/inbox` | The inbox: captures oldest-first beside a triage panel. **Open link** opens the profile in a new tab; one form files the person, opens a deal at stage Lead and logs that you wrote to them, then advances to the next capture. Nav badge counts what is waiting. |
| `/capture` | Where Android's share sheet lands. Saves what was shared, then offers "Add another" or the inbox. Outside the app shell — arrived at from outside, not navigated to. |
| `/watches` | Sources: "Due now" / "All active" / "Everything", filter by kind. **Open & sweep** opens the source in a new tab, then offers the check dialog. Nav badge counts what is due. |
| `/deals` | List beside detail, scoped "On my plate" / "Still competing" / "No next step" / "Past expected close" / "Won" / "Finished" / one stage. Detail moves the deal with stage chips. |
| `/organizations` | List beside detail: contacts at the company, add-someone-here, attached documents and interactions. |
| `/projects` | Project list and detail with its contacts, tasks, documents and interactions. |
| `/documents` | Upload, pdfrx viewer, markdown render, replace content, attach anywhere. |
| `/interactions` | "Planned" vs. "Activity log". "Follow up" on a tile creates a task carrying the interaction and the person. |
| `/account`, `/account/password`, `/health`, `/login` | Profile, password change, health, sign-in. |

Contact detail is a pushed page: fields, chips for status / type / freelancer,
the address as an envelope, that contact's interactions, documents and open
tasks. A background version check prompts a reload when the deployed build hash
changes.

The **quick capture** bolt sits in the app bar in both the wide and the narrow
layout, because the whole feature is worth nothing if putting something in is
ever more than one tap away. One autofocused field: Enter saves and clears while
keeping focus, so several go in without leaving the dialog, and each saved line
can be undone on the spot. A failed save leaves the text where it is.

Shared widgets worth knowing: `RecordPicker` / `AttachmentPickers` (the four
attach pickers used by every form), `LinkedTasksSection`, `PaginationBar`,
`AttachedDocumentsSection`, `AttachedInteractionsSection`, `QuickCaptureButton`.

---

## The morning briefing

Weekday mornings, 07:00, one Slack message: overdue tasks, what is due today,
today's planned interactions, planned interactions never confirmed, the sources
due to be swept, the people still waiting to be written to, the deals with no
next step, and the deals past their expected close date.

`app/briefing.py` gathers and renders, `scripts/send_briefing.py` runs it,
`charts/tinycrm/templates/briefing-cronjob.yaml` schedules it on the backend
image. **No scheduler inside the API** — an in-process loop fires once per
replica, and a delivery that quietly stops looks exactly like a quiet week. A
Job fails visibly. `startingDeadlineSeconds` skips a missed slot rather than
queueing yesterday's briefing on top of this morning's.

**The day boundary is the operator's, not UTC.** Task due dates are filed as
23:59 local, which is 21:59Z in summer, so a UTC "today" puts a task due
tonight in tomorrow's message. `DayWindow` is local midnight to local midnight
— 23 or 25 hours long across a DST switch — and `days_late` counts calendar
days. `BRIEFING_TIMEZONE` must equal the CronJob's `timeZone`; the chart sets
both from `briefing.timeZone`, on the backend Deployment as well as the CronJob.

Watches appear as "due today", not "due now": a source due at 15:00 belongs in
the 07:00 message. Paused sources never appear.

**Waiting captures have no date filter**, unlike everything else in the message
— a capture has no due date, which is precisely why it needs to be here. Nothing
else in the app would ever surface one, so an inbox nobody opens stays invisible
until the names in it are cold. Each line carries how long it has waited, which
is the part that means something: "3 waiting" is a healthy inbox on a Tuesday
and a broken habit if the oldest is from March.

**Deals past their expected close date** (#117) are the rows of
`GET /deals/?overdue=true`, furthest past first: in play, with an
`expected_close_date` before today. One predicate (`overdue_on`) and one query
(`briefing_queries().overdue_deals`) serve the message, `GET /briefing`, and the
dashboard's count. A deal can be listed here and under "no next step" at once —
one asks whether anybody is working it, the other whether its forecast still
holds.

```bash
cd backend
uv run python scripts/send_briefing.py --dry-run   # print it, send nothing
uv run python scripts/send_briefing.py             # needs SLACK_WEBHOOK_URL
```

Off by default in the chart (`briefing.enabled`): a CronJob that fails every
morning is worse than none.

**The same briefing, as data: `GET /briefing`.** The React dashboard's "Today"
section renders it rather than assembling the day from the list endpoints —
those have no due-date or confirmation filters, and would need their own idea
of where today starts. Every list is complete (the Slack message caps its
sections), and each item carries the day count the briefing computed in
`BRIEFING_TIMEZONE`, so the page and the 07:00 message cannot disagree about
what is late. `app/routers/briefing.py`; the clock is a dependency
(`current_time`) so tests pin it.

---

## Dashboard numbers

`GET /metrics/dashboard?period=quarter` — `week` · `month` · `quarter` ·
`year`, the calendar one containing today in `BRIEFING_TIMEZONE`, echoed back
resolved. One response, one model per group from [DASHBOARD.md](DASHBOARD.md)
(#138); `app/metrics.py` holds the queries, each one grouped aggregate.

| Group | Now / period | What |
|---|---|---|
| `pipeline` (A) | now | deals in play (`lead` to `negotiation`, never `draft`) per stage and currency: count, value, open-ended count; won + running per currency |
| `velocity` (B) | both | per stage in play the median calendar days in stage and the oldest deal; deals entering each stage in the period (`draft` included); all-time conversion to a later stage; median days from opening to first win for deals won in the period |
| `outcomes` (C) | period | deals decided in the period — moved into won or into lost — as they stand now, per currency: count, value, open-ended count; win rate by count across currencies and by value per currency, null when nothing was decided |
| `attention` (D) | now | stalled deals, overdue deals, overdue tasks, unconfirmed interactions, waiting captures (with the oldest's age), each with the list request behind it |
| `activity` (E) | period | interactions that happened, by kind; deals opened; captures converted and dismissed; tasks created and tasks completed |
| `trends` | last 10 weeks | deals opened per ISO week in local time, oldest first, zeros included; the running week is marked `complete: false` |

**Money is a pair and never crosses currencies:** every amount is a `Decimal`
string beside the count of deals with no derivable amount, grouped by
currency. **A group that cannot be computed yet is absent, not zero** —
`delivery` (F), and within the groups the weighted pipeline (#120), lost
reasons, win rate by source and revisits (#118) and reply direction (#135).
The attention counts run the briefing's own queries
(`briefing_queries`), so the two cannot disagree about what is late. **Nothing
archived is counted**, in any group: every number links to a list, and no list
shows an archived row.

---

## Auth and hardening

- **JWT bearer** via fastapi-users. No register router; accounts come from
  `python -m app.cli create-user` (`app/cli.py`), which mails an invite.
  `/auth/jwt/login`, `/auth/jwt/mfa`, `/auth/jwt/refresh`, `/auth/jwt/logout`,
  `/users/me`, `/users/me/password`, `/users/me/mfa/*`.
- **Sessions** (#133, `app/auth/sessions.py`): a login opens a row in
  `auth_sessions` and returns a 15-minute access token plus a refresh token.
  The access token names its session (`sid`), and every request checks that
  the session still exists, so ending one takes effect at once. Refresh tokens
  rotate on every use and are verified by HMAC, not stored; one replaced less
  than 60 s ago is answered with the same new pair (two tabs, a retried
  request), anything older is treated as stolen and ends the session. The
  refresh lifetime is idle time — each refresh extends it.
  **Ended by:** sign-out (`/auth/jwt/logout`, takes the refresh token, always
  204); a password change (every *other* session; the one that changed it
  stays); a password reset (all of them). Both clients renew the access token
  shortly before it expires and retry once on a 401, so a stale tab recovers
  by itself.
- **Two-factor sign-in** (#18, `app/auth/mfa.py`): TOTP from an authenticator
  app, turned on from the account page (`/users/me/mfa/setup` → scan →
  `/users/me/mfa/confirm` with the first code). With it on, a correct password
  gets a challenge (`mfa_required`, a 5-minute `mfa_token`) instead of tokens,
  and `/auth/jwt/mfa` trades that plus a code for the session. Codes are
  single-use (the matched time step is stored); wrong codes count against the
  same per-address limit and per-account backoff as wrong passwords, and the
  backoff only clears once the code is right — at sign-in and on the account
  endpoints that check a password or code. A challenge dies when the password
  is changed or reset, or MFA is turned off and on again. Ten single-use **recovery codes**
  (stored as SHA-256) are issued on setup and replaced via
  `/users/me/mfa/recovery-codes` (password). Turning it off needs password
  and code (`/users/me/mfa/disable`); turning it on or off ends every other
  session. A password reset leaves MFA on. The secret is encrypted with a key
  derived from `JWT_SECRET` — **rotating it voids every stored secret**, and
  those accounts sign in with a recovery code. Last resort:
  `python -m app.cli disable-mfa <email>`.
- **Password reset** (#128): `/auth/forgot-password` mails a link through
  Brevo (`app/mail.py`); `/auth/reset-password` redeems it. The pages are
  frontend-next only: `/next/forgot-password` (linked from sign-in) and
  `/next/reset-password#token=…` — the token in the fragment, so it never
  reaches a server log. Invites use the same
  token. Links are single-use and expire after 12 hours
  (`PASSWORD_TOKEN_LIFETIME_SECONDS`). Redeeming one marks the address verified;
  `/auth/request-verify-token` + `/auth/verify` are mounted too, but no mail
  carries a verify token.
- **Login throttle** (`app/ratelimit.py`): sliding window of *failed* logins per
  client address, `LOGIN_MAX_FAILURES` (10) per `LOGIN_FAILURE_WINDOW_SECONDS`
  (300). Over budget → 429 with `Retry-After`. Counted in middleware, because a
  dependency runs before the handler and cannot see whether the credentials were
  accepted. Every failure logs at WARNING with the source address.
  **Requires `FORWARDED_ALLOW_IPS`** wherever Caddy fronts the API, or every
  user shares one bucket — which in turn requires the backend port not to be
  publicly reachable.
- **Per-account login backoff** (`app/auth/throttle.py`, table `auth_throttle`):
  after `LOGIN_BACKOFF_FREE_FAILURES` (3) failed logins for one address, each
  further failure locks it for 2, 4, 8, … seconds up to
  `LOGIN_BACKOFF_MAX_SECONDS` (900). Locked → 429 with `Retry-After`, before
  the password is checked. Keyed by an HMAC of the typed address, so unknown
  addresses are throttled exactly like real ones and no address is stored.
  `LOGIN_BACKOFF_DECAY_SECONDS` (86400) of quiet, a successful login or a
  completed password reset clear it; so does `python -m app.cli unlock <email>`.
  `/auth/jwt/refresh` is never throttled, so signed-in devices keep working.
- **Reset-mail cooldown:** at most one password-reset mail per account per
  `PASSWORD_RESET_COOLDOWN_SECONDS` (300), failed deliveries included. Inside
  the cooldown the request still answers 202 and sends nothing.
- **Insecure-default guard.** `check_secure_defaults()` runs in the lifespan
  hook. Development warns per problem; **production logs each at ERROR and
  aborts startup with exit code 3**. Covers the placeholder JWT secret,
  `CORS_ORIGINS=["*"]` and the `minioadmin` demo S3 credentials.
  The guard is inert unless `ENVIRONMENT=production` is set.
- **SQL echo is off by default** — `echo=True` logs every statement with its
  bound parameters, i.e. contact names, emails and notes.

---

## Configuration

All via env or `backend/.env` (see `.env.example`).

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` turns the default-guard warnings into a refusal to start |
| `DATABASE_URL` | local compose | asyncpg URL |
| `DB_ECHO` | `false` | leave off — echo logs personal data |
| `CORS_ORIGINS` | `["*"]` | must be the real origin in production |
| `JWT_SECRET` | placeholder | `openssl rand -hex 32` |
| `ACCESS_TOKEN_LIFETIME_SECONDS` | 15 min | what a leaked token is good for |
| `REFRESH_TOKEN_LIFETIME_SECONDS` | 90 days | idle time: every refresh extends it |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW_SECONDS` | 10 / 300 | failed logins only |
| `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` / `S3_REGION` | Versity Gateway locally, Hetzner Object Storage in production | bucket versioning is checked at boot |
| `SLACK_WEBHOOK_URL` | unset | without it a real briefing send exits 2 |
| `BRIEFING_TIMEZONE` | `Europe/Berlin` | must match the CronJob's `timeZone` |
| `APP_URL` | unset | the "Open tinyCRM" link in the briefing |
| `GIT_COMMIT` | `unknown` | injected at image build, served by `/version` |

`GET /health` returns 200 `{status: ok, db: ok}` or **503** when the database
is unreachable. `GET /version` returns the running commit and build timestamp;
the frontend polls it to prompt a reload after a deploy.

---

## Tests

- **Backend: 396 tests** (`cd backend && uv run pytest`). A scratch Postgres
  database per session; tables rebuilt from the models before each test; two
  accounts (Alice and Bob) with sessions opened directly, skipping the password hash.
  S3 is faked in memory for document tests. `uv run mypy app tests` is clean and
  gated in CI; `ruff check` and `ruff format --check` too.
- **Frontend: 11 test files** (`cd frontend && flutter test`) covering the
  hand-written models, money and date formatting, and error text.
  `widget_test.dart` is browser-only — add `--platform chrome`.
- **`ci/smoke.sh`** drives the real built images against Postgres and the S3 fixture:
  health, matching versions, the Flutter bundle and its SPA fallback, admin
  creation, login, a 401 for anonymous requests, contact / document / deal /
  watch round-trips, and the briefing script's `--dry-run` inside the image.

---

## Build and ship

- **CI** (`.github/workflows/ci.yml`, on PR into `main`): backend tests +
  frontend tests → build and push `ci-<short-head-sha>` → integration test with
  `compose.ci.yml` and `ci/smoke.sh`. A PR comment carries pass/fail counts,
  failing test names and coverage.
- **Promote** (`.github/workflows/promote.yml`, on merge to `main`): re-tags
  the *same digest* that passed the integration test to `sha-<short-main-sha>`.
  Nothing is rebuilt, so nothing can drift between test and release. There is
  no `latest` tag, and the chart has no default image tag.
- **Deploy**: Flux, pull-based. `deploy/flux/` + `charts/tinycrm/`. Merging to
  `main` deploys to staging (`crm-staging.niecke-it.de`, namespace
  `tinycrm-staging`); production is fed by release tags (#114). No cluster
  credentials live in GitHub. Rollback is
  `helm -n tinycrm rollback tinycrm`, and a failed upgrade rolls itself back
  after three retries.
- **Migrations** run as a Helm pre-upgrade hook (and a one-shot `migrate`
  service in compose), never from the backend image's `CMD` — under a rolling
  update every starting replica would race the same migration.
- **Backups**: Hetzner server snapshots (seven rolling) plus a daily CronJob
  writing one `tiny-crm-<TS>.tar` — a brotli'd `pg_dump` plus the raw document
  objects — to Google Cloud Storage through its S3 endpoint. Restore rehearsed
  2026-09-05 into a throwaway kind cluster; procedure in the infrastructure
  repo's `scripts/niecke-it/RESTORE.md`. **A failed backup run is still
  silent** — the known gap, with a monthly freshness check as the interim.
