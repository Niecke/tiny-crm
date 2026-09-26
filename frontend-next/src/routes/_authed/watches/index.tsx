import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Cell, Column, Row, Table, TableBody, TableHeader } from 'react-aria-components'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { Select } from '../../../components/ui/Select'
import { PAGE_SIZE } from '../../../contacts'
import { useDebounced } from '../../../useDebounced'
import { cadenceLabel, dueLabel, isDue, kindLabel, kindOptions, scopeOptions, watchesQuery } from '../../../watches'

export const Route = createFileRoute('/_authed/watches/')({
  component: Watches,
})

// The sources to sweep, what is due first.
function Watches() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', scope = 'due', kind, page = 1 } = filters
  const navigate = Route.useNavigate()
  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())
  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(watchesQuery(api, { q: search, scope, kind, page }))
  const [now] = useState(() => Date.now())

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>Watches</h1>
          <p>Job boards, careers pages and tender portals, swept on a schedule.</p>
        </div>
        <Link to="/watches/new" search={filters} className="button">
          New source
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search sources" placeholder="Search names" value={input} onChange={setInput} />
        <Select
          label="Show"
          hideLabel
          options={[...scopeOptions]}
          value={scope}
          onChange={(v) =>
            void navigate({
              search: (prev) => ({ ...prev, scope: v === 'active' || v === 'all' ? v : undefined, page: undefined }),
              replace: true,
            })
          }
        />
        <Select
          label="Kind"
          hideLabel
          emptyLabel="All kinds"
          options={kindOptions.map((o) => ({ value: o.value, label: o.plural }))}
          value={kind ?? ''}
          onChange={(v) =>
            void navigate({ search: (prev) => ({ ...prev, kind: v || undefined, page: undefined }), replace: true })
          }
        />
      </div>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 && page === 1 ? (
        <p className="muted">{scope === 'due' && !search && !kind ? 'Nothing due. All swept.' : 'No sources here.'}</p>
      ) : (
        <>
          <div className="panel table-wrap" data-stale={isPlaceholderData || undefined}>
            <Table
              aria-label="Sources"
              className="table"
              onRowAction={(id) => navigate({ to: '/watches/$watchId', params: { watchId: String(id) }, search: filters })}
            >
              <TableHeader>
                <Column isRowHeader>Source</Column>
                <Column className="col-optional">Cadence</Column>
                <Column>Due</Column>
              </TableHeader>
              <TableBody items={data.items}>
                {(w) => (
                  <Row id={w.id} className="table-row" data-paused={!w.active || undefined}>
                    <Cell>
                      <span className="cell-main">
                        <span className="cell-title">{w.name}</span>
                        <span className="cell-meta">
                          {[kindLabel(w.kind), w.organization_name, !w.active && 'paused'].filter(Boolean).join(' · ')}
                        </span>
                      </span>
                    </Cell>
                    <Cell className="col-optional muted">{cadenceLabel(w)}</Cell>
                    <Cell>
                      <span className={isDue(w, now) ? 'badge' : 'muted small'} data-tone={isDue(w, now) ? 'warning' : undefined}>
                        {w.active ? dueLabel(w, now) : 'Paused'}
                      </span>
                    </Cell>
                  </Row>
                )}
              </TableBody>
            </Table>
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            isStale={isPlaceholderData}
            onChange={(next) => void navigate({ search: (prev) => ({ ...prev, page: next > 1 ? next : undefined }) })}
          />
        </>
      )}
    </div>
  )
}
