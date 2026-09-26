import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import type { DealCreate } from '../../../api/types'
import { DealForm } from '../../../components/DealForm'
import { createDeal, dealQuery, invalidateDeals } from '../../../deals'

export const Route = createFileRoute('/_authed/deals/new')({
  component: NewDeal,
})

function NewDeal() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (body: DealCreate) => createDeal(api, body),
    onSuccess: async (deal) => {
      queryClient.setQueryData(dealQuery(api, deal.id).queryKey, deal)
      await invalidateDeals(queryClient)
      await navigate({ to: '/deals/$dealId', params: { dealId: deal.id }, search: filters, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/deals" search={filters} className="back-link">
        ← Deals
      </Link>
      <header className="page-header">
        <h1>New deal</h1>
      </header>
      <DealForm
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Create deal"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Link to="/deals" search={filters} className="button button-quiet">
            Cancel
          </Link>
        }
      />
    </div>
  )
}
