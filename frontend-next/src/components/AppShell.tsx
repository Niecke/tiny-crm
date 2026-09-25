import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, type LinkProps, useLocation, useRouteContext, useRouter } from '@tanstack/react-router'
import { type ReactNode, useEffect, useRef } from 'react'
import { meQuery } from '../auth'
import { clearToken } from '../token'
import { Button } from './ui/Button'

// Every screen the Flutter app has, in its order. `to` is set once a screen is
// ported; until then the entry stays visible but inert, so the nav doubles as
// the parity checklist.
const nav: { label: string; to?: LinkProps['to'] }[] = [
  { label: 'Dashboard', to: '/' },
  { label: 'Inbox' },
  { label: 'Organizations', to: '/organizations' },
  { label: 'Deals' },
  { label: 'Projects' },
  { label: 'Interactions' },
  { label: 'Documents' },
  { label: 'Watches' },
  { label: 'Account' },
  { label: 'System', to: '/system' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const { data: me } = useQuery(meQuery(api))
  const queryClient = useQueryClient()
  const router = useRouter()
  const navRef = useRef<HTMLElement>(null)
  const pathname = useLocation({ select: (l) => l.pathname })

  // On a phone the nav is one scrolling row, and the current entry can sit
  // off-screen. 'nearest' leaves it alone when it is already visible, which on
  // the desktop sidebar it always is.
  useEffect(() => {
    navRef.current
      ?.querySelector('[data-status="active"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [pathname])

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
        <nav className="nav" aria-label="Main" ref={navRef}>
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
          <Button variant="quiet" onPress={logout}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
