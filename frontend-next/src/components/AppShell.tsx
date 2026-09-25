import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, type LinkProps, useRouteContext, useRouter } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { meQuery } from '../auth'
import { clearToken } from '../token'

// Every screen the Flutter app has, in its order. `to` is set once a screen is
// ported; until then the entry stays visible but inert, so the nav doubles as
// the parity checklist.
const nav: { label: string; to?: LinkProps['to'] }[] = [
  { label: 'Dashboard', to: '/' },
  { label: 'Inbox' },
  { label: 'Organizations' },
  { label: 'Deals' },
  { label: 'Projects' },
  { label: 'Interactions' },
  { label: 'Documents' },
  { label: 'Watches' },
  { label: 'Account' },
  { label: 'System', to: '/system' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { config } = useRouteContext({ from: '/_authed' })
  const { data: me } = useQuery(meQuery(config.apiUrl))
  const queryClient = useQueryClient()
  const router = useRouter()

  // The JWT is stateless, so there is nothing to revoke server-side: dropping
  // the token is the logout. The cache goes last, after the protected page
  // has unmounted, so nothing refetches in between.
  async function logout() {
    clearToken()
    await router.navigate({ to: '/login' })
    queryClient.clear()
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">tinyCRM</div>
        <nav className="nav" aria-label="Main">
          {nav.map((item) =>
            item.to ? (
              // Active matching is by prefix, so / needs to be exact or it
              // would stay highlighted on every page.
              <Link
                key={item.label}
                to={item.to}
                activeOptions={{ exact: item.to === '/' }}
                className="nav-link"
              >
                {item.label}
              </Link>
            ) : (
              <span key={item.label} className="nav-link" aria-disabled="true" title="Not ported yet">
                {item.label}
              </span>
            ),
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-meta">
            <div className="sidebar-user" title={me?.email}>
              {me?.name ?? me?.email}
            </div>
            <div>React preview · #122</div>
          </div>
          <button className="button button-quiet" type="button" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
