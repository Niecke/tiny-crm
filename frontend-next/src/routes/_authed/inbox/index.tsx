import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useRouterState } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { GridList, GridListItem } from 'react-aria-components'
import type { CaptureRead, CaptureStatus } from '../../../api/types'
import { capturesQuery } from '../../../captures'
import { SearchField } from '../../../components/ui/SearchField'
import { daysSince } from '../../../format'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/inbox/')({
  component: Inbox,
})

const statuses: { value: CaptureStatus; label: string }[] = [
  { value: 'new', label: 'Waiting' },
  { value: 'converted', label: 'Converted' },
  { value: 'dismissed', label: 'Dismissed' },
]

function Inbox() {
  const { api } = Route.useRouteContext()
  const { status = 'new', q = '' } = Route.useSearch()
  const navigate = Route.useNavigate()
  // What the last triage did, handed over by the triage page after it ran out
  // of captures to advance to.
  const flash = useRouterState({ select: (s) => s.location.state.flash })

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())
  useEffect(() => {
    if (search !== q) void navigate({ search: (prev) => ({ ...prev, q: search || undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(capturesQuery(api, status, search))
  const keep = { status: status === 'new' ? undefined : status, q: search || undefined }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Inbox</h1>
        <p>People and leads captured on the go, waiting to be worked.</p>
      </header>

      {flash && (
        <p className="notice" role="status">
          {flash}
        </p>
      )}

      <div className="toolbar">
        <nav className="tabs tabs-plain" aria-label="Status">
          {statuses.map((s) => (
            <Link
              key={s.value}
              to="/inbox"
              search={{ status: s.value === 'new' ? undefined : s.value, q: search || undefined }}
              replace
              // "Waiting" leaves status out of the URL; without this its
              // {status: undefined} would count as matching every other tab
              // too. Active links get aria-current="page", which styles them.
              activeOptions={{ explicitUndefined: true }}
              className="tab"
            >
              {s.label}
            </Link>
          ))}
        </nav>
        <SearchField label="Search the inbox" placeholder="Search" value={input} onChange={setInput} />
      </div>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 ? (
        <p className="today-clear">
          {search
            ? `Nothing matches “${search}”.`
            : status === 'new'
              ? 'Inbox zero. New captures come from Quick note or from sharing on your phone.'
              : `Nothing ${status} yet.`}
        </p>
      ) : (
        <>
          {/* React Aria's GridList: arrow keys move through the list, Enter or
              a click opens the capture for triage. */}
          <GridList
            aria-label="Captures"
            className="panel capture-list"
            data-stale={isPlaceholderData || undefined}
            items={data.items}
            onAction={(id) =>
              navigate({ to: '/inbox/$captureId', params: { captureId: String(id) }, search: keep })
            }
          >
            {(c) => (
              <GridListItem id={c.id} textValue={c.name ?? c.raw} className="capture-item">
                <CaptureRow capture={c} />
              </GridListItem>
            )}
          </GridList>
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

function CaptureRow({ capture: c }: { capture: CaptureRead }) {
  const host = c.url ? safeHost(c.url) : null
  const meta = [host, c.note].filter(Boolean).join(' · ')
  return (
    <>
      <span className="row-main">
        <span className="cell-title">{c.name ?? c.raw}</span>
        {meta && <span className="row-meta">{meta}</span>}
      </span>
      <span className="row-side muted">
        {c.status === 'converted'
          ? `→ ${c.contact_name ?? 'contact'}${c.deal_title ? ' · lead' : ''}`
          : c.status === 'dismissed'
            ? 'dismissed'
            : waitingText(daysSince(c.created_at))}
      </span>
    </>
  )
}

function waitingText(days: number): string {
  if (days === 0) return 'today'
  return days === 1 ? 'waiting 1 day' : `waiting ${days} days`
}

function safeHost(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}
