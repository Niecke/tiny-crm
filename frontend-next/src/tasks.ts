import { keepPreviousData, type QueryClient, queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { type Api, unwrap } from './api/client'
import type { TaskCreate, TaskRead, TaskUpdate } from './api/types'
import { PAGE_SIZE } from './contacts'

// Priority is 0–2 on the model. Low is the default and says nothing, so only
// Medium and High get a badge (PriorityBadge); the text is always there, since
// colour alone fails in grey print and for colour-blind readers (#137).
export const priorityOptions = [
  { value: '0', label: 'Low' },
  { value: '1', label: 'Medium' },
  { value: '2', label: 'High' },
] as const

type Rule = NonNullable<TaskCreate['recurrence_rule']>

export const recurrenceOptions: { value: Rule; label: string; unit: string; units: string }[] = [
  { value: 'daily', label: 'Daily', unit: 'day', units: 'days' },
  { value: 'weekly', label: 'Weekly', unit: 'week', units: 'weeks' },
  { value: 'monthly', label: 'Monthly', unit: 'month', units: 'months' },
  { value: 'yearly', label: 'Yearly', unit: 'year', units: 'years' },
]

export const MAX_RECURRENCE_INTERVAL = 366

// "Repeats weekly", "Repeats every 2 months until 31 Dec 2026".
export function recurrenceLabel(
  task: Pick<TaskRead, 'recurrence_rule' | 'recurrence_interval' | 'recurrence_until'>,
  formatDay: (iso: string) => string,
): string | null {
  const rule = recurrenceOptions.find((o) => o.value === task.recurrence_rule)
  if (!rule) return null
  const every = task.recurrence_interval === 1 ? rule.label.toLowerCase() : `every ${task.recurrence_interval} ${rule.units}`
  return task.recurrence_until ? `Repeats ${every} until ${formatDay(task.recurrence_until)}` : `Repeats ${every}`
}

// Past its due moment and not done. Due dates are filed as 23:59 local, so a
// task due today is not late until the day is over.
export const isOverdue = (task: Pick<TaskRead, 'done' | 'due_date'>, now = Date.now()) =>
  !task.done && task.due_date !== null && task.due_date !== undefined && Date.parse(task.due_date) < now

export type TaskFilters = { q?: string; done?: boolean; page?: number }

// Soonest due first, undated last — the API's order.
export const tasksQuery = (api: Api, { q, done, page = 1 }: TaskFilters) =>
  queryOptions({
    queryKey: ['tasks', 'list', { q, done, page }],
    queryFn: () =>
      unwrap(
        api.GET('/tasks/', {
          params: {
            query: {
              search: q || undefined,
              include_done: done || undefined,
              skip: (page - 1) * PAGE_SIZE,
              limit: PAGE_SIZE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

export const taskQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['tasks', 'detail', id],
    queryFn: () => unwrap(api.GET('/tasks/{task_id}', { params: { path: { task_id: id } } })),
  })

// The tasks on one record page. Done ones only on request.
export const linkedTasksQuery = (
  api: Api,
  link: { contact_id?: string; deal_id?: string; interaction_id?: string },
  includeDone: boolean,
) =>
  queryOptions({
    queryKey: ['tasks', 'linked', link, includeDone],
    queryFn: () =>
      unwrap(api.GET('/tasks/', { params: { query: { ...link, include_done: includeDone || undefined, limit: 50 } } })),
  })

export const createTask = (api: Api, body: Omit<TaskCreate, 'done'>) =>
  unwrap(api.POST('/tasks/', { body: { ...body, done: false } }))

export const updateTask = (api: Api, id: string, body: TaskUpdate) =>
  unwrap(api.PATCH('/tasks/{task_id}', { params: { path: { task_id: id } }, body }))

export const deleteTask = (api: Api, id: string) =>
  unwrap(api.DELETE('/tasks/{task_id}', { params: { path: { task_id: id } } }))

// A task write changes every task list, the record pages' task tabs (all under
// ['tasks']) and the dashboard briefing.
export const invalidateTasks = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['tasks'] }),
    queryClient.invalidateQueries({ queryKey: ['briefing'] }),
  ])

// Ticking a task off, wherever it is listed. Completing a repeating task
// leaves it as history and creates the next instance; the server decides
// whether the series has one left (recurrence_until), so the answer is shown
// rather than assumed: `repeated` is the new instance's due date. It lives
// with the list, not the row, because the row is gone once the list refetches.
export function useToggleDone(api: Api) {
  const queryClient = useQueryClient()
  const [repeated, setRepeated] = useState<{ title: string; due: string } | null>(null)
  const mutation = useMutation({
    mutationFn: (task: TaskRead) =>
      unwrap(api.PATCH('/tasks/{task_id}', { params: { path: { task_id: task.id } }, body: { done: !task.done } })),
    onSuccess: async (saved) => {
      const next = saved.next_occurrence
      setRepeated(next?.due_date ? { title: next.title, due: next.due_date } : null)
      await invalidateTasks(queryClient)
    },
  })
  return { toggle: mutation.mutate, pendingId: mutation.isPending ? mutation.variables?.id : undefined, error: mutation.error, repeated }
}
