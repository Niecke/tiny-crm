import { queryOptions, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { apiFetch } from '../../api'

// Every list endpoint answers with Page{items, total}; limit=1 turns it into a
// count without shipping rows nobody renders. The fuller metric set is #138
// (DASHBOARD.md) — this is just the at-a-glance row.
const countQuery = (apiUrl: string, path: string, params: Record<string, string> = {}) =>
  queryOptions({
    queryKey: ['count', path, params],
    queryFn: async () => {
      const qs = new URLSearchParams({ ...params, limit: '1' })
      const page = await apiFetch<{ total: number }>(apiUrl, `${path}?${qs}`)
      return page.total
    },
  })

type CaptureCount = { new: number; oldest_days: number | null }

const inboxQuery = (apiUrl: string) =>
  queryOptions({
    queryKey: ['captures', 'count'],
    queryFn: () => apiFetch<CaptureCount>(apiUrl, '/captures/count'),
  })

export const Route = createFileRoute('/_authed/')({
  component: Dashboard,
})

function Dashboard() {
  const { config } = Route.useRouteContext()
  const inbox = useQuery(inboxQuery(config.apiUrl))

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
        <CountStat label="Contacts" path="/contacts/" />
        <CountStat label="Organizations" path="/organizations/" />
        <CountStat label="Open tasks" path="/tasks/" />
        <CountStat label="Open deals" path="/deals/" params={{ status: 'open' }} />
        <CountStat label="Projects" path="/projects/" />
      </section>
    </div>
  )
}

function CountStat({ label, path, params }: { label: string; path: string; params?: Record<string, string> }) {
  const { config } = Route.useRouteContext()
  const { data, error } = useQuery(countQuery(config.apiUrl, path, params))
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
