import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { WatchCheckCreate, WatchCreate, WatchRead, WatchUpdate } from './api/types'
import { PAGE_SIZE } from './contacts'
import { formatDay, localDay } from './format'
import { recurrenceOptions } from './tasks'

// Sources: job boards, careers pages and tender portals swept on a schedule.
type Kind = WatchRead['kind']

export const kindOptions: { value: Kind; label: string; plural: string }[] = [
  { value: 'job_board', label: 'Job board', plural: 'Job boards' },
  { value: 'careers_page', label: 'Careers page', plural: 'Careers pages' },
  { value: 'tender_portal', label: 'Tender portal', plural: 'Tender portals' },
  { value: 'other', label: 'Other', plural: 'Other' },
]

export const kindLabel = (kind: string) => kindOptions.find((o) => o.value === kind)?.label ?? kind

// Due now by default: a sweep list nobody works through is the failure this
// screen exists to prevent.
export const scopeOptions = [
  { value: 'due', label: 'Due now' },
  { value: 'active', label: 'All active' },
  { value: 'all', label: 'Everything' },
] as const
export type WatchScope = (typeof scopeOptions)[number]['value']

const scopeQuery = (scope: WatchScope) =>
  scope === 'due' ? { due: true, active: true } : scope === 'active' ? { active: true } : {}

// Due now or overdue. A paused source is never due, whatever its date says.
export const isDue = (w: Pick<WatchRead, 'active' | 'next_due_at'>, now: number) =>
  w.active && Date.parse(w.next_due_at) <= now

// "Never checked", "Due today", "3 days overdue", "Due 3 Oct 2026".
export function dueLabel(w: WatchRead, now: number): string {
  if (!w.last_checked_at) return 'Never checked'
  if (!isDue(w, now)) return `Due ${formatDay(localDay(w.next_due_at))}`
  const days = Math.floor((now - Date.parse(w.next_due_at)) / 86_400_000)
  if (days === 0) return 'Due today'
  return days === 1 ? '1 day overdue' : `${days} days overdue`
}

// "Every week", "Every 2 months".
export function cadenceLabel(w: Pick<WatchRead, 'recurrence_rule' | 'recurrence_interval'>): string {
  const rule = recurrenceOptions.find((o) => o.value === w.recurrence_rule)
  if (!rule) return w.recurrence_rule
  return w.recurrence_interval === 1 ? `Every ${rule.unit}` : `Every ${w.recurrence_interval} ${rule.units}`
}

export type WatchFilters = { q?: string; scope?: WatchScope; kind?: Kind; page?: number }

// Active first, then soonest due — the API's order.
export const watchesQuery = (api: Api, { q, scope = 'due', kind, page = 1 }: WatchFilters) =>
  queryOptions({
    queryKey: ['watches', 'list', { q, scope, kind, page }],
    queryFn: () =>
      unwrap(
        api.GET('/watches/', {
          params: {
            query: {
              search: q || undefined,
              kind,
              ...scopeQuery(scope),
              skip: (page - 1) * PAGE_SIZE,
              limit: PAGE_SIZE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

// The nav badge: how many sources are due, read from the total of a one-row
// page.
export const dueCountQuery = (api: Api) =>
  queryOptions({
    queryKey: ['watches', 'due-count'],
    queryFn: async () =>
      (await unwrap(api.GET('/watches/', { params: { query: { due: true, active: true, limit: 1 } } }))).total,
  })

export const watchQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['watches', 'detail', id],
    queryFn: () => unwrap(api.GET('/watches/{watch_id}', { params: { path: { watch_id: id } } })),
  })

// Every sweep of one source, newest first.
export const checksQuery = (api: Api, id: string, page = 1) =>
  queryOptions({
    queryKey: ['watches', 'checks', id, page],
    queryFn: () =>
      unwrap(
        api.GET('/watches/{watch_id}/checks', {
          params: { path: { watch_id: id }, query: { skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  })

export const createWatch = (api: Api, body: WatchCreate) => unwrap(api.POST('/watches/', { body }))

export const updateWatch = (api: Api, id: string, body: WatchUpdate) =>
  unwrap(api.PATCH('/watches/{watch_id}', { params: { path: { watch_id: id } }, body }))

export const deleteWatch = (api: Api, id: string) =>
  unwrap(api.DELETE('/watches/{watch_id}', { params: { path: { watch_id: id } } }))

// One sweep. The server moves the next due date on from it, and a find can
// become a deal or a task in the same request.
export const logCheck = (api: Api, id: string, body: WatchCheckCreate) =>
  unwrap(api.POST('/watches/{watch_id}/check', { params: { path: { watch_id: id } }, body }))

// A sweep that found something may have made a deal or a task.
export const invalidateWatches = (queryClient: QueryClient) =>
  Promise.all(
    [['watches'], ['deals'], ['tasks'], ['briefing']].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
  )

// Only http(s) is opened, so a stored URL cannot become a javascript: link.
export const safeUrl = (url: string) => (/^https?:\/\//i.test(url) ? url : `https://${url.replace(/^[a-z]+:/i, '')}`)
