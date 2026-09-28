import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import type { WatchCreate } from '../../../../api/types'
import { WatchForm } from '../../../../components/WatchForm'
import { invalidateWatches, updateWatch, watchQuery } from '../../../../watches'

export const Route = createFileRoute('/_authed/watches/$watchId/edit')({
  component: EditWatch,
})

function EditWatch() {
  const { api } = Route.useRouteContext()
  const { watchId } = Route.useParams()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const watch = useQuery(watchQuery(api, watchId))
  const mutation = useMutation({
    mutationFn: (body: WatchCreate) => updateWatch(api, watchId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(watchQuery(api, watchId).queryKey, saved)
      await invalidateWatches(queryClient)
      await navigate({ to: '/watches/$watchId', params: { watchId }, search: filters, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/watches/$watchId" params={{ watchId }} search={filters} className="back-link">
        ← {watch.data?.name ?? 'Source'}
      </Link>
      <header className="page-header">
        <h1>Edit source</h1>
      </header>
      {watch.isPending ? (
        <p className="muted">Loading…</p>
      ) : watch.error ? (
        <p className="form-error">{watch.error.message}</p>
      ) : (
        <WatchForm
          initial={watch.data}
          onSubmit={(body) => mutation.mutate(body)}
          submitLabel="Save changes"
          pending={mutation.isPending}
          error={mutation.error}
          cancel={
            <Link to="/watches/$watchId" params={{ watchId }} search={filters} className="button button-quiet">
              Cancel
            </Link>
          }
        />
      )}
    </div>
  )
}
