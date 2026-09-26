import { queryOptions, useIsFetching, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { type Api, unwrap } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { formatDateTime, formatTimeAgo } from '../../format'
import { useMediaQuery } from '../../useMediaQuery'

const repoUrl = 'https://github.com/Niecke/tiny-crm'

// This bundle's build, baked in by the Dockerfile. Both are unset on the dev
// server, and a locally built image carries a placeholder ("dev", "unknown")
// instead of a commit.
const frontendCommit = import.meta.env.VITE_GIT_COMMIT
const frontendBuilt = import.meta.env.VITE_BUILD_TIMESTAMP

const isCommit = (value: string | undefined): value is string => !!value && /^[0-9a-f]{7,40}$/.test(value)

// Which build is running and whether it can reach its database. Both endpoints
// are unauthenticated, so this page still answers when the login is broken.
// No retries: the page reports what it sees now, and Recheck asks again.
const versionQuery = (api: Api) =>
  queryOptions({
    queryKey: ['system', 'version'],
    queryFn: () => unwrap(api.GET('/version')),
    retry: false,
  })

const isHealthBody = (body: unknown): body is { status: string; db: string } =>
  typeof body === 'object' && body !== null && 'status' in body && 'db' in body

// A degraded backend answers 503 with the same body as a healthy one: that is
// a report, not a failure, so it resolves. Only an API that cannot be reached,
// or a 503 from something in front of it, lands in the error branch.
const healthQuery = (api: Api) =>
  queryOptions({
    queryKey: ['system', 'health'],
    queryFn: async () => {
      const started = performance.now()
      const request = api.GET('/health')
      const { error, response } = await request
      const responseMs = Math.round(performance.now() - started)
      const body = response.status === 503 && isHealthBody(error) ? error : await unwrap(request)
      return { status: body.status, db: body.db, responseMs }
    },
    retry: false,
    // A status page tends to be left open; keep it current without a click.
    refetchInterval: 30_000,
  })

// The frontend build the server hands out now. index.html revalidates on every
// load, but an open tab keeps running the bundle it started with until it is
// reloaded. version.json only exists in the image, so the dev server skips it.
const deployedQuery = queryOptions({
  queryKey: ['system', 'deployed'],
  queryFn: async () => {
    const res = await fetch(`${import.meta.env.BASE_URL}version.json`, { cache: 'no-cache' })
    if (!res.ok) throw new Error(`version.json → ${res.status}`)
    const { version } = (await res.json()) as { version?: unknown }
    if (typeof version !== 'string') throw new Error('version.json has no version')
    return version
  },
  enabled: import.meta.env.PROD,
  retry: false,
})

const clock = new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' })

type Tone = 'success' | 'warning' | 'danger' | undefined

export const Route = createFileRoute('/_authed/system')({
  component: SystemPage,
})

function SystemPage() {
  const { api, config } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const version = useQuery(versionQuery(api))
  const health = useQuery(healthQuery(api))
  const deployed = useQuery(deployedQuery)
  const checking = useIsFetching({ queryKey: ['system'] }) > 0
  const installed = useMediaQuery('(display-mode: standalone)')

  const backendCommit = version.data?.version
  const outdated = isCommit(frontendCommit) && deployed.isSuccess && deployed.data !== frontendCommit
  // A deploy ships both images from one commit. Compared with what is
  // deployed rather than with this tab: a stale tab is the reload note, not a
  // half-finished rollout.
  const liveFrontend = deployed.data ?? frontendCommit
  const split = isCommit(liveFrontend) && isCommit(backendCommit) && liveFrontend !== backendCommit

  const apiTone: Tone = health.isPending ? undefined : health.isError ? 'danger' : 'success'
  const dbTone: Tone = health.isSuccess ? (health.data.db === 'ok' ? 'success' : 'danger') : undefined
  const dbLabel = health.isPending
    ? 'Checking…'
    : health.isError
      ? 'Unknown'
      : health.data.db === 'ok'
        ? 'Connected'
        : 'Unreachable'
  const checkedAt = Math.max(health.dataUpdatedAt, health.errorUpdatedAt)

  const [tone, title, detail]: [Tone, string, string] = health.isPending
    ? [undefined, 'Checking…', 'Asking the API for its health.']
    : health.isError
      ? ['danger', 'API unreachable', 'Nothing can be loaded or saved until it answers again.']
      : health.data.db !== 'ok'
        ? ['danger', 'Database unreachable', 'The API answers but cannot reach its database, so nothing can be loaded or saved.']
        : ['success', 'Everything is running', 'The API answers and reaches its database.']

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>System</h1>
          <p>Which builds are running, and whether they can reach each other.</p>
        </div>
        <Button
          variant="quiet"
          isDisabled={checking}
          onPress={() => void queryClient.refetchQueries({ queryKey: ['system'] })}
        >
          {checking ? 'Checking…' : 'Recheck'}
        </Button>
      </header>

      <section className="panel system-status" aria-label="Status">
        <div className="system-verdict">
          <span className="status-dot" data-tone={tone} aria-hidden="true" />
          <div className="row-main" role="status">
            <h2>{title}</h2>
            <p className="muted small">{detail}</p>
            {health.isError && <p className="mono small muted">{health.error.message}</p>}
          </div>
          {checkedAt > 0 && <span className="muted small system-checked">Checked {clock.format(checkedAt)}</span>}
        </div>

        <ol className="status-chain">
          <ChainNode name="Frontend" tone={outdated ? 'warning' : 'success'}>
            {outdated ? 'Outdated' : deployed.isSuccess ? 'Up to date' : 'Running'}
          </ChainNode>
          <ChainNode name="API" tone={apiTone}>
            {health.isPending ? 'Checking…' : health.isError ? 'Unreachable' : `${health.data.responseMs} ms`}
          </ChainNode>
          <ChainNode name="Database" tone={dbTone}>
            {dbLabel}
          </ChainNode>
        </ol>

        {outdated && (
          <div className="system-note">
            <p>
              A new frontend build is live: <Commit sha={deployed.data} />. This tab still runs{' '}
              <Commit sha={frontendCommit} />.
            </p>
            <Button variant="quiet" onPress={() => window.location.reload()}>
              Reload
            </Button>
          </div>
        )}
        {split && (
          <div className="system-note">
            <p>
              Frontend (<Commit sha={liveFrontend} />) and backend (<Commit sha={backendCommit} />) run different
              builds. A deploy ships both from one commit, so one of them has not rolled out.
            </p>
          </div>
        )}
      </section>

      <div className="system-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Frontend</h2>
          </div>
          <div className="panel-body">
            <ul className="rows">
              <Row label="Commit">
                <Commit sha={frontendCommit} />
              </Row>
              <Row label="Built">
                <BuiltAt iso={frontendBuilt} />
              </Row>
              <Row label="Mode">{import.meta.env.MODE}</Row>
              {/* The share target only exists in the installed app. */}
              <Row label="Running as">{installed ? 'Installed app' : 'Browser tab'}</Row>
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Backend</h2>
          </div>
          <div className="panel-body">
            <ul className="rows">
              <Row label="Health">
                <span className="badge" data-tone={tone}>
                  {health.isPending
                    ? 'Checking…'
                    : health.isError
                      ? 'Unreachable'
                      : health.data.status === 'ok'
                        ? 'Healthy'
                        : 'Degraded'}
                </span>
              </Row>
              <Row label="Database">
                <span className="badge" data-tone={dbTone}>
                  {dbLabel}
                </span>
              </Row>
              <Row label="Response time">
                {health.isSuccess ? `${health.data.responseMs} ms` : <span className="muted">—</span>}
              </Row>
              <Row label="Commit">
                {version.isPending ? (
                  <span className="muted">…</span>
                ) : version.isError ? (
                  <span className="muted">—</span>
                ) : (
                  <Commit sha={backendCommit} />
                )}
              </Row>
              <Row label="Built">
                <BuiltAt iso={version.data?.build_timestamp} />
              </Row>
              <Row label="API">
                <span className="mono">{config.apiUrl}</span>
              </Row>
            </ul>
          </div>
        </section>
      </div>
    </div>
  )
}

// One stop on the way from this tab to the data. The line into a stop takes
// its tone: the line into the API is whether the API answers, the line into
// the database whether the API reaches it.
function ChainNode({ name, tone, children }: { name: string; tone: Tone; children: ReactNode }) {
  return (
    <li className="status-node" data-tone={tone}>
      <span className="status-dot" data-tone={tone} aria-hidden="true" />
      <span className="status-node-name">{name}</span>
      <span className="status-node-detail">{children}</span>
    </li>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <li>
      <span className="label">{label}</span>
      <span>{children}</span>
    </li>
  )
}

// A commit, short, linked to it on GitHub. A local build's placeholder is shown
// as it is.
function Commit({ sha }: { sha: string | undefined }) {
  if (!isCommit(sha)) return <span className="muted">{sha ?? 'dev'}</span>
  return (
    <a className="mono" href={`${repoUrl}/commit/${sha}`} target="_blank" rel="noreferrer" title={sha}>
      {sha.slice(0, 7)}
    </a>
  )
}

// A build time, or a dash where a local build has none ("unknown", unset).
function BuiltAt({ iso }: { iso: string | undefined }) {
  if (!iso || Number.isNaN(Date.parse(iso))) return <span className="muted">—</span>
  return (
    <>
      {formatDateTime(iso)} <span className="muted">· {formatTimeAgo(iso)}</span>
    </>
  )
}
