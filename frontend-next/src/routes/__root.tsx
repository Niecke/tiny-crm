import type { QueryClient } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import type { Api } from '../api/client'
import type { AppConfig } from '../config'

export type RouterContext = {
  api: Api
  config: AppConfig
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  return (
    <>
      <Outlet />
      {import.meta.env.DEV && (
        <>
          {/* Top right: bottom left would cover the sidebar's sign-out button. */}
          <ReactQueryDevtools buttonPosition="top-right" />
          <TanStackRouterDevtools position="bottom-right" />
        </>
      )}
    </>
  )
}
