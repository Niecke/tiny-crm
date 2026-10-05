import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { z } from 'zod'
import type { SearchGroup, SearchType } from '../../api/types'
import { Pagination } from '../../components/ui/Pagination'
import { SearchField } from '../../components/ui/SearchField'
import {
  hitLink,
  hitMeta,
  isSearchable,
  MIN_QUERY_LENGTH,
  OVERVIEW_LIMIT,
  PAGE_SIZE,
  searchQuery,
  typeLabels,
} from '../../search'
import { useDebounced } from '../../useDebounced'

const types = Object.keys(typeLabels) as [SearchType, ...SearchType[]]

// The query, one type to page through, and the page — all in the URL, so a
// search survives a reload and Back returns to the same results.
const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
  type: z.enum(types).optional().catch(undefined),
  page: z.number().int().min(2).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/search')({
  validateSearch: searchSchema,
  component: SearchPage,
})

function SearchPage() {
  const { api } = Route.useRouteContext()
  const { q = '', type, page = 1 } = Route.useSearch()
  const navigate = Route.useNavigate()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())

  // The app-bar box can send a new query to this page while it is open. That
  // query replaces what is in the field; one this field sent itself (q equal
  // to its own debounced text) does not, or a keystroke typed meanwhile would
  // be lost.
  const [seenQ, setSeenQ] = useState(q)
  if (q !== seenQ) {
    setSeenQ(q)
    if (q !== search) setInput(q)
  }

  // Only once the debounce has caught up with the field: until then `search`
  // is the text from before an outside query arrived, and sending it would
  // undo that query.
  useEffect(() => {
    if (search !== q && search === input.trim())
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, input, q, navigate])

  const limit = type ? PAGE_SIZE : OVERVIEW_LIMIT
  const { data, error, isPending, isPlaceholderData } = useQuery(searchQuery(api, q, { type, page, limit }))
  const groups = data?.groups.filter((g) => g.total > 0) ?? []

  return (
    <div className="page">
      <header className="page-header">
        <h1>{type ? `Search · ${typeLabels[type]}` : 'Search'}</h1>
        <p>Contacts, organizations, deals, tasks, interactions, projects, documents, watches and the inbox.</p>
      </header>

      <div className="toolbar">
        {type && (
          <Link to="/search" search={{ q: q || undefined }} className="back-link">
            ‹ All types
          </Link>
        )}
        <SearchField label="Search terms" placeholder="Search everything" value={input} onChange={setInput} />
      </div>

      {!q ? (
        <p className="muted">Type a name, an email address, part of a phone number or a word from a note.</p>
      ) : !isSearchable(q) ? (
        <p className="muted">Type at least {MIN_QUERY_LENGTH} characters.</p>
      ) : isPending ? (
        <p className="muted">Searching…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : groups.length === 0 ? (
        <p className="muted">Nothing matches “{q}”.</p>
      ) : (
        groups.map((group) => (
          <ResultGroup
            key={group.type}
            group={group}
            q={q}
            paged={Boolean(type)}
            page={page}
            isStale={isPlaceholderData}
            onPage={(next) =>
              void navigate({ search: (prev) => ({ ...prev, page: next > 1 ? next : undefined }) })
            }
          />
        ))
      )}
    </div>
  )
}

function ResultGroup({
  group,
  q,
  paged,
  page,
  isStale,
  onPage,
}: {
  group: SearchGroup
  q: string
  paged: boolean
  page: number
  isStale: boolean
  onPage: (page: number) => void
}) {
  const label = typeLabels[group.type]
  return (
    <section className="panel search-group" aria-label={label} data-stale={isStale || undefined}>
      <header className="panel-header search-group-header">
        <h2>
          {label} <span className="muted">· {group.total}</span>
        </h2>
        {!paged && group.total > group.items.length && (
          <Link to="/search" search={{ q, type: group.type }} className="small">
            Show all {group.total}
          </Link>
        )}
      </header>
      <ul className="search-hits">
        {group.items.map((hit) => (
          <li key={hit.id}>
            <Link {...hitLink(hit)} className="search-hit">
              <span className="cell-title">{hit.title}</span>
              {hitMeta(hit) && <span className="row-meta">{hitMeta(hit)}</span>}
            </Link>
          </li>
        ))}
      </ul>
      {paged && <Pagination page={page} pageSize={PAGE_SIZE} total={group.total} onChange={onPage} isStale={isStale} />}
    </section>
  )
}
