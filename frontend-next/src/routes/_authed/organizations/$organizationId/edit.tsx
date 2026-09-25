import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { OrganizationForm } from '../../../../components/OrganizationForm'
import type { OrganizationCreate } from '../../../../api/types'
import { organizationQuery, updateOrganization } from '../../../../organizations'

export const Route = createFileRoute('/_authed/organizations/$organizationId/edit')({
  component: EditOrganization,
})

function EditOrganization() {
  const { api } = Route.useRouteContext()
  const { organizationId } = Route.useParams()
  const { q } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const org = useQuery(organizationQuery(api, organizationId))

  const backToDetail = { to: '/organizations/$organizationId', params: { organizationId }, search: { q } } as const

  const mutation = useMutation({
    mutationFn: (body: OrganizationCreate) => updateOrganization(api, organizationId, body),
    onSuccess: async (updated) => {
      queryClient.setQueryData(organizationQuery(api, organizationId).queryKey, updated)
      // Name, domain and industry show in the list.
      await queryClient.invalidateQueries({ queryKey: ['organizations', 'list'] })
      await navigate({ ...backToDetail, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link {...backToDetail} className="back-link">
        ← {org.data?.name ?? 'Organization'}
      </Link>
      <header className="page-header">
        <h1>Edit organization</h1>
      </header>
      {org.isPending ? (
        <p className="muted">Loading…</p>
      ) : org.error ? (
        <p className="form-error">{org.error.message}</p>
      ) : (
        <OrganizationForm
          initial={org.data}
          onSubmit={(body) => mutation.mutate(body)}
          submitLabel="Save changes"
          pending={mutation.isPending}
          error={mutation.error}
          cancel={
            <Link {...backToDetail} className="button button-quiet">
              Cancel
            </Link>
          }
        />
      )}
    </div>
  )
}
