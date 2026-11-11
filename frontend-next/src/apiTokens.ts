import { queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { components } from './api/schema'

// An agent's credential (backend/app/auth/api_tokens.py). The list never holds
// the secret; only the response that creates a token does.
export type ApiToken = components['schemas']['ApiTokenRead']
export type ApiTokenStatus = ApiToken['status']

export const apiTokensQuery = (api: Api) =>
  queryOptions({
    queryKey: ['api-tokens'],
    queryFn: () => unwrap(api.GET('/users/me/api-tokens/')),
  })

// How long a new token lasts, as the dialog offers it. '' is "never".
export const EXPIRY_OPTIONS = [
  { value: '', label: 'Never' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '365 days' },
] as const

export type Expiry = (typeof EXPIRY_OPTIONS)[number]['value']

// The `expires_at` to send for an option: that many days from `now`, or null.
export function expiresAt(option: Expiry | '', now: Date = new Date()): string | null {
  if (option === '') return null
  return new Date(now.getTime() + Number(option) * 24 * 60 * 60 * 1000).toISOString()
}

const statusLabels: Record<ApiTokenStatus, string> = {
  active: 'Active',
  expired: 'Expired',
  revoked: 'Revoked',
}

export function statusLabel(status: ApiTokenStatus): string {
  return statusLabels[status]
}

export function statusTone(status: ApiTokenStatus): 'success' | 'warning' | 'danger' {
  return status === 'active' ? 'success' : status === 'expired' ? 'warning' : 'danger'
}
