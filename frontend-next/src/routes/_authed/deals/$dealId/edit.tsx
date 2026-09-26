import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import type { DealCreate } from '../../../../api/types'
import { DealForm } from '../../../../components/DealForm'
import { dealQuery, invalidateDeals, updateDeal } from '../../../../deals'

export const Route = createFileRoute('/_authed/deals/$dealId/edit')({
  component: EditDeal,
})

function EditDeal() {
  const { api } = Route.useRouteContext()
  const { dealId } = Route.useParams()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const deal = useQuery(dealQuery(api, dealId))

  const mutation = useMutation({
    mutationFn: (body: DealCreate) => updateDeal(api, dealId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(dealQuery(api, dealId).queryKey, saved)
      await invalidateDeals(queryClient)
      await navigate({ to: '/deals/$dealId', params: { dealId }, search: filters, replace: true })
    },
  })

  const back = (
    <Link to="/deals/$dealId" params={{ dealId }} search={filters} className="button button-quiet">
      Cancel
    </Link>
  )

  return (
    <div className="page page-narrow">
      <Link to="/deals/$dealId" params={{ dealId }} search={filters} className="back-link">
        ← {deal.data?.title ?? 'Deal'}
      </Link>
      <header className="page-header">
        <h1>Edit deal</h1>
      </header>
      {deal.isPending ? (
        <p className="muted">Loading…</p>
      ) : deal.error ? (
        <p className="form-error">{deal.error.message}</p>
      ) : (
        <DealForm
          initial={deal.data}
          onSubmit={(body) => mutation.mutate(body)}
          submitLabel="Save changes"
          pending={mutation.isPending}
          error={mutation.error}
          cancel={back}
        />
      )}
    </div>
  )
}
