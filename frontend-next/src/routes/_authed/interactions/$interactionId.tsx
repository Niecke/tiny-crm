import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { ApiError } from '../../../api/client'
import type { InteractionCreate } from '../../../api/types'
import { ArchiveButton, ArchivedNotice, ReadOnlyWhenArchived } from '../../../components/Archive'
import { useArchive } from '../../../useArchive'
import { InteractionForm } from '../../../components/InteractionForm'
import { Button } from '../../../components/ui/Button'
import {
  archiveInteraction,
  deleteInteraction,
  interactionQuery,
  invalidateInteractions,
  restoreInteraction,
  updateInteraction,
} from '../../../interactions'
import { StaleSaveNotice } from '../../../components/StaleSaveNotice'
import { formError } from '../../../useEditVersion'

// An interaction's page is its form: read it, change it, archive it, or turn
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
  const leave = useLeave({ to: '/interactions', search: filters })

  // The form below is remounted whenever the interaction changes, so the version on
  // screen is always the one it was filled from (#142, see useEditVersion).
  const save = useMutation({
    mutationFn: (body: InteractionCreate) => updateInteraction(api, interactionId, body, interaction.data?.version),
    onSuccess: async (saved) => {
      queryClient.setQueryData(interactionQuery(api, interactionId).queryKey, saved)
      await invalidateInteractions(queryClient)
      await leave()
    },
  })

  const archiving = useArchive({
    queryKey: interactionQuery(api, interactionId).queryKey,
    archive: () => archiveInteraction(api, interactionId),
    restore: () => restoreInteraction(api, interactionId),
    remove: () => deleteInteraction(api, interactionId),
    leave,
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
      <StaleSaveNotice error={save.error} onReload={() => void interaction.refetch().then(() => save.reset())} />
      {i && (
        <ArchivedNotice record={i} noun="interaction" name={i.subject} archiving={archiving}>
          Tasks following up on it are kept.
        </ArchivedNotice>
      )}

      {interaction.isPending ? (
        <p className="muted">Loading…</p>
      ) : interaction.error ? (
        <p className="form-error">
          {interaction.error instanceof ApiError && interaction.error.status === 404
            ? 'This interaction does not exist, or was deleted.'
            : interaction.error.message}
        </p>
      ) : (
        <ReadOnlyWhenArchived record={interaction.data}>
          <InteractionForm
            key={interaction.data.updated_at}
            initial={interaction.data}
            onSubmit={(body) => save.mutate(body)}
            submitLabel="Save changes"
            pending={save.isPending}
            error={formError(save.error)}
            cancel={
              <Button variant="quiet" onPress={() => void leave()}>
                Cancel
              </Button>
            }
            extraActions={!interaction.data.archived_at && <ArchiveButton archiving={archiving} />}
          />
        </ReadOnlyWhenArchived>
      )}
    </div>
  )
}
