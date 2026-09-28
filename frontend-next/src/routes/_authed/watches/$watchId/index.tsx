import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import { CheckDialog } from '../../../../components/CheckDialog'
import { Fact, Facts } from '../../../../components/RecordPage'
import { Button } from '../../../../components/ui/Button'
import { ConfirmDialog } from '../../../../components/ui/ConfirmDialog'
import { Pagination } from '../../../../components/ui/Pagination'
import { PAGE_SIZE } from '../../../../contacts'
import { formatDateTime } from '../../../../format'
import {
  cadenceLabel,
  checksQuery,
  deleteWatch,
  dueLabel,
  invalidateWatches,
  isDue,
  kindLabel,
  safeUrl,
  updateWatch,
  watchQuery,
} from '../../../../watches'

// The page of sweep history in view.
const searchSchema = z.object({
  checks: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/watches/$watchId/')({
  validateSearch: searchSchema,
  component: WatchDetail,
})

function WatchDetail() {
  const { api } = Route.useRouteContext()
  const { watchId } = Route.useParams()
  const { checks: checksPage = 1, ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const watch = useQuery(watchQuery(api, watchId))
  const checks = useQuery(checksQuery(api, watchId, checksPage))
  const [now] = useState(() => Date.now())
  const [sweeping, setSweeping] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const pause = useMutation({
    mutationFn: (active: boolean) => updateWatch(api, watchId, { active }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(watchQuery(api, watchId).queryKey, saved)
      setConfirmDelete(false)
      await invalidateWatches(queryClient)
    },
  })

  const remove = useMutation({
    mutationFn: () => deleteWatch(api, watchId),
    onSuccess: async () => {
      await navigate({ to: '/watches', search: filters, replace: true })
      queryClient.removeQueries({ queryKey: ['watches', 'detail', watchId] })
      queryClient.removeQueries({ queryKey: ['watches', 'checks', watchId] })
      await invalidateWatches(queryClient)
    },
  })

  const back = (
    <Link to="/watches" search={filters} className="back-link">
      ← Watches
    </Link>
  )

  if (watch.isPending || watch.error) {
    return (
      <div className="page">
        {back}
        {watch.isPending ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="form-error">
            {watch.error instanceof ApiError && watch.error.status === 404
              ? 'This source does not exist, or was deleted.'
              : watch.error.message}
          </p>
        )}
      </div>
    )
  }

  const w = watch.data
  const url = safeUrl(w.url)
  const due = isDue(w, now)

  return (
    <div className="page">
      {back}

      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>{w.name}</h1>
          <p>
            {kindLabel(w.kind)} · {cadenceLabel(w)}
            {w.organization_id && (
              <>
                {' · '}
                <Link to="/organizations/$organizationId" params={{ organizationId: w.organization_id }}>
                  {w.organization_name}
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="header-actions">
          <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
            Delete
          </Button>
          <Link to="/watches/$watchId/edit" params={{ watchId }} search={filters} className="button button-quiet">
            Edit
          </Link>
        </div>
      </header>

      <section className="panel sweep-bar" data-due={due || undefined}>
        <div className="row-main">
          <strong>{w.active ? dueLabel(w, now) : 'Paused'}</strong>
          <span className="row-meta">
            {w.last_checked_at ? `Last swept ${formatDateTime(w.last_checked_at)}` : 'Never swept'}
            {w.check_count > 0 &&
              ` · ${w.found_count} ${w.found_count === 1 ? 'find' : 'finds'} in ${w.check_count} ${w.check_count === 1 ? 'sweep' : 'sweeps'}`}
          </span>
        </div>
        <div className="header-actions">
          {/* Opens the source in a new tab and the log dialog here, so coming
              back to this tab after looking is one step. */}
          <Button
            onPress={() => {
              window.open(url, '_blank', 'noopener,noreferrer')
              setSweeping(true)
            }}
          >
            Open &amp; sweep
          </Button>
          <Button variant="quiet" onPress={() => setSweeping(true)}>
            Log a sweep
          </Button>
        </div>
      </section>

      <div className="profile">
        <Facts>
          <Fact label="Web address">
            <a href={url} target="_blank" rel="noreferrer">
              {w.url}
            </a>
          </Fact>
          {w.query_note && <Fact label="What to look for">{w.query_note}</Fact>}
          <Fact label="Status">
            {w.active ? (
              'Active'
            ) : (
              <>
                Paused{' '}
                <Button variant="quiet" className="link-button" onPress={() => pause.mutate(true)}>
                  Resume
                </Button>
              </>
            )}
          </Fact>
          {w.notes && <Fact label="Notes">{w.notes}</Fact>}
        </Facts>

        <section className="panel" aria-labelledby="history-heading">
          <div className="panel-header">
            <h2 id="history-heading">Sweeps</h2>
          </div>
          <div className="panel-body" data-stale={checks.isPlaceholderData || undefined}>
            {checks.isPending ? (
              <p className="muted">Loading…</p>
            ) : checks.error ? (
              <p className="form-error">{checks.error.message}</p>
            ) : checks.data.items.length === 0 ? (
              <p className="muted">Never swept.</p>
            ) : (
              <>
                <ul className="rows">
                  {checks.data.items.map((c) => (
                    <li key={c.id} className="sweep-row" data-found={c.outcome === 'found' || undefined}>
                      <span className="sweep-mark" aria-hidden="true">
                        {c.outcome === 'found' ? '★' : '–'}
                      </span>
                      <span className="row-main">
                        <span>{c.note || (c.outcome === 'found' ? 'Found something' : 'Nothing new')}</span>
                        <span className="row-meta">
                          {formatDateTime(c.checked_at)}
                          {c.outcome === 'found' && ' · found'}
                        </span>
                      </span>
                      {c.created_deal_id && (
                        <Link to="/deals/$dealId" params={{ dealId: c.created_deal_id }} className="row-side">
                          Became a deal
                        </Link>
                      )}
                      {c.created_task_id && (
                        <Link to="/tasks/$taskId" params={{ taskId: c.created_task_id }} className="row-side">
                          Became a task
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
                <Pagination
                  page={checksPage}
                  pageSize={PAGE_SIZE}
                  total={checks.data.total}
                  isStale={checks.isPlaceholderData}
                  onChange={(next) =>
                    void navigate({ to: '.', search: { ...filters, checks: next > 1 ? next : undefined }, replace: true })
                  }
                />
              </>
            )}
          </div>
        </section>
      </div>

      <CheckDialog watch={w} isOpen={sweeping} onOpenChange={setSweeping} />

      {/* A source with history is usually better paused than deleted; the
          dialog offers both. */}
      <ConfirmDialog
        title="Delete this source?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error ?? pause.error}
      >
        <p>
          <strong>{w.name}</strong> and its {w.check_count} logged {w.check_count === 1 ? 'sweep' : 'sweeps'} will be
          permanently deleted.
        </p>
        {w.active && w.check_count > 0 && (
          <p className="muted small">
            To stop sweeping it but keep the history,{' '}
            <Button variant="quiet" className="link-button" onPress={() => pause.mutate(false)}>
              pause it instead
            </Button>
            .
          </p>
        )}
      </ConfirmDialog>
    </div>
  )
}
