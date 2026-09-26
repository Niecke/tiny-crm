import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import type { WatchCreate } from '../../../api/types'
import { WatchForm } from '../../../components/WatchForm'
import { createWatch, invalidateWatches, watchQuery } from '../../../watches'

export const Route = createFileRoute('/_authed/watches/new')({
  component: NewWatch,
})

function NewWatch() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (body: WatchCreate) => createWatch(api, body),
    onSuccess: async (watch) => {
      queryClient.setQueryData(watchQuery(api, watch.id).queryKey, watch)
      await invalidateWatches(queryClient)
      await navigate({ to: '/watches/$watchId', params: { watchId: watch.id }, search: filters, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/watches" search={filters} className="back-link">
        ← Watches
      </Link>
      <header className="page-header">
        <h1>New source</h1>
        <p>A new source is due at once, so the first sweep shows up straight away.</p>
      </header>
      <WatchForm
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Add source"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Link to="/watches" search={filters} className="button button-quiet">
            Cancel
          </Link>
        }
      />
    </div>
  )
}
