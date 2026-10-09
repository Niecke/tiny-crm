import { queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { components } from './api/schema'
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

// What a correct password gets when the account has two-factor sign-in on
// (backend/app/auth/mfa.py): no session yet, a short-lived token to trade at
// verifyMfa() together with a code.
export type MfaChallenge = components['schemas']['MfaChallenge']

export function isMfaChallenge(result: Tokens | MfaChallenge): result is MfaChallenge {
  return 'mfa_token' in result
}

// fastapi-users expects the OAuth2 password form, not JSON. `scope` is part
// of that form and required by the schema; this app uses no scopes.
export function login(api: Api, email: string, password: string): Promise<Tokens | MfaChallenge> {
  return unwrap(
    api.POST('/auth/jwt/login', {
      body: { username: email, password, scope: '' },
      bodySerializer: (body) => new URLSearchParams({ username: body.username, password: body.password }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  )
}

// The second step of a login with MFA on. `code` is six digits from the
// authenticator app or one of the recovery codes; the backend tells them apart.
export function verifyMfa(api: Api, mfa_token: string, code: string): Promise<Tokens> {
  return unwrap(api.POST('/auth/jwt/mfa', { body: { mfa_token, code } }))
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
