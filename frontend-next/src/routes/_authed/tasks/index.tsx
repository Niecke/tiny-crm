import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { TaskList } from '../../../components/TaskList'
import { Checkbox } from '../../../components/ui/Checkbox'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { PAGE_SIZE } from '../../../contacts'
import { formatDay, localDay } from '../../../format'
import { tasksQuery, useToggleDone } from '../../../tasks'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/tasks/')({
  component: TasksList,
})

function TasksList() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', done = false, page = 1 } = filters
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())

  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(tasksQuery(api, { q: search, done, page }))
  const { toggle, pendingId, error: toggleError, repeated } = useToggleDone(api)
  const [now] = useState(() => Date.now())

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>Tasks</h1>
          <p>Soonest due first; undated tasks at the end.</p>
        </div>
        <Link to="/tasks/new" search={filters} className="button">
          New task
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search tasks" placeholder="Search titles" value={input} onChange={setInput} />
        <Checkbox
          isSelected={done}
          onChange={(v) =>
            void navigate({ search: (prev) => ({ ...prev, done: v || undefined, page: undefined }), replace: true })
          }
        >
          Show done
        </Checkbox>
      </div>

      {repeated && (
        <p className="notice" role="status">
          Repeated: “{repeated.title}” is due again {formatDay(localDay(repeated.due))}.
        </p>
      )}
      {toggleError && (
        <p className="form-error" role="alert">
          Could not update the task: {toggleError.message}
        </p>
      )}

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 && page === 1 ? (
        <p className="muted">{search ? `No task matches “${search}”.` : done ? 'No tasks yet.' : 'Nothing outstanding.'}</p>
      ) : (
        <>
          <div className="panel panel-body" data-stale={isPlaceholderData || undefined}>
            <TaskList tasks={data.items} onToggle={toggle} pendingId={pendingId} now={now} />
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
