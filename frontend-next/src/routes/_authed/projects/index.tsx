import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { PAGE_SIZE } from '../../../contacts'
import { formatDay } from '../../../format'
import { type ProjectStatus, projectsQuery, statusLabels, statusOf } from '../../../projects'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/projects/')({
  component: ProjectsList,
})

const order: ProjectStatus[] = ['active', 'upcoming', 'completed']

// Projects grouped by where they stand — running, not started, done — within
// the page on screen.
function ProjectsList() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', page = 1 } = filters
  const navigate = Route.useNavigate()
  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())
  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(projectsQuery(api, { q: search, page }))

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <h1>Projects</h1>
        <Link to="/projects/new" search={filters} className="button">
          New project
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search projects" placeholder="Search names" value={input} onChange={setInput} />
      </div>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 && page === 1 ? (
        <p className="muted">{search ? `No project matches “${search}”.` : 'No projects yet.'}</p>
      ) : (
        <>
          <div className="project-groups" data-stale={isPlaceholderData || undefined}>
            {order.map((status) => {
              const group = data.items.filter((p) => statusOf(p) === status)
              if (group.length === 0) return null
              return (
                <section key={status} className="panel" aria-labelledby={`group-${status}`}>
                  <div className="panel-header">
                    <h2 id={`group-${status}`}>
                      {statusLabels[status]} <span className="tab-count">{group.length}</span>
                    </h2>
                  </div>
                  <div className="panel-body">
                    <ul className="rows">
                      {group.map((p) => (
                        <li key={p.id}>
                          <span className="row-main">
                            <Link
                              to="/projects/$projectId"
                              params={{ projectId: p.id }}
                              search={filters}
                              className="row-link cell-title"
                            >
                              {p.name}
                            </Link>
                            <span className="row-meta">
                              {p.end_date
                                ? `${formatDay(p.start_date)} – ${formatDay(p.end_date)}`
                                : `From ${formatDay(p.start_date)}`}
                            </span>
                          </span>
                          <span className="row-side muted">
                            {p.contact_ids.length} contacts · {p.task_ids.length} tasks · {p.document_ids.length} docs
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </section>
              )
            })}
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
