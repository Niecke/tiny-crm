import createClient, { type Client, type Middleware } from 'openapi-fetch'
import { clearToken, getToken } from '../token'
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

const auth: Middleware = {
  onRequest({ request }) {
    const token = getToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  onResponse({ request, response }) {
    // An authenticated call rejected means the token is dead (expired, secret
    // rotated, password changed). Dropping it here is what sends the guard
    // back to /login on the next navigation.
    if (response.status === 401 && request.headers.has('Authorization')) clearToken()
    return response
  },
}

export function createApi(baseUrl: string): Api {
  const api = createClient<paths>({ baseUrl })
  api.use(auth)
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
