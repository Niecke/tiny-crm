import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { ContactCreate } from './api/types'

// Rows per page on every paged list (FRONTEND.md, "Paging").
export const PAGE_SIZE = 25
// Per tab on a record page, as on the organization page.
const DETAIL_LIMIT = 20

// The fixed vocabularies, in the order the Flutter app offers them. The values
// are the API's; the schema types them, so a value the backend does not have
// is a compile error.
type Lifecycle = NonNullable<ContactCreate['lifecycle_status']>
type Relation = NonNullable<ContactCreate['relation_type']>
type Source = NonNullable<ContactCreate['source']>

export const lifecycleOptions: { value: Lifecycle; label: string }[] = [
  { value: 'lead', label: 'Lead' },
  { value: 'prospect', label: 'Prospect' },
  { value: 'customer', label: 'Customer' },
  { value: 'former', label: 'Former' },
]

export const relationOptions: { value: Relation; label: string }[] = [
  { value: 'customer', label: 'Customer' },
  { value: 'partner', label: 'Partner' },
  { value: 'subcontracting_target', label: 'Subcontracting target' },
  { value: 'contracting_authority', label: 'Contracting authority' },
]

export const sourceOptions: { value: Source; label: string }[] = [
  { value: 'referral', label: 'Referral' },
  { value: 'inbound', label: 'Inbound' },
  { value: 'outbound', label: 'Outbound' },
  { value: 'event', label: 'Event' },
  { value: 'job_board', label: 'Job board' },
  { value: 'tender_portal', label: 'Tender portal' },
  { value: 'other', label: 'Other' },
]

export const labelOf = (options: { value: string; label: string }[], value: string | null | undefined) =>
  options.find((o) => o.value === value)?.label ?? value ?? ''

// Three answers, not two: "never asked" is the one that produces the next
// approach, so it is shown rather than left blank.
export function freelancerAnswer(value: boolean | null | undefined): { label: string; tone?: 'success' | 'accent' } {
  if (value === true) return { label: 'Works with freelancers', tone: 'success' }
  if (value === false) return { label: 'Does not use freelancers' }
  return { label: 'Never asked about freelancers', tone: 'accent' }
}

export type ContactFilters = {
  q?: string
  status?: Lifecycle
  relation?: Relation
  page?: number
}

// Sorted by name on the server.
export const contactsQuery = (api: Api, { q, status, relation, page = 1 }: ContactFilters) =>
  queryOptions({
    queryKey: ['contacts', 'list', { q, status, relation, page }],
    queryFn: () =>
      unwrap(
        api.GET('/contacts/', {
          params: {
            query: {
              search: q || undefined,
              lifecycle_status: status,
              relation_type: relation,
              skip: (page - 1) * PAGE_SIZE,
              limit: PAGE_SIZE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

export const contactQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['contacts', 'detail', id],
    queryFn: () => unwrap(api.GET('/contacts/{contact_id}', { params: { path: { contact_id: id } } })),
  })

// Suggestions for a contact picker, by name. Ten is plenty for a dropdown.
export const contactOptionsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['contacts', 'options', search],
    queryFn: () => unwrap(api.GET('/contacts/', { params: { query: { search: search || undefined, limit: 10 } } })),
    placeholderData: keepPreviousData,
  })

export const createContact = (api: Api, body: ContactCreate) => unwrap(api.POST('/contacts/', { body }))

// Every field is sent, so a field emptied in the form is cleared (null).
export const updateContact = (api: Api, id: string, body: ContactCreate) =>
  unwrap(api.PATCH('/contacts/{contact_id}', { params: { path: { contact_id: id } }, body }))

export const deleteContact = (api: Api, id: string) =>
  unwrap(api.DELETE('/contacts/{contact_id}', { params: { path: { contact_id: id } } }))

// A contact write changes every contact list, and the contact count on its
// organization (old and new, after a move), so organizations go too.
export const invalidateContacts = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['contacts'] }),
    queryClient.invalidateQueries({ queryKey: ['organizations'] }),
  ])

// The record page's tabs: each linked type filtered by contact_id.
const linked = (id: string) => ({ params: { query: { contact_id: id, limit: DETAIL_LIMIT } } })

export const contactInteractionsQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['interactions', 'by-contact', id],
    queryFn: () => unwrap(api.GET('/interactions/', linked(id))),
  })

export const contactDocumentsQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['documents', 'by-contact', id],
    queryFn: () => unwrap(api.GET('/documents/', linked(id))),
  })
