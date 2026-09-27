import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { useState } from 'react'
import { ApiError, unwrap } from '../../../api/client'
import { TaskForm, type TaskFields } from '../../../components/TaskForm'
import { Button } from '../../../components/ui/Button'
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog'
import { formatDay, localDay } from '../../../format'
import { deleteTask, invalidateTasks, taskQuery, updateTask } from '../../../tasks'

// A task is small enough that its page is its form: open it to read it,
// change it, or delete it.
export const Route = createFileRoute('/_authed/tasks/$taskId')({
  component: EditTask,
})

function EditTask() {
  const { api } = Route.useRouteContext()
  const { taskId } = Route.useParams()
  const filters = Route.useSearch()
  const queryClient = useQueryClient()
  const task = useQuery(taskQuery(api, taskId))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [repeated, setRepeated] = useState<string | null>(null)

  const leave = useLeave({ to: '/tasks', search: filters })

  const save = useMutation({
    mutationFn: (body: TaskFields) => updateTask(api, taskId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(taskQuery(api, taskId).queryKey, saved)
      await invalidateTasks(queryClient)
      await leave()
    },
  })

  const remove = useMutation({
    mutationFn: () => deleteTask(api, taskId),
    onSuccess: async () => {
      await leave()
      queryClient.removeQueries({ queryKey: taskQuery(api, taskId).queryKey })
      await invalidateTasks(queryClient)
    },
  })

  // Done / not done from the page itself, without going through the form.
  const toggle = useMutation({
    mutationFn: (done: boolean) =>
      unwrap(api.PATCH('/tasks/{task_id}', { params: { path: { task_id: taskId } }, body: { done } })),
    onSuccess: async (saved) => {
      setRepeated(saved.next_occurrence?.due_date ?? null)
      queryClient.setQueryData(taskQuery(api, taskId).queryKey, saved)
      await invalidateTasks(queryClient)
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/tasks" search={filters} className="back-link">
        ← Tasks
      </Link>
      <header className="page-header page-header-row">
        <h1>{task.data?.title ?? 'Task'}</h1>
        {task.data && (
          <Button variant={task.data.done ? 'quiet' : 'primary'} onPress={() => toggle.mutate(!task.data.done)} isDisabled={toggle.isPending}>
            {task.data.done ? 'Mark as not done' : 'Mark as done'}
          </Button>
        )}
      </header>
      {task.data?.done && <p className="notice">Done.</p>}
      {repeated && <p className="notice" role="status">Repeated: the next one is due {formatDay(localDay(repeated))}.</p>}
      {toggle.error && <p className="form-error" role="alert">{toggle.error.message}</p>}

      {task.isPending ? (
        <p className="muted">Loading…</p>
      ) : task.error ? (
        <p className="form-error">
          {task.error instanceof ApiError && task.error.status === 404
            ? 'This task does not exist, or was deleted.'
            : task.error.message}
        </p>
      ) : (
        <TaskForm
          // Remounted when a toggle replaces the task, so the form shows it.
          key={task.data.updated}
          initial={task.data}
          onSubmit={(body) => save.mutate(body)}
          submitLabel="Save changes"
          pending={save.isPending}
          error={save.error}
          cancel={
            <Button variant="quiet" onPress={() => void leave()}>
              Cancel
            </Button>
          }
          extraActions={
            <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
              Delete
            </Button>
          }
        />
      )}

      <ConfirmDialog
        title="Delete this task?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{task.data?.title}</strong> will be permanently deleted.
        </p>
      </ConfirmDialog>
    </div>
  )
}
