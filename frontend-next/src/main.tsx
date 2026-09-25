import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { loadConfig } from './config'
import { routeTree } from './routeTree.gen'

const config = await loadConfig()
const queryClient = new QueryClient()

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
