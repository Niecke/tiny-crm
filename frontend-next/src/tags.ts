import { type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'

export const tagsQuery = (api: Api) =>
  queryOptions({
    queryKey: ['tags'],
    queryFn: () => unwrap(api.GET('/tags')),
    staleTime: 60_000,
  })

export const invalidateTags = (queryClient: QueryClient) =>
  queryClient.invalidateQueries({ queryKey: ['tags'] })
