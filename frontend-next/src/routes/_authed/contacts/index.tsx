import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Cell, Column, Row, Table, TableBody, TableHeader } from 'react-aria-components'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { Select } from '../../../components/ui/Select'
import { contactsQuery, labelOf, lifecycleOptions, PAGE_SIZE, relationOptions } from '../../../contacts'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/contacts/')({
  component: ContactsList,
})

function ContactsList() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', status, relation, page = 1 } = filters
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())

  // A new search or filter starts again at page one.
  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(
    contactsQuery(api, { q: search, status, relation, page }),
  )
  const filtered = Boolean(search || status || relation)

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <h1>Contacts</h1>
        <Link to="/contacts/new" search={filters} className="button">
          New contact
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search contacts" placeholder="Search name or email" value={input} onChange={setInput} />
        <Select
          label="Status"
          hideLabel
          emptyLabel="Any status"
          options={lifecycleOptions}
          value={status ?? ''}
          onChange={(v) =>
            void navigate({ search: (prev) => ({ ...prev, status: v || undefined, page: undefined }), replace: true })
          }
        />
        <Select
          label="Relation"
          hideLabel
          emptyLabel="Any relation"
          options={relationOptions}
          value={relation ?? ''}
          onChange={(v) =>
            void navigate({ search: (prev) => ({ ...prev, relation: v || undefined, page: undefined }), replace: true })
          }
        />
      </div>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 && page === 1 ? (
        <p className="muted">{filtered ? 'No contact matches these filters.' : 'No contacts yet.'}</p>
      ) : (
        <>
          <div className="panel table-wrap" data-stale={isPlaceholderData || undefined}>
            <Table
              aria-label="Contacts"
              className="table"
              onRowAction={(id) =>
                navigate({ to: '/contacts/$contactId', params: { contactId: String(id) }, search: filters })
              }
            >
              <TableHeader>
                <Column isRowHeader>Name</Column>
                <Column className="col-optional">Organization</Column>
                <Column>Status</Column>
              </TableHeader>
              <TableBody items={data.items}>
                {(c) => (
                  <Row id={c.id} className="table-row">
                    <Cell>
                      <span className="cell-main">
                        <span className="cell-title">{c.name}</span>
                        {(c.job_title || c.email) && <span className="cell-meta">{c.job_title || c.email}</span>}
                      </span>
                    </Cell>
                    <Cell className="col-optional muted">{c.organization_name}</Cell>
                    <Cell>
                      {c.lifecycle_status && <span className="badge">{labelOf(lifecycleOptions, c.lifecycle_status)}</span>}
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
