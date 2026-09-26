import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { ProjectCreate, ProjectRead, ProjectUpdate } from './api/types'
import { PAGE_SIZE } from './contacts'

// Where a project stands, from its dates alone: finished once the end date
// has passed, upcoming until the start date, running in between.
export type ProjectStatus = 'active' | 'upcoming' | 'completed'

export const statusLabels: Record<ProjectStatus, string> = {
  active: 'Active',
  upcoming: 'Upcoming',
  completed: 'Completed',
}

const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function statusOf(p: Pick<ProjectRead, 'start_date' | 'end_date'>, on = today()): ProjectStatus {
  if (p.end_date && p.end_date < on) return 'completed'
  if (p.start_date > on) return 'upcoming'
  return 'active'
}

export const projectsQuery = (api: Api, { q, page = 1 }: { q?: string; page?: number }) =>
  queryOptions({
    queryKey: ['projects', 'list', { q, page }],
    queryFn: () =>
      unwrap(
        api.GET('/projects/', {
          params: { query: { search: q || undefined, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  })

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

export const createProject = (api: Api, body: ProjectCreate) => unwrap(api.POST('/projects/', { body }))

// Only the fields sent are changed; the link lists, when sent, replace what is
// stored.
export const updateProject = (api: Api, id: string, body: ProjectUpdate) =>
  unwrap(api.PATCH('/projects/{project_id}', { params: { path: { project_id: id } }, body }))

export const deleteProject = (api: Api, id: string) =>
  unwrap(api.DELETE('/projects/{project_id}', { params: { path: { project_id: id } } }))

// Documents list their projects too (project_ids), from the same link table.
export const invalidateProjects = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['projects'] }),
    queryClient.invalidateQueries({ queryKey: ['documents'], predicate: (q) => q.queryKey[1] !== 'content' && q.queryKey[1] !== 'preview' }),
  ])
