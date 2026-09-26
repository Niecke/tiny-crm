import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'

// Suggestions for a deal picker, by title. Ten is plenty for a dropdown.
export const dealOptionsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['deals', 'options', search],
    queryFn: () => unwrap(api.GET('/deals/', { params: { query: { search: search || undefined, limit: 10 } } })),
    placeholderData: keepPreviousData,
  })

export const dealQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['deals', 'detail', id],
    queryFn: () => unwrap(api.GET('/deals/{deal_id}', { params: { path: { deal_id: id } } })),
  })
