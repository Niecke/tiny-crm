import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'

export const projectQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['projects', 'detail', id],
    queryFn: () => unwrap(api.GET('/projects/{project_id}', { params: { path: { project_id: id } } })),
  })

// Suggestions for a project picker, by name. Ten is plenty for a dropdown.
export const projectOptionsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['projects', 'options', search],
    queryFn: () => unwrap(api.GET('/projects/', { params: { query: { search: search || undefined, limit: 10 } } })),
    placeholderData: keepPreviousData,
  })
