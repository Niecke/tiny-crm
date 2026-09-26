import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useCanGoBack, useNavigate, useRouter } from '@tanstack/react-router'
import { z } from 'zod'
import type { InteractionCreate } from '../../../api/types'
import { InteractionForm } from '../../../components/InteractionForm'
import { Button } from '../../../components/ui/Button'
import { createInteraction, interactionQuery, invalidateInteractions } from '../../../interactions'

// Logged from a record page, the entry starts linked to that record, and
// saving goes back there.
const searchSchema = z.object({
  contactId: z.string().optional().catch(undefined),
  organizationId: z.string().optional().catch(undefined),
  dealId: z.string().optional().catch(undefined),
  projectId: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/interactions/new')({
  validateSearch: searchSchema,
  component: NewInteraction,
})

function NewInteraction() {
  const { api } = Route.useRouteContext()
  const { contactId, organizationId, dealId, projectId, ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const router = useRouter()
  const canGoBack = useCanGoBack()
  const queryClient = useQueryClient()
  const leave = () => (canGoBack ? router.history.back() : navigate({ to: '/interactions', search: filters }))

  const mutation = useMutation({
    mutationFn: (body: InteractionCreate) => createInteraction(api, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(interactionQuery(api, saved.id).queryKey, saved)
      await invalidateInteractions(queryClient)
      await leave()
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/interactions" search={filters} className="back-link">
        ← Interactions
      </Link>
      <header className="page-header">
        <h1>Log interaction</h1>
      </header>
      <InteractionForm
        preset={{ contact_id: contactId, organization_id: organizationId, deal_id: dealId, project_id: projectId }}
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Save"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Button variant="quiet" onPress={() => void leave()}>
            Cancel
          </Button>
        }
      />
    </div>
  )
}
