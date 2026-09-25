import { queryOptions } from '@tanstack/react-query'
import { apiFetch } from './api'

export type Me = { id: string; email: string; name: string | null }

// Also the guard's token check: a token that no longer works fails here with a
// 401 before any protected page renders.
export const meQuery = (apiUrl: string) =>
  queryOptions({
    queryKey: ['me'],
    queryFn: () => apiFetch<Me>(apiUrl, '/users/me'),
    staleTime: Infinity,
  })

// fastapi-users expects the OAuth2 password form, not JSON.
export async function login(apiUrl: string, email: string, password: string): Promise<string> {
  const { access_token } = await apiFetch<{ access_token: string }>(apiUrl, '/auth/jwt/login', {
    method: 'POST',
    body: new URLSearchParams({ username: email, password }),
    auth: false,
  })
  return access_token
}
