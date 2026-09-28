import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Cell, Column, Row, Table, TableBody, TableHeader } from 'react-aria-components'
import { DealBoard } from '../../../components/DealBoard'
import { LostReasonDialog } from '../../../components/LostReasonDialog'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { Segmented } from '../../../components/ui/Segmented'
import { Select } from '../../../components/ui/Select'
import { PAGE_SIZE } from '../../../contacts'
import {
  BOARD_LIMIT,
  boardQuery,
  dealsQuery,
  scopeOf,
  scopeOptions,
  stageLabel,
  stageTone,
  valueSummary,
} from '../../../deals'
import { formatDay } from '../../../format'
import { useDebounced } from '../../../useDebounced'
import { useMoveDeal } from '../../../useMoveDeal'

export const Route = createFileRoute('/_authed/deals/')({
  component: Deals,
})

// The pipeline: a board by default (#13), or a paged list.
function Deals() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', scope, view, page = 1 } = filters
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())
  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const current = scopeOf(scope)
  const board = useQuery({ ...boardQuery(api, { q: search, scope }), enabled: view !== 'list' })
  const list = useQuery({ ...dealsQuery(api, { q: search, scope, page }), enabled: view === 'list' })
  const mover = useMoveDeal(api)

  return (
    <div className="page page-wide">
      <header className="page-header page-header-row">
        <h1>Deals</h1>
        <Link to="/deals/new" search={filters} className="button">
          New deal
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search deals" placeholder="Search titles" value={input} onChange={setInput} />
        <Select
          label="Show"
          hideLabel
          options={scopeOptions.map((o) => ({ value: o.value, label: o.label }))}
          value={current.value}
          onChange={(v) =>
            void navigate({
              search: (prev) => ({ ...prev, scope: v && v !== 'plate' ? v : undefined, page: undefined }),
              replace: true,
            })
          }
        />
        <Segmented
          label="View"
          value={view ?? 'board'}
          onChange={(v) =>
            void navigate({ search: (prev) => ({ ...prev, view: v === 'list' ? 'list' : undefined, page: undefined }), replace: true })
          }
          options={[
            { value: 'board', label: 'Board' },
            { value: 'list', label: 'List' },
          ]}
        />
      </div>

      {mover.error && (
        <p className="form-error" role="alert">
          Could not move the deal: {mover.error.message}
        </p>
      )}

      {view !== 'list' ? (
        board.isPending ? (
          <p className="muted">Loading…</p>
        ) : board.error ? (
          <p className="form-error">{board.error.message}</p>
        ) : (
          <>
            <DealBoard
              deals={board.data.items}
              columns={current.columns}
              onMove={mover.move}
              pendingId={mover.pendingId}
            />
            {board.data.total > BOARD_LIMIT && (
              <p className="muted small">
                Showing {BOARD_LIMIT} of {board.data.total}. Narrow the search or the scope to see the rest.
              </p>
            )}
          </>
        )
      ) : list.isPending ? (
        <p className="muted">Loading…</p>
      ) : list.error ? (
        <p className="form-error">{list.error.message}</p>
      ) : list.data.items.length === 0 && page === 1 ? (
        <p className="muted">{current.value === 'plate' && !search ? 'Nothing on your plate.' : 'No deals here.'}</p>
      ) : (
        <>
          <div className="panel table-wrap" data-stale={list.isPlaceholderData || undefined}>
            <Table
              aria-label="Deals"
              className="table"
              onRowAction={(id) => navigate({ to: '/deals/$dealId', params: { dealId: String(id) }, search: filters })}
            >
              <TableHeader>
                <Column isRowHeader>Deal</Column>
                <Column className="col-optional">Value</Column>
                <Column className="col-optional">Expected close</Column>
                <Column>Stage</Column>
              </TableHeader>
              <TableBody items={list.data.items}>
                {(d) => (
                  <Row id={d.id} className="table-row">
                    <Cell>
                      <span className="cell-main">
                        <span className="cell-title">{d.title}</span>
                        {(d.organization_name || d.contact_name) && (
                          <span className="cell-meta">{d.organization_name ?? d.contact_name}</span>
                        )}
                      </span>
                    </Cell>
                    <Cell className="col-optional">{valueSummary(d) ?? <span className="muted">—</span>}</Cell>
                    <Cell className="col-optional muted">
                      {d.expected_close_date ? formatDay(d.expected_close_date) : '—'}
                    </Cell>
                    <Cell>
                      <span className="badge" data-tone={stageTone(d.stage)}>
                        {stageLabel(d.stage)}
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
            total={list.data.total}
            isStale={list.isPlaceholderData}
            onChange={(next) => void navigate({ search: (prev) => ({ ...prev, page: next > 1 ? next : undefined }) })}
          />
        </>
      )}

      <LostReasonDialog deal={mover.askingWhy} onConfirm={mover.confirmLost} onCancel={mover.cancelLost} />
    </div>
  )
}
