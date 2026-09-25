import { queryOptions, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

// Placeholder until the inbox slice lands. /version is unauthenticated, so it
// proves the config → fetch → query cache path without the login in between.
type Version = { version: string; build_timestamp: string }

const versionQuery = (apiUrl: string) =>
  queryOptions({
    queryKey: ['version', apiUrl],
    queryFn: async (): Promise<Version> => {
      const res = await fetch(`${apiUrl}/version`)
      if (!res.ok) throw new Error(`GET /version → ${res.status}`)
      return res.json()
    },
  })

type Health = { status: string; db: string; timestamp: string }

const healthQuery = (apiUrl: string) =>
  queryOptions({
    queryKey: ['health', apiUrl],
    queryFn: async (): Promise<Health> => {
      const res = await fetch(`${apiUrl}/health`)
      if (!res.ok) throw new Error(`GET /health -> ${res.status}`)
      return res.json()
    }
  })

export const Route = createFileRoute('/')({
  component: Home,
})

function Home() {
  const { config } = Route.useRouteContext()
  const { data, error, isPending } = useQuery(versionQuery(config.apiUrl))
  const {
    data: health,
    error: healthError,
    isPending: healthPending,
  } = useQuery(healthQuery(config.apiUrl))

  return (
    <main>
      <h1>tinyCRM</h1>
      <p>React skeleton — see #122.</p>
      <p>
        API {config.apiUrl}:{' '}
        {isPending ? 'checking…' : error ? error.message : `${data.version} (${data.build_timestamp})`}
      </p>
      <p>
        Backend Health
        {healthPending ? 'checking...' : healthError ? healthError.message : `status: ${health.status} | db: ${health.db}`}
      </p>
    </main>
  )
}
