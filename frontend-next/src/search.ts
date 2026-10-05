import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import { linkOptions } from '@tanstack/react-router'
import { type Api, unwrap } from './api/client'
import type { SearchHit, SearchType } from './api/types'
import { formatDate, formatDay } from './format'

// Hits per type in the app-bar dropdown: enough to pick from, few enough that
// nine groups still fit on a screen.
export const DROPDOWN_LIMIT = 5
// Per type on the results page before "Show all".
export const OVERVIEW_LIMIT = 10
// One type, paged, on the results page.
export const PAGE_SIZE = 25

// The API refuses anything shorter: one character matches most of every
// table, and no index helps it look.
export const MIN_QUERY_LENGTH = 2
export const isSearchable = (q: string) => q.trim().length >= MIN_QUERY_LENGTH

// One request for every type, or one type a page at a time. A query too short
// to search for is never sent: the API refuses it, and there is nothing to
// show anyway.
export const searchQuery = (
  api: Api,
  q: string,
  { type, page = 1, limit = DROPDOWN_LIMIT }: { type?: SearchType; page?: number; limit?: number } = {},
) =>
  queryOptions({
    queryKey: ['search', q, type ?? 'all', page, limit],
    queryFn: () =>
      unwrap(
        api.GET('/search/', {
          params: { query: { q, type, limit, skip: type ? (page - 1) * limit : undefined } },
        }),
      ),
    enabled: isSearchable(q),
    // Keep the previous hits on screen while the next keystroke's load,
    // instead of flashing an empty list.
    placeholderData: keepPreviousData,
  })

export const typeLabels: Record<SearchType, string> = {
  contacts: 'Contacts',
  organizations: 'Organizations',
  deals: 'Deals',
  tasks: 'Tasks',
  interactions: 'Interactions',
  projects: 'Projects',
  documents: 'Documents',
  watches: 'Watches',
  captures: 'Inbox',
}

// Where a hit opens: its own record page, or the triage page for a capture.
// One place, so the dropdown and the results page cannot send the same hit to
// different screens.
export function hitLink(hit: Pick<SearchHit, 'type' | 'id'>) {
  const id = hit.id
  switch (hit.type) {
    case 'contacts':
      return linkOptions({ to: '/contacts/$contactId', params: { contactId: id } })
    case 'organizations':
      return linkOptions({ to: '/organizations/$organizationId', params: { organizationId: id } })
    case 'deals':
      return linkOptions({ to: '/deals/$dealId', params: { dealId: id } })
    case 'tasks':
      return linkOptions({ to: '/tasks/$taskId', params: { taskId: id } })
    case 'interactions':
      return linkOptions({ to: '/interactions/$interactionId', params: { interactionId: id } })
    case 'projects':
      return linkOptions({ to: '/projects/$projectId', params: { projectId: id } })
    case 'documents':
      return linkOptions({ to: '/documents/$documentId', params: { documentId: id } })
    case 'watches':
      return linkOptions({ to: '/watches/$watchId', params: { watchId: id } })
    case 'captures':
      return linkOptions({ to: '/inbox/$captureId', params: { captureId: id } })
  }
}

// A hit's date as the reader's own calendar shows it. The API sends the value,
// not text: a task due at 23:59 here is already tomorrow in UTC.
function hitDate(date: SearchHit['date']): string | null {
  if (!date) return null
  const text = date.at ? formatDate(date.at) : date.day ? formatDay(date.day) : null
  if (!text) return null
  return date.label ? `${date.label} ${text}` : text
}

// The line under a hit's title: its subtitle and date, and where it matched
// when the title does not show it.
export function hitMeta(hit: SearchHit): string {
  const match = hit.match ? `${hit.match.field}: ${hit.match.excerpt}` : null
  return [hit.subtitle, hitDate(hit.date), match].filter(Boolean).join(' · ')
}
