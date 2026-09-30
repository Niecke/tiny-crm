// A login is a pair (backend/app/auth/sessions.py): an access token that
// lives 15 minutes and a refresh token that renews it. Both live in
// localStorage, so a login survives a closed tab and every tab shares one
// session. That makes them readable by any script on the origin — see
// FRONTEND.md, "Token storage", for why that is acceptable now that the access
// token is short and the session can be ended server-side. All access goes
// through this file, so moving the tokens elsewhere later touches one place.
const ACCESS_KEY = 'tinycrm.token'
const REFRESH_KEY = 'tinycrm.refresh'

export type Tokens = { access_token: string; refresh_token: string }

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return read(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return read(REFRESH_KEY)
}

export function setTokens({ access_token, refresh_token }: Tokens) {
  try {
    localStorage.setItem(ACCESS_KEY, access_token)
    localStorage.setItem(REFRESH_KEY, refresh_token)
  } catch {
    // Storage blocked (private mode, site data disabled): the login still
    // works for this page load, it just is not remembered.
  }
}

export function clearTokens() {
  try {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  } catch {
    // Nothing stored, nothing to clear.
  }
}

// Renew this long before the access token actually expires, so a request
// never leaves with a token that dies on the way.
const EXPIRY_MARGIN_SECONDS = 30

// Reads the JWT's own `exp` rather than keeping a separate timestamp that
// could drift from the token it describes. Unreadable counts as expiring: the
// refresh will sort it out, or fail and send the user to sign in.
export function expiresSoon(token: string): boolean {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const { exp } = JSON.parse(atob(payload)) as { exp?: unknown }
    return typeof exp !== 'number' || exp - EXPIRY_MARGIN_SECONDS <= Date.now() / 1000
  } catch {
    return true
  }
}
