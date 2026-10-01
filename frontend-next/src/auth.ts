import { queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import { clearTokens, getRefreshToken, type Tokens } from './token'

// The backend's rule (MIN_PASSWORD_LENGTH in app/schemas/user.py), checked here
// first so the common mistake never needs a round trip.
export const MIN_PASSWORD_LENGTH = 8

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
export function login(api: Api, email: string, password: string): Promise<Tokens> {
  return unwrap(
    api.POST('/auth/jwt/login', {
      body: { username: email, password, scope: '' },
      bodySerializer: (body) => new URLSearchParams({ username: body.username, password: body.password }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  )
}

// Ends the session server-side, so the tokens stop working on the spot —
// not just in this browser. Takes the refresh token, which works even when
// the access token has already expired. Best effort: offline, the tokens are
// still dropped here, and the session runs out on its own.
export async function logout(api: Api): Promise<void> {
  const refresh_token = getRefreshToken()
  clearTokens()
  if (!refresh_token) return
  try {
    await api.POST('/auth/jwt/logout', { body: { refresh_token } })
  } catch {
    // Unreachable API; nothing more to do from here.
  }
}
