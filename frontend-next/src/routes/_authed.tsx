import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'
import { ApiError } from '../api/client'
import { meQuery } from '../auth'
import { AppShell } from '../components/AppShell'
import { clearToken, getToken } from '../token'

// Pathless layout: every route under src/routes/_authed/ is behind the login
// and inside the app shell. /login is the only page outside it.
export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ context, location }) => {
    const toLogin = redirect({ to: '/login', search: { redirect: location.href } })
    if (!getToken()) throw toLogin

    try {
      await context.queryClient.ensureQueryData(meQuery(context.api))
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        throw toLogin
      }
      // Anything else (API down, 500) is not a reason to log out; the error
      // boundary shows it and a reload retries.
      throw err
    }
  },
  component: AuthedLayout,
})

function AuthedLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}
