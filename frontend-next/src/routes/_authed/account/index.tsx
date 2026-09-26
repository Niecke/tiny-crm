import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { meQuery } from '../../../auth'
import { formatDateTime, formatTimeAgo } from '../../../format'

export const Route = createFileRoute('/_authed/account/')({
  component: AccountPage,
})

// Who is signed in, and the one thing they can change about it. The guard has
// already loaded /users/me, so this renders from the cache without a request.
function AccountPage() {
  const { api } = Route.useRouteContext()
  const { data: me, error, isPending } = useQuery(meQuery(api))

  return (
    <div className="page page-narrow">
      <header className="page-header">
        <h1>Account</h1>
        <p>The user this browser is signed in as.</p>
      </header>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : (
        <section className="panel">
          <div className="panel-body">
            <ul className="rows">
              <Row label="Name">{me.name || <span className="muted">—</span>}</Row>
              <Row label="Email">{me.email}</Row>
              <Row label="Password last changed">
                {me.password_changed_at ? (
                  <>
                    {formatDateTime(me.password_changed_at)}{' '}
                    <span className="muted">· {formatTimeAgo(me.password_changed_at)}</span>
                  </>
                ) : (
                  <span className="muted">Never changed</span>
                )}
              </Row>
            </ul>
          </div>
        </section>
      )}

      <div className="form-actions account-actions">
        <Link to="/system" className="button button-quiet">
          System status
        </Link>
        <Link to="/account/password" className="button">
          Change password
        </Link>
      </div>
    </div>
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
