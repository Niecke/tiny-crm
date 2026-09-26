import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, type LinkProps, useLocation, useRouteContext, useRouter } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'
import { Dialog, Modal, ModalOverlay } from 'react-aria-components'
import { meQuery } from '../auth'
import { captureCountQuery } from '../captures'
import { clearToken } from '../token'
import { QuickCaptureButton } from './QuickCapture'
import { Button } from './ui/Button'

// Every screen the Flutter app has, in its order. `to` is set once a screen is
// ported; until then the entry stays visible but inert, so the nav doubles as
// the parity checklist.
const nav: { label: string; to?: LinkProps['to'] }[] = [
  { label: 'Dashboard', to: '/' },
  { label: 'Inbox', to: '/inbox' },
  { label: 'Organizations', to: '/organizations' },
  { label: 'Contacts', to: '/contacts' },
  { label: 'Tasks', to: '/tasks' },
  { label: 'Deals', to: '/deals' },
  { label: 'Projects', to: '/projects' },
  { label: 'Interactions', to: '/interactions' },
  { label: 'Documents', to: '/documents' },
  { label: 'Watches' },
  { label: 'Account', to: '/account' },
  { label: 'System', to: '/system' },
]

// A sidebar on a desktop. On a phone the sidebar is hidden and a slim top bar
// takes its place: the brand and a menu button that opens the same nav as a
// slide-in panel (styles.css, Narrow screens). The quick-note button is in the
// sidebar on a desktop and floats bottom right on a phone.
export function AppShell({ children }: { children: ReactNode }) {
  const { api } = useRouteContext({ from: '/_authed' })
  // Waiting captures, on the Inbox entry: the inbox is the one list nothing
  // else in the app would ever surface.
  const { data: inbox } = useQuery(captureCountQuery(api))
  const waiting = inbox?.new ?? 0
  // The menu is open on the history entry it was opened on, and only there:
  // any navigation closes it — the back button too, which never goes through
  // a link in it, even back to an identical URL — without an effect to reset
  // it. Every entry has its own key; the href is the fallback.
  const entry = useLocation({ select: (l) => l.state.__TSR_key ?? l.href })
  const [openedOn, setOpenedOn] = useState<string | null>(null)
  const menuOpen = openedOn === entry
  const setMenuOpen = (open: boolean) => setOpenedOn(open ? entry : null)

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          tinyCRM
        </Link>
        <Button
          variant="quiet"
          className="menu-button"
          onPress={() => setMenuOpen(true)}
          aria-label={waiting ? `Menu, ${waiting} waiting in the inbox` : 'Menu'}
        >
          {waiting > 0 && (
            <span className="nav-count" aria-hidden="true">
              {waiting}
            </span>
          )}
          <span className="menu-icon" aria-hidden="true" />
        </Button>
      </header>

      <aside className="sidebar">
        <div className="brand">tinyCRM</div>
        <QuickCaptureButton className="quick-note-sidebar" />
        <NavLinks waiting={waiting} />
        <Account />
      </aside>

      {/* React Aria's modal: focus moves into the panel and stays there,
          Escape or a tap outside closes it, and focus returns to the button. */}
      <ModalOverlay className="drawer-overlay" isOpen={menuOpen} onOpenChange={setMenuOpen} isDismissable>
        <Modal className="drawer">
          <Dialog className="drawer-dialog" aria-label="Menu">
            <div className="drawer-head">
              <span className="brand">tinyCRM</span>
              <Button variant="quiet" className="drawer-close" onPress={() => setMenuOpen(false)} aria-label="Close menu">
                ×
              </Button>
            </div>
            <NavLinks waiting={waiting} onNavigate={() => setMenuOpen(false)} />
            <Account />
          </Dialog>
        </Modal>
      </ModalOverlay>

      <QuickCaptureButton className="quick-note-fab" />
      <main className="main">{children}</main>
    </div>
  )
}

function NavLinks({ waiting, onNavigate }: { waiting: number; onNavigate?: () => void }) {
  return (
    <nav className="nav" aria-label="Main">
      {nav.map((item) =>
        item.to ? (
          // Active matching is by prefix, so / needs to be exact or it would
          // stay highlighted on every page.
          <Link
            key={item.label}
            to={item.to}
            activeOptions={{ exact: item.to === '/' }}
            className="nav-link"
            // Also closes the menu when the link is the page already open,
            // which changes no pathname.
            onClick={onNavigate}
          >
            {item.label}
            {item.to === '/inbox' && waiting > 0 && (
              <span className="nav-count" aria-label={`${waiting} waiting`}>
                {waiting}
              </span>
            )}
          </Link>
        ) : (
          <span key={item.label} className="nav-link" aria-disabled="true" title="Not ported yet">
            {item.label}
          </span>
        ),
      )}
    </nav>
  )
}

function Account() {
  const { api } = useRouteContext({ from: '/_authed' })
  const { data: me } = useQuery(meQuery(api))
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
  )
}
