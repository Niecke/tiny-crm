import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { OrganizationForm } from '../../../components/OrganizationForm'
import type { OrganizationCreate } from '../../../api/types'
import { createOrganization, organizationQuery } from '../../../organizations'

export const Route = createFileRoute('/_authed/organizations/new')({
  component: NewOrganization,
})

function NewOrganization() {
  const { api } = Route.useRouteContext()
  const { q } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (body: OrganizationCreate) => createOrganization(api, body),
    onSuccess: async (org) => {
      // Seeded from the POST response, so the detail page renders at once
      // instead of showing "Loading…"; every list, whatever its search, is
      // stale now.
      queryClient.setQueryData(organizationQuery(api, org.id).queryKey, org)
      await queryClient.invalidateQueries({ queryKey: ['organizations', 'list'] })
      await navigate({
        to: '/organizations/$organizationId',
        params: { organizationId: org.id },
        search: { q },
        replace: true,
      })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/organizations" search={{ q }} className="back-link">
        ← Organizations
      </Link>
      <header className="page-header">
        <h1>New organization</h1>
      </header>
      <OrganizationForm
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Create organization"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Link to="/organizations" search={{ q }} className="button button-quiet">
            Cancel
          </Link>
        }
      />
    </div>
  )
}
