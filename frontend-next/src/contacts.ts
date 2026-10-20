import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { ContactCreate, TimelineItemType, VCardImportSummary } from './api/types'
import { saveBlob } from './download'

// Rows per page on every paged list (FRONTEND.md, "Paging").
export const PAGE_SIZE = 25

// Rows a picker's dropdown asks for. The list scrolls, so this is more than
// anyone reads through; past it the dropdown says how many it left out rather
// than looking complete (#228).
export const PICKER_LIMIT = 50

// How many matches a picker's page did not bring along.
export const notShown = (page: { total: number; items: unknown[] } | undefined) =>
  page ? Math.max(0, page.total - page.items.length) : 0

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
  // The archive instead of the list (#140).
  archived?: boolean
  page?: number
}

// Sorted by name on the server.
export const contactsQuery = (api: Api, { q, status, relation, archived, page = 1 }: ContactFilters) =>
  queryOptions({
    queryKey: ['contacts', 'list', { q, status, relation, archived, page }],
    queryFn: () =>
      unwrap(
        api.GET('/contacts/', {
          params: {
            query: {
              search: q || undefined,
              lifecycle_status: status,
              relation_type: relation,
              archived: archived || undefined,
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

export type TimelineFilters = {
  types?: TimelineItemType[]
  archived?: boolean
}

export const contactTimelineQuery = (
  api: Api,
  contactId: string,
  filter?: TimelineFilters,
  page = 1,
) =>
  queryOptions({
    queryKey: ['contacts', 'timeline', contactId, filter, page],
    queryFn: () =>
      unwrap(
        api.GET('/contacts/{contact_id}/timeline', {
          params: {
            path: { contact_id: contactId },
            query: {
              types: filter?.types,
              archived: filter?.archived ?? false,
              skip: (page - 1) * PAGE_SIZE,
              limit: PAGE_SIZE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

// Suggestions for a contact picker, by name.
export const contactOptionsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['contacts', 'options', search],
    queryFn: () => unwrap(api.GET('/contacts/', { params: { query: { search: search || undefined, limit: PICKER_LIMIT } } })),
    placeholderData: keepPreviousData,
  })

export const createContact = (api: Api, body: ContactCreate) => unwrap(api.POST('/contacts/', { body }))

// Every field is sent, so a field emptied in the form is cleared (null).
// `version` makes the save conditional — see useEditVersion (#142).
export const updateContact = (api: Api, id: string, body: ContactCreate, version?: number) =>
  unwrap(api.PATCH('/contacts/{contact_id}', { params: { path: { contact_id: id } }, body: { ...body, version } }))

export const deleteContact = (api: Api, id: string) =>
  unwrap(api.DELETE('/contacts/{contact_id}', { params: { path: { contact_id: id } } }))

export const archiveContact = (api: Api, id: string) =>
  unwrap(api.POST('/contacts/{contact_id}/archive', { params: { path: { contact_id: id } } }))

export const restoreContact = (api: Api, id: string) =>
  unwrap(api.POST('/contacts/{contact_id}/restore', { params: { path: { contact_id: id } } }))

export async function importContactsVcard(api: Api, file: File): Promise<VCardImportSummary> {
  const form = new FormData()
  form.append('file', file)
  return unwrap(
    api.POST('/contacts/import/vcard', {
      body: {} as never,
      bodySerializer: () => form,
    }),
  )
}

// The cards are behind the login, so they are fetched with the token as blobs
// and saved from there, like a document's file.
export async function exportContactVcard(api: Api, contactId: string, filename = 'contact.vcf') {
  const blob = (await unwrap(
    api.GET('/contacts/{contact_id}/vcard', {
      params: { path: { contact_id: contactId } },
      parseAs: 'blob',
    }),
  )) as unknown as Blob
  saveBlob(blob, filename)
}

export async function exportAllContactsVcard(api: Api, archived = false) {
  const blob = (await unwrap(
    api.GET('/contacts/vcard', {
      params: { query: { archived } },
      parseAs: 'blob',
    }),
  )) as unknown as Blob
  saveBlob(blob, archived ? 'contacts-archived.vcf' : 'contacts.vcf')
}

// A contact write changes every contact list, and the contact count on its
// organization (old and new, after a move), so organizations go too.
export const invalidateContacts = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['contacts'] }),
    queryClient.invalidateQueries({ queryKey: ['organizations'] }),
    queryClient.invalidateQueries({ queryKey: ['tags'] }),
  ])
