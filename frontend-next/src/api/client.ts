import createClient, { type Client, type Middleware } from 'openapi-fetch'
import { clearTokens, expiresSoon, getRefreshToken, getToken, setTokens } from '../token'
import type { paths } from './schema'

// The API client, typed end to end from the backend's OpenAPI schema
// (src/api/schema.d.ts, generated — see FRONTEND.md, "API client"). A path,
// a query parameter or a body field the backend does not have is a compile
// error, and so is reading a response field it does not return.
export type Api = Client<paths>

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

// Trades the refresh token for a new pair. A refusal (401) means the session
// is over — signed out, revoked by a password change, or idle too long — and
// the tokens go. Anything else (offline, a 5xx) leaves them for the next try.
async function renew(refresher: Api): Promise<boolean> {
  const refresh_token = getRefreshToken()
  if (!refresh_token) return false
  try {
    const { data, response } = await refresher.POST('/auth/jwt/refresh', { body: { refresh_token } })
    if (data) {
      setTokens(data)
      return true
    }
    // Unless another tab stored a newer pair while this one was on the way.
    if (response.status === 401 && getRefreshToken() === refresh_token) clearTokens()
    return false
  } catch {
    return false
  }
}

// The access token lives 15 minutes (backend/app/auth/sessions.py), so it
// expires all the time in a tab left open. The middleware renews it before a
// request goes out, and once more if the API refuses it anyway; only when the
// session itself is over does a 401 reach the app, which sends the user to
// /login (src/main.tsx).
function authMiddleware(baseUrl: string): Middleware {
  // Its own client, without this middleware: a refresh must not trigger one.
  const refresher = createClient<paths>({ baseUrl })
  // One refresh at a time per tab; every request that needs one waits for it.
  // Tabs racing each other are the backend's to sort out: it answers a
  // refresh token that was rotated a moment ago with the same new pair.
  let inFlight: Promise<boolean> | null = null
  const refresh = () => (inFlight ??= renew(refresher).finally(() => (inFlight = null)))

  // A copy of each authenticated request, to send again after a refresh. The
  // original's body is spent by the time its response arrives.
  const copies = new Map<string, Request>()

  return {
    async onRequest({ request, id }) {
      let token = getToken()
      if (token && expiresSoon(token)) {
        await refresh()
        token = getToken()
      }
      if (!token) return request
      request.headers.set('Authorization', `Bearer ${token}`)
      copies.set(id, request.clone())
      return request
    },
    async onResponse({ request, response, id }) {
      const copy = copies.get(id)
      copies.delete(id)
      if (response.status !== 401 || !copy) return response

      // Refused although it looked valid: the clock is off, or the token was
      // signed with a secret that has since been rotated. Renew — unless
      // another request already has — and try once more.
      const current = getToken()
      const renewedMeanwhile = current !== null && request.headers.get('Authorization') !== `Bearer ${current}`
      if (renewedMeanwhile || (await refresh())) {
        copy.headers.set('Authorization', `Bearer ${getToken()}`)
        const retried = await fetch(copy)
        if (retried.status !== 401) return retried
      }
      // The session is over. Dropping the tokens is what sends the guard back
      // to /login on the next navigation.
      clearTokens()
      return response
    },
    onError({ id }) {
      copies.delete(id)
    },
  }
}

export function createApi(baseUrl: string): Api {
  const api = createClient<paths>({ baseUrl })
  api.use(authMiddleware(baseUrl))
  return api
}

// openapi-fetch resolves on every HTTP status and hands back `data` or
// `error`. TanStack Query only sees a failure when the promise rejects, so
// every call goes through this: the typed `data` on success, an ApiError
// carrying the status and FastAPI's `detail` otherwise.
export async function unwrap<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    const detail = (error as { detail?: unknown } | undefined)?.detail
    const path = response.url ? new URL(response.url).pathname : 'request'
    throw new ApiError(response.status, detail, typeof detail === 'string' ? detail : `${path} → ${response.status}`)
  }
  // A 204 has no body; its `data` is undefined, which is what the schema
  // says for it too.
  return data as T
}
