import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { InteractionList } from '../../../components/InteractionList'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { Select } from '../../../components/ui/Select'
import { PAGE_SIZE } from '../../../contacts'
import { interactionsQuery, kindOptions, useToggleHappened } from '../../../interactions'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/interactions/')({
  component: Activity,
})

// Two lists from one search: what is planned (soonest first) and what has
// been logged (newest first). Side by side on a desktop, stacked on a phone
// with Planned on top, since it is the shorter and the one acted on.
function Activity() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', kind, planned = 1, page = 1 } = filters
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())

  useEffect(() => {
    if (search !== q)
      void navigate({
        search: (prev) => ({ ...prev, q: search || undefined, planned: undefined, page: undefined }),
        replace: true,
      })
  }, [search, q, navigate])

  const upcoming = useQuery(interactionsQuery(api, true, { q: search, kind, page: planned }))
  const log = useQuery(interactionsQuery(api, false, { q: search, kind, page }))
  const { toggle, pendingId, error: toggleError } = useToggleHappened(api)
  const [now] = useState(() => Date.now())

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>Interactions</h1>
          <p>Calls, meetings, mails and notes — planned and logged.</p>
        </div>
        <Link to="/interactions/new" search={filters} className="button">
          Log interaction
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search interactions" placeholder="Search subjects and notes" value={input} onChange={setInput} />
        <Select
          label="Kind"
          hideLabel
          emptyLabel="All kinds"
          options={kindOptions}
          value={kind ?? ''}
          onChange={(v) =>
            void navigate({
              search: (prev) => ({ ...prev, kind: v || undefined, planned: undefined, page: undefined }),
              replace: true,
            })
          }
        />
      </div>

      {toggleError && (
        <p className="form-error" role="alert">
          Could not update the interaction: {toggleError.message}
        </p>
      )}

      <div className="activity-grid">
        <section className="panel" aria-labelledby="planned-heading">
          <div className="panel-header">
            <h2 id="planned-heading">
              Planned {upcoming.data && <span className="tab-count">{upcoming.data.total}</span>}
            </h2>
          </div>
          <div className="panel-body" data-stale={upcoming.isPlaceholderData || undefined}>
            {upcoming.isPending ? (
              <p className="muted">Loading…</p>
            ) : upcoming.error ? (
              <p className="form-error">{upcoming.error.message}</p>
            ) : upcoming.data.items.length === 0 && planned === 1 ? (
              <p className="muted">Nothing planned.</p>
            ) : (
              <>
                <InteractionList items={upcoming.data.items} onToggle={toggle} pendingId={pendingId} now={now} compact />
                <Pagination
                  page={planned}
                  pageSize={PAGE_SIZE}
                  total={upcoming.data.total}
                  isStale={upcoming.isPlaceholderData}
                  onChange={(next) =>
                    void navigate({ search: (prev) => ({ ...prev, planned: next > 1 ? next : undefined }) })
                  }
                />
              </>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="log-heading">
          <div className="panel-header">
            <h2 id="log-heading">
              Activity log {log.data && <span className="tab-count">{log.data.total}</span>}
            </h2>
          </div>
          <div className="panel-body" data-stale={log.isPlaceholderData || undefined}>
            {log.isPending ? (
              <p className="muted">Loading…</p>
            ) : log.error ? (
              <p className="form-error">{log.error.message}</p>
            ) : log.data.items.length === 0 && page === 1 ? (
              <p className="muted">{search || kind ? 'Nothing logged matches.' : 'No interactions logged yet.'}</p>
            ) : (
              <>
                <InteractionList items={log.data.items} onToggle={toggle} pendingId={pendingId} now={now} />
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={log.data.total}
                  isStale={log.isPlaceholderData}
                  onChange={(next) =>
                    void navigate({ search: (prev) => ({ ...prev, page: next > 1 ? next : undefined }) })
                  }
                />
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
