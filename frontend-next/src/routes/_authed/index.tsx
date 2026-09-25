import { queryOptions, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { type Api, unwrap } from '../../api/client'

// Every list endpoint answers with a Page of {items, total}; limit=1 turns it
// into a count without shipping rows nobody renders. The fuller metric set is
// #138 (DASHBOARD.md) — this is just the at-a-glance row.
const first = { params: { query: { limit: 1 } } }

// Each call is unwrapped on its own: the five pages are different types, and
// only their `total` is shared.
const total = async (request: Promise<{ data?: { total: number }; error?: unknown; response: Response }>) =>
  (await unwrap(request)).total

const counts = {
  contacts: (api: Api) => total(api.GET('/contacts/', first)),
  organizations: (api: Api) => total(api.GET('/organizations/', first)),
  // Done tasks are left out by default.
  tasks: (api: Api) => total(api.GET('/tasks/', first)),
  deals: (api: Api) => total(api.GET('/deals/', { params: { query: { limit: 1, status: 'open' } } })),
  projects: (api: Api) => total(api.GET('/projects/', first)),
}

type CountKey = keyof typeof counts

const countQuery = (api: Api, key: CountKey) =>
  queryOptions({
    queryKey: ['count', key],
    queryFn: () => counts[key](api),
  })

const inboxQuery = (api: Api) =>
  queryOptions({
    queryKey: ['captures', 'count'],
    queryFn: () => unwrap(api.GET('/captures/count')),
  })

export const Route = createFileRoute('/_authed/')({
  component: Dashboard,
})

function Dashboard() {
  const { api } = Route.useRouteContext()
  const inbox = useQuery(inboxQuery(api))

  const inboxHint =
    inbox.data?.oldest_days == null
      ? undefined
      : inbox.data.oldest_days === 0
        ? 'oldest from today'
        : `oldest ${inbox.data.oldest_days} d`

  return (
    <div className="page">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p>Where things stand.</p>
      </header>

      <section className="stats" aria-label="Counts">
        <Stat
          label="Inbox"
          value={inbox.data?.new}
          error={inbox.error}
          hint={inboxHint}
          tone={inbox.data?.new ? 'warning' : undefined}
        />
        <CountStat label="Contacts" count="contacts" />
        <CountStat label="Organizations" count="organizations" />
        <CountStat label="Open tasks" count="tasks" />
        <CountStat label="Open deals" count="deals" />
        <CountStat label="Projects" count="projects" />
      </section>
    </div>
  )
}

function CountStat({ label, count }: { label: string; count: CountKey }) {
  const { api } = Route.useRouteContext()
  const { data, error } = useQuery(countQuery(api, count))
  return <Stat label={label} value={data} error={error} />
}

function Stat({
  label,
  value,
  error,
  hint,
  tone,
}: {
  label: string
  value: number | undefined
  error: Error | null
  hint?: string
  tone?: 'warning'
}) {
  return (
    <div className="panel stat" data-tone={tone}>
      <span className="stat-label">{label}</span>
      <span className="stat-value" title={error?.message}>
        {error ? '!' : value === undefined ? '–' : value}
      </span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  )
}
