import { queryOptions, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { type Api, unwrap } from '../../api/client'

// Which build is running and whether it can reach its database. Both endpoints
// are unauthenticated, so this page still answers when the login is broken.
const versionQuery = (api: Api) =>
  queryOptions({
    queryKey: ['version'],
    queryFn: () => unwrap(api.GET('/version')),
  })

// A degraded backend answers 503, which lands in the error branch.
const healthQuery = (api: Api) =>
  queryOptions({
    queryKey: ['health'],
    queryFn: () => unwrap(api.GET('/health')),
  })

export const Route = createFileRoute('/_authed/system')({
  component: SystemPage,
})

function SystemPage() {
  const { api, config } = Route.useRouteContext()
  const { data, error, isPending } = useQuery(versionQuery(api))
  const {
    data: health,
    error: healthError,
    isPending: healthPending,
  } = useQuery(healthQuery(api))

  return (
    <div className="page">
      <header className="page-header">
        <h1>System</h1>
        <p>Which builds are running, and whether they can reach each other.</p>
      </header>

      <section className="panel">
        <div className="panel-header">
          <h2>Frontend</h2>
        </div>
        <div className="panel-body">
          <ul className="rows">
            <li>
              <span className="label">Version</span>
              <span className="mono">{import.meta.env.VITE_GIT_COMMIT ?? 'dev'}</span>
            </li>
          </ul>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Backend</h2>
        </div>
        <div className="panel-body">
          <ul className="rows">
            <li>
              <span className="label">API</span>
              <span className="mono">{config.apiUrl}</span>
            </li>
            <li>
              <span className="label">Version</span>
              <span className="mono">
                {isPending ? 'checking…' : error ? error.message : `${data.version} (${data.build_timestamp})`}
              </span>
            </li>
            <li>
              <span className="label">Health</span>
              {healthPending ? (
                <span className="badge">checking…</span>
              ) : healthError ? (
                <span className="badge" data-tone="danger">
                  {healthError.message}
                </span>
              ) : (
                <span className="badge" data-tone={health.status === 'ok' ? 'success' : 'warning'}>
                  {health.status} · db {health.db}
                </span>
              )}
            </li>
          </ul>
        </div>
      </section>
    </div>
  )
}
