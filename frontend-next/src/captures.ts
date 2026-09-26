import { type QueryClient, keepPreviousData, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { CaptureConvert, CaptureStatus } from './api/types'

// The inbox: captures are one line of typed or shared text, parsed on the
// server into a name and a link, and worked here into a contact (plus maybe a
// lead and a logged message) or dismissed.

// Oldest first — the API's order, and the order an inbox is worked in.
export const INBOX_LIMIT = 100

export const capturesQuery = (api: Api, status: CaptureStatus, search: string) =>
  queryOptions({
    queryKey: ['captures', 'list', status, search],
    queryFn: () =>
      unwrap(api.GET('/captures/', { params: { query: { status, search: search || undefined, limit: INBOX_LIMIT } } })),
    placeholderData: keepPreviousData,
  })

export const captureQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['captures', 'detail', id],
    queryFn: () => unwrap(api.GET('/captures/{capture_id}', { params: { path: { capture_id: id } } })),
  })

// The nav badge.
export const captureCountQuery = (api: Api) =>
  queryOptions({
    queryKey: ['captures', 'count'],
    queryFn: () => unwrap(api.GET('/captures/count')),
  })

export const createCapture = (api: Api, body: { raw: string; note?: string; url?: string }) =>
  unwrap(api.POST('/captures/', { body }))

// For a typo, not a decision — a decision is a dismiss, which stays on record.
export const deleteCapture = (api: Api, id: string) =>
  unwrap(api.DELETE('/captures/{capture_id}', { params: { path: { capture_id: id } } }))

export const convertCapture = (api: Api, id: string, body: CaptureConvert) =>
  unwrap(api.POST('/captures/{capture_id}/convert', { params: { path: { capture_id: id } }, body }))

export const dismissCapture = (api: Api, id: string) =>
  unwrap(api.POST('/captures/{capture_id}/dismiss', { params: { path: { capture_id: id } } }))

// Everything a new or worked capture changes: the inbox lists and badge, the
// dashboard's queue count, and — after a convert — the records it created.
export async function invalidateAfterCapture(queryClient: QueryClient, converted = false) {
  const keys = [['captures'], ['briefing']]
  if (converted) keys.push(['contacts'], ['organizations'], ['count'], ['interactions'])
  await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
}
