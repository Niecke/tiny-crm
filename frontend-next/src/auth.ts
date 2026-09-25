import { queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'

// Also the guard's token check: a token that no longer works fails here with a
// 401 before any protected page renders.
export const meQuery = (api: Api) =>
  queryOptions({
    queryKey: ['me'],
    queryFn: () => unwrap(api.GET('/users/me')),
    staleTime: Infinity,
  })

// fastapi-users expects the OAuth2 password form, not JSON. `scope` is part
// of that form and required by the schema; this app uses no scopes.
export async function login(api: Api, email: string, password: string): Promise<string> {
  const { access_token } = await unwrap(
    api.POST('/auth/jwt/login', {
      body: { username: email, password, scope: '' },
      bodySerializer: (body) => new URLSearchParams({ username: body.username, password: body.password }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  )
  return access_token
}
