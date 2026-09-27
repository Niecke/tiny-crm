import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { useState } from 'react'
import { ApiError } from '../../../api/client'
import type { InteractionCreate } from '../../../api/types'
import { InteractionForm } from '../../../components/InteractionForm'
import { Button } from '../../../components/ui/Button'
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog'
import {
  deleteInteraction,
  interactionQuery,
  invalidateInteractions,
  updateInteraction,
} from '../../../interactions'

// An interaction's page is its form: read it, change it, delete it, or turn
// it into a follow-up task.
export const Route = createFileRoute('/_authed/interactions/$interactionId')({
  component: EditInteraction,
})

function EditInteraction() {
  const { api } = Route.useRouteContext()
  const { interactionId } = Route.useParams()
  const filters = Route.useSearch()
  const queryClient = useQueryClient()
  const interaction = useQuery(interactionQuery(api, interactionId))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const leave = useLeave({ to: '/interactions', search: filters })

  const save = useMutation({
    mutationFn: (body: InteractionCreate) => updateInteraction(api, interactionId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(interactionQuery(api, interactionId).queryKey, saved)
      await invalidateInteractions(queryClient)
      await leave()
    },
  })

  const remove = useMutation({
    mutationFn: () => deleteInteraction(api, interactionId),
    onSuccess: async () => {
      await leave()
      queryClient.removeQueries({ queryKey: interactionQuery(api, interactionId).queryKey })
      await invalidateInteractions(queryClient)
    },
  })

  const i = interaction.data

  return (
    <div className="page page-narrow">
      <Link to="/interactions" search={filters} className="back-link">
        ← Interactions
      </Link>
      <header className="page-header page-header-row">
        <h1>{i?.subject ?? 'Interaction'}</h1>
        {i && (
          <Link
            to="/tasks/new"
            search={{ interactionId: i.id, interactionSubject: i.subject, contactId: i.contact_ids[0] }}
            className="button button-quiet"
          >
            Follow up
          </Link>
        )}
      </header>

      {interaction.isPending ? (
        <p className="muted">Loading…</p>
      ) : interaction.error ? (
        <p className="form-error">
          {interaction.error instanceof ApiError && interaction.error.status === 404
            ? 'This interaction does not exist, or was deleted.'
            : interaction.error.message}
        </p>
      ) : (
        <InteractionForm
          key={interaction.data.updated_at}
          initial={interaction.data}
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
        title="Delete this interaction?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{i?.subject}</strong> will be permanently deleted. Tasks following up on it are kept.
        </p>
      </ConfirmDialog>
    </div>
  )
}
