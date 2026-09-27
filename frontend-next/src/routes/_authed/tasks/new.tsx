import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { z } from 'zod'
import { TaskForm, type TaskFields, type TaskLinks } from '../../../components/TaskForm'
import { Button } from '../../../components/ui/Button'
import { contactQuery } from '../../../contacts'
import { createTask, invalidateTasks, taskQuery } from '../../../tasks'

// A new task opened from a record starts linked to it. The names travel with
// the ids so the pickers can show them without a request.
const searchSchema = z.object({
  contactId: z.string().optional().catch(undefined),
  contactName: z.string().optional().catch(undefined),
  dealId: z.string().optional().catch(undefined),
  dealTitle: z.string().optional().catch(undefined),
  interactionId: z.string().optional().catch(undefined),
  interactionSubject: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/tasks/new')({
  validateSearch: searchSchema,
  component: NewTask,
})

function NewTask() {
  const { api } = Route.useRouteContext()
  const { contactId, contactName, dealId, dealTitle, interactionId, interactionSubject, ...filters } =
    Route.useSearch()
  const queryClient = useQueryClient()

  // A follow-up from an interaction knows the contact's id but not the name;
  // the picker needs the name to show it, so it is looked up first.
  const contact = useQuery({ ...contactQuery(api, contactId ?? ''), enabled: Boolean(contactId && !contactName) })
  const links: TaskLinks = {
    contact: contactId ? { id: contactId, name: contactName ?? contact.data?.name ?? '' } : undefined,
    deal: dealId ? { id: dealId, title: dealTitle ?? '' } : undefined,
    interaction: interactionId ? { id: interactionId, subject: interactionSubject ?? '' } : undefined,
  }

  const leave = useLeave({ to: '/tasks', search: filters })

  const mutation = useMutation({
    mutationFn: (body: TaskFields) => createTask(api, body),
    onSuccess: async (task) => {
      queryClient.setQueryData(taskQuery(api, task.id).queryKey, task)
      await invalidateTasks(queryClient)
      await leave()
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/tasks" search={filters} className="back-link">
        ← Tasks
      </Link>
      <header className="page-header">
        <h1>New task</h1>
      </header>
      {contactId && !contactName && contact.isPending ? (
        <p className="muted">Loading…</p>
      ) : (
      <TaskForm
        links={links}
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Create task"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Button variant="quiet" onPress={() => void leave()}>
            Cancel
          </Button>
        }
      />
      )}
    </div>
  )
}
