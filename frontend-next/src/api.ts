import { clearToken, getToken } from './token'

// Hand-written stand-in until the client is generated from /openapi.json
// (#122). It only adds the bearer token and turns non-2xx into ApiError.
export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

type ApiInit = RequestInit & { auth?: boolean }

export async function apiFetch<T>(apiUrl: string, path: string, init: ApiInit = {}): Promise<T> {
  const { auth = true, ...rest } = init
  const headers = new Headers(rest.headers)
  const token = auth ? getToken() : null
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${apiUrl}${path}`, { ...rest, headers })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    // An authenticated call rejected means the token is dead (expired, secret
    // rotated, password changed). Dropping it here is what sends the guard back
    // to /login on the next navigation.
    if (res.status === 401 && token) clearToken()
    throw new ApiError(res.status, detail, typeof detail === 'string' ? detail : `${path} → ${res.status}`)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
