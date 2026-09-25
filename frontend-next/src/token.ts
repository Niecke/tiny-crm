// The JWT lives in localStorage so a login survives a closed tab, as it does in
// the Flutter app. That makes it readable by any script on the origin, and the
// token is valid for ~9 months (T24) — the trade-off still has to be recorded
// in FRONTEND.md (#122). Access goes through these three functions so moving it
// elsewhere later touches one file.
const TOKEN_KEY = 'tinycrm.token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage blocked (private mode, site data disabled): the login still
    // works for this page load, it just is not remembered.
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing stored, nothing to clear.
  }
}
