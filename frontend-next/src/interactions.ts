import { keepPreviousData, type QueryClient, queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { InteractionCreate, InteractionRead } from './api/types'
import { PAGE_SIZE } from './contacts'

type Kind = NonNullable<InteractionCreate['kind']>

// In the Flutter app's order and words ("Mail" for email).
export const kindOptions: { value: Kind; label: string }[] = [
  { value: 'call', label: 'Call' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'email', label: 'Mail' },
  { value: 'note', label: 'Note' },
  { value: 'other', label: 'Other' },
]

export const kindLabel = (kind: string) => kindOptions.find((o) => o.value === kind)?.label ?? kind

// Planned: in the future. Overdue: planned for a time that has passed, and not
// marked as happened.
export const isPlanned = (i: Pick<InteractionRead, 'occurred_at'>, now: number) => Date.parse(i.occurred_at) > now
export const isOverdueInteraction = (i: Pick<InteractionRead, 'occurred_at' | 'done'>, now: number) =>
  !i.done && Date.parse(i.occurred_at) <= now

export type InteractionFilters = { q?: string; kind?: Kind; page?: number }

// The two halves of the activity screen. Planned is soonest first, the log
// newest first — the API orders each that way when `upcoming` is set.
export const interactionsQuery = (api: Api, upcoming: boolean, { q, kind, page = 1 }: InteractionFilters) =>
  queryOptions({
    queryKey: ['interactions', 'list', upcoming, { q, kind, page }],
    queryFn: () =>
      unwrap(
        api.GET('/interactions/', {
          params: {
            query: { search: q || undefined, kind, upcoming, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

export const interactionQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['interactions', 'detail', id],
    queryFn: () =>
      unwrap(api.GET('/interactions/{interaction_id}', { params: { path: { interaction_id: id } } })),
  })

export type InteractionLink = { contact_id?: string; organization_id?: string; deal_id?: string; project_id?: string }

// Everything logged with one record, newest first, planned entries included.
export const linkedInteractionsQuery = (api: Api, link: InteractionLink, page = 1) =>
  queryOptions({
    queryKey: ['interactions', 'linked', link, page],
    queryFn: () =>
      unwrap(
        api.GET('/interactions/', { params: { query: { ...link, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE } } }),
      ),
    placeholderData: keepPreviousData,
  })

export const createInteraction = (api: Api, body: InteractionCreate) => unwrap(api.POST('/interactions/', { body }))

// The link lists are sent whole: they replace what is stored.
export const updateInteraction = (api: Api, id: string, body: InteractionCreate) =>
  unwrap(api.PATCH('/interactions/{interaction_id}', { params: { path: { interaction_id: id } }, body }))

export const deleteInteraction = (api: Api, id: string) =>
  unwrap(api.DELETE('/interactions/{interaction_id}', { params: { path: { interaction_id: id } } }))

// Every list and every record tab lives under ['interactions'], so one
// invalidation reaches them all — the Flutter app refreshed only the main
// list and left the record pages' sections stale. The briefing lists today's
// and overdue ones.
export const invalidateInteractions = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['interactions'] }),
    queryClient.invalidateQueries({ queryKey: ['briefing'] }),
  ])

// Happened / not happened, from any list.
export function useToggleHappened(api: Api) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (i: InteractionRead) =>
      unwrap(
        api.PATCH('/interactions/{interaction_id}', {
          params: { path: { interaction_id: i.id } },
          body: { done: !i.done },
        }),
      ),
    onSuccess: () => invalidateInteractions(queryClient),
  })
  return { toggle: mutation.mutate, pendingId: mutation.isPending ? mutation.variables?.id : undefined, error: mutation.error }
}
