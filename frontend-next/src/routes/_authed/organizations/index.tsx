import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Cell, Column, Row, Table, TableBody, TableHeader } from 'react-aria-components'
import { SearchField } from '../../../components/ui/SearchField'
import { organizationsQuery } from '../../../organizations'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/organizations/')({
  component: OrganizationsList,
})

function OrganizationsList() {
  const { api } = Route.useRouteContext()
  const { q = '' } = Route.useSearch()
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())

  useEffect(() => {
    if (search !== q) void navigate({ search: (prev) => ({ ...prev, q: search || undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(organizationsQuery(api, search))
  const keep = { q: search || undefined }

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <h1>Organizations</h1>
        <Link to="/organizations/new" search={keep} className="button">
          New organization
        </Link>
      </header>

      <SearchField
        label="Search organizations"
        placeholder="Search name or domain"
        value={input}
        onChange={setInput}
      />

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 ? (
        <p className="muted">{search ? `No organization matches “${search}”.` : 'No organizations yet.'}</p>
      ) : (
        <>
          {/* React Aria's Table: a real <table> with row navigation — arrow keys
              move between rows, Enter or a click opens one. */}
          <div className="panel table-wrap" data-stale={isPlaceholderData || undefined}>
            <Table
              aria-label="Organizations"
              className="table"
              onRowAction={(id) =>
                navigate({
                  to: '/organizations/$organizationId',
                  params: { organizationId: String(id) },
                  search: keep,
                })
              }
            >
              <TableHeader>
                <Column isRowHeader>Name</Column>
                <Column className="col-optional">Industry</Column>
                <Column className="col-num">Contacts</Column>
              </TableHeader>
              <TableBody items={data.items}>
                {(o) => (
                  <Row id={o.id} className="table-row">
                    <Cell>
                      <span className="cell-main">
                        <span className="cell-title">{o.name}</span>
                        {o.domain && <span className="cell-meta">{o.domain}</span>}
                      </span>
                    </Cell>
                    <Cell className="col-optional muted">{o.industry}</Cell>
                    <Cell className="col-num">{o.contact_count}</Cell>
                  </Row>
                )}
              </TableBody>
            </Table>
          </div>
          {data.total > data.items.length && (
            <p className="muted small">
              Showing {data.items.length} of {data.total}. Narrow the search to find the rest.
            </p>
          )}
        </>
      )}
    </div>
  )
}
