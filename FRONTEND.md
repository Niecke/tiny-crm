# Frontend

The React client in `frontend-next/` replaces the Flutter app in `frontend/`
([#122](https://github.com/Niecke/tiny-crm/issues/122)). It is built in
parallel, served at `/next/` on staging, and takes over in a single cutover
commit once the criteria at the end of this file are met.

This file holds the decisions — what was chosen, why, and what would make it
worth revisiting. How to run and build the app is in
[`frontend-next/README.md`](frontend-next/README.md); how it is deployed is in
[`deploy/README.md`](deploy/README.md).

## Stack

| Concern | Choice |
|---|---|
| Build | Vite, TypeScript (strict) |
| UI | React 19 |
| Components | React Aria Components, styled with our own CSS |
| Styling | Plain CSS with design tokens, `src/styles.css` |
| Routing | TanStack Router, file-based (`src/routes/`) |
| Server state | TanStack Query |
| Forms | react-hook-form + zod |
| API client | Generated from the backend's OpenAPI schema (`openapi-typescript` + `openapi-fetch`) |
| Lint | oxlint |
| Serving | Caddy, static files only, in the `frontend-next` image |

## Decisions

### Component library: React Aria Components

**Decision.** Interactive controls — buttons, text fields, search, tabs,
tables, and later dialogs, selects, comboboxes and date pickers — come from
[React Aria Components](https://react-spectrum.adobe.com/react-aria/).
React Aria is *headless*: it provides behaviour and accessibility (keyboard
navigation, focus management, ARIA roles, screen-reader announcements) and no
look. The look is ours.

**Why.**

- The hard part of a component is behaviour, not appearance. A searchable
  organization picker, a date-time picker for interactions and a multi-select
  for document links are all coming, and those are exactly the components that
  break when written by hand.
- The app already had a design — warm beige tokens, soft borders — before a
  library was chosen. A headless library keeps it; a styled one (Mantine, MUI)
  would mean theming against its look, and shadcn/ui would mean adopting
  Tailwind and restyling.
- Of the headless options, React Aria has the most complete set for this app:
  its date picker, combobox and table are built in, where Radix has none of
  the three.

**How it is used.**

- Thin wrappers live in `src/components/ui/` (`Button`, `TextField`,
  `FormTextField`, `SearchField`). Screens use the wrappers, not React Aria
  directly, when a wrapper exists; add one the second time a pattern repeats.
- Styling hooks are React Aria's `data-*` state attributes (`data-hovered`,
  `data-focus-visible`, `data-invalid`, `data-selected`, `data-empty`) and the
  ARIA attributes it sets, targeted from `src/styles.css`.
- **Navigation stays a router `<Link>`**, not a React Aria link or button.
  TanStack's `Link` is typed against the route tree, keeps search params, and
  marks the active route; a "button" that goes somewhere (New, Edit, Cancel) is
  a `Link` with `className="button"`. React Aria's `Button` is for actions.
- Forms: React Aria inputs are controlled, so they bind to react-hook-form
  through `Controller` (`FormTextField`), not `register()`. Validation stays in
  zod; React Aria only displays the result (`validationBehavior="aria"`).

**Revisit if** the app needs a large set of ready-made composite components
(data grids with editing, rich text) that would be cheaper to adopt than to
build on these primitives.

### Styling: plain CSS with tokens

One stylesheet, `src/styles.css`. Colours, spacing, radii and shadows are CSS
custom properties on `:root`; everything else refers to them. The palette is a
warm beige with a muted sage accent, chosen for long sessions: body text is
about 11:1 against the background rather than 21:1, and every text colour
still clears WCAG AA on each surface it is used on.

Structure comes from tone first and lines second: the sidebar is a darker
beige with no border, content sits in rounded panels with a hairline border,
and dividers inside a panel are inset so nothing runs edge to edge.

No Tailwind, no CSS-in-JS. At one stylesheet and one developer, the cost of
either is higher than what it buys. **Revisit if** the stylesheet grows past
the point where finding a rule is harder than writing a new one — CSS Modules
per component would be the next step.

### URL holds the view state

Anything that decides what is on screen and should survive a reload or a
shared link goes in the URL as a search param, validated with zod in the
route's `validateSearch`: the list search (`?q=`), the open tab (`?tab=`), the
login redirect. Component state is for what is genuinely transient.

A route with a redirect parameter accepts same-app paths only (starts with `/`,
not `//`), so it cannot become an open redirect.

### Server state: TanStack Query

All API data goes through the query cache. Query definitions are
`queryOptions` factories per record type (`src/auth.ts`,
`src/organizations.ts`), so a component, a route loader and a mutation that
updates the cache all use the same key. After a write: seed the detail from
the response with `setQueryData`, invalidate the lists.

A 401 anywhere drops the token and sends the user to `/login` with a redirect
back (`src/main.tsx`). Queries do not retry on 4xx.

### API client: generated from OpenAPI

**Decision.** No hand-written API types. The backend's OpenAPI schema is
exported to `frontend-next/openapi.json`, `openapi-typescript` turns it into
`src/api/schema.d.ts`, and `openapi-fetch` is the client (`src/api/client.ts`).
Paths, path and query parameters, request bodies and responses are all typed
from the schema: a misspelled path, an unknown filter or a field the backend
does not return is a compile error.

**Why.** The Flutter client's hand-written models are its biggest maintenance
cost — `ContactRead` alone has 26 fields. Generated types turn a backend change
into a compile error at every affected screen. `openapi-fetch` was chosen over
`@hey-api/openapi-ts` because it generates no runtime code to review and fits
the `queryOptions` pattern unchanged.

**How it works.**

- `npm run api:generate` in `frontend-next/` re-exports the schema
  (`backend/scripts/export_openapi.py` — imports the app, needs no database
  or environment) and regenerates the types. Both files are committed, so an
  API change is visible as a diff in the pull request that makes it.
- CI regenerates both in *Frontend next checks* and fails if they differ from
  what is committed. A backend change that alters the API has to regenerate
  the client in the same pull request.
- Calls go through `unwrap()`, which returns the typed `data` or throws an
  `ApiError` with the status and FastAPI's `detail` — TanStack Query only sees
  a failure when the promise rejects. The client's middleware adds the bearer
  token and drops it on a 401.
- The client lives in the router context (`context.api`), created once from
  the runtime `config.json`.
- `src/api/types.ts` holds short aliases for the few schemas a screen names
  explicitly (a prop, a mutation body). Query results need none: they are typed
  by the call.

**Caveat.** `openapi-typescript` 7.13 declares a peer dependency on
TypeScript 5; this project is on TypeScript 6. `package.json` has an
`overrides` entry pointing it at our TypeScript — the generator only uses the
printer API, which 6 keeps. Drop the override once a release supports 6.

### Token storage: `localStorage`

**Decision.** The JWT is stored in `localStorage` under `tinycrm.token`
(`src/token.ts`), so a login survives a closed tab, as it does in the Flutter
app.

**The risk, stated plainly.** Any script running on the origin can read
`localStorage`. The token is valid for about 270 days (T24) and there is no
refresh token or server-side revocation, so a token stolen through an XSS is
usable for months. The browser has no equivalent of Flutter's
`flutter_secure_storage`.

**Why it is still the choice for now.** The alternative that removes the
exposure — an `HttpOnly` cookie set by the backend — is a backend change
(cookie transport in fastapi-users, CSRF protection, same-site setup) and
belongs with the auth work in #147. Until then:

- the exposure is the same as the Flutter app's today, not new;
- React escapes all rendered text, and nothing uses
  `dangerouslySetInnerHTML`;
- all storage access goes through `src/token.ts`, so moving to a cookie
  touches one file on this side.

**Revisit** before the cutover: either shorten the token lifetime (T24) or
move to an `HttpOnly` cookie. A strict Content-Security-Policy on the Caddy
image is the cheap mitigation in the meantime.

### Serving: a static image at `/next`

The app is built with `base: '/next/'` and served by Caddy from
`/srv/next` in its own image (`frontend-next/Dockerfile`). Its own Deployment
in the chart, off by default and enabled only on staging, with `/next` routed
to it on the Flutter app's Ingress, so staging's basic auth and `noindex`
cover it too. Hashed assets are cached for a year; everything else
revalidates. The API URL comes from `/next/config.json`, mounted from the same
ConfigMap as the Flutter app's.

Why a separate image rather than a second directory in the Flutter image:
either app can roll, fail or be removed without the other, and the cutover is
a routing change rather than a rebuild.

## Conventions

- **Routes** in `src/routes/`; everything behind the login sits under the
  pathless `_authed` layout. A record type gets `index` (list), `new`,
  `$id/index` (detail) and `$id/edit`.
- **Record pages** share one shape: a facts column (label above value) on the
  left, linked records in tabs on the right, the tab in `?tab=`.
- **Lists** show how many rows they are not showing rather than stopping
  silently at the page limit.
- **Not built yet** is visible, not hidden: nav entries for unported screens
  are shown disabled, and actions that are not implemented are disabled
  buttons with a note saying so.

## Cutover criteria

*Proposed — to be confirmed before phase 2 starts, then not renegotiated at
cutover time.*

The React app replaces Flutter at `/` when all of these hold:

1. **Parity.** Every screen in the Flutter nav exists in React, with create,
   edit and delete where Flutter has them. The disabled nav entries are the
   checklist: none left.
2. **Capture from the phone.** The PWA installs, and the Android share target
   (`/capture`, in the Flutter manifest's `share_target`) works from the React
   app — this is how the inbox gets filled.
3. **Generated API client.** No hand-written response types remain — true
   since the client moved to `openapi-fetch`; CI keeps it true.
4. **Token decision revisited** (see Token storage) — lifetime shortened or
   cookie in place.
5. **Stale-client reload.** An open tab picks up a new deploy by itself, as the
   Flutter app does via `version.json`.
6. **CI.** The integration test drives a real workflow through the React build,
   not only that it serves.
7. **Daily use.** A week of normal daily use on staging's `/next` without
   falling back to the Flutter app.

The cutover itself is one commit: `frontend/` deleted, `frontend-next/` served
at `/` (Vite `base`, the Ingress path, the Caddy root), and the Flutter image
dropped from CI and promote.
