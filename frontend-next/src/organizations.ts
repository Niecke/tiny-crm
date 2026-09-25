import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { OrganizationCreate } from './api/types'

// The API caps a page at 200. A list this long is past scanning anyway, so the
// screen says how many it is not showing instead of paging through the rest.
export const LIST_LIMIT = 100
// Per tab on the detail page: enough to see what is going on with a company,
// and the total says when there is more.
export const DETAIL_LIMIT = 20

export const organizationsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['organizations', 'list', search],
    queryFn: () =>
      unwrap(api.GET('/organizations/', { params: { query: { limit: LIST_LIMIT, search: search || undefined } } })),
    // Keep the old rows on screen while the next search loads, instead of
    // flashing an empty list on every keystroke.
    placeholderData: keepPreviousData,
  })

export const organizationQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['organizations', 'detail', id],
    queryFn: () => unwrap(api.GET('/organizations/{organization_id}', { params: { path: { organization_id: id } } })),
  })

export const createOrganization = (api: Api, body: OrganizationCreate) =>
  unwrap(api.POST('/organizations/', { body }))

// Every field is sent, so a field emptied in the form is cleared (null) rather
// than left as it was.
export const updateOrganization = (api: Api, id: string, body: OrganizationCreate) =>
  unwrap(api.PATCH('/organizations/{organization_id}', { params: { path: { organization_id: id } }, body }))

// Contacts, interactions and documents each filter by organization_id. Three
// calls rather than one generic helper: each path is checked against the
// schema, and each result keeps its own row type.
const linked = (id: string) => ({ params: { query: { organization_id: id, limit: DETAIL_LIMIT } } })

export const orgContactsQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['contacts', 'by-organization', id],
    queryFn: () => unwrap(api.GET('/contacts/', linked(id))),
  })

// Newest first, planned entries included — the API's default order.
export const orgInteractionsQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['interactions', 'by-organization', id],
    queryFn: () => unwrap(api.GET('/interactions/', linked(id))),
  })

export const orgDocumentsQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['documents', 'by-organization', id],
    queryFn: () => unwrap(api.GET('/documents/', linked(id))),
  })
