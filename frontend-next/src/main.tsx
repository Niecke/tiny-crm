import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ApiError } from './api'
import { loadConfig } from './config'
import { routeTree } from './routeTree.gen'
import './styles.css'

const config = await loadConfig()

// A token that dies mid-session (expiry, password change elsewhere) shows up as
// a 401 on whatever request comes next. apiFetch has already dropped it; this
// sends the user to /login and back here afterwards.
function onAuthError(err: unknown) {
  if (!(err instanceof ApiError) || err.status !== 401) return
  const { location } = router.state
  if (location.pathname === '/login') return
  void router.navigate({ to: '/login', search: { redirect: location.href } })
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: onAuthError }),
  mutationCache: new MutationCache({ onError: onAuthError }),
  defaultOptions: {
    queries: {
      // A 4xx will not change on retry; only network and server errors might.
      retry: (failureCount, err) =>
        !(err instanceof ApiError && err.status >= 400 && err.status < 500) && failureCount < 3,
    },
  },
})

const router = createRouter({
  routeTree,
  basepath: '/next',
  context: { config, queryClient },
  // Route loaders go through the query cache, so the router's own cache would
  // only hold a second, staler copy of the same data.
  defaultPreloadStaleTime: 0,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
