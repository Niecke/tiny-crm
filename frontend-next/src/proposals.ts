import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { ProposalEntity, ProposalRead, ProposalStatus } from './api/types'
import { contactQuery } from './contacts'
import { dealQuery } from './deals'
import { interactionQuery } from './interactions'
import { organizationQuery } from './organizations'
import { taskQuery } from './tasks'

// What agents propose (backend/app/proposals.py): a create, update or archive
// that waits here until the operator approves, edits or rejects it.

// Oldest first, so a page of decided proposals ends before the newest ones;
// the inbox asks for another PROPOSALS_LIMIT at a time.
export const PROPOSALS_LIMIT = 100

export const proposalsQuery = (api: Api, status: ProposalStatus, limit = PROPOSALS_LIMIT) =>
  queryOptions({
    queryKey: ['proposals', 'list', status, limit],
    queryFn: () => unwrap(api.GET('/proposals/', { params: { query: { status, limit } } })),
    placeholderData: keepPreviousData,
  })

// The nav badge.
export const proposalCountQuery = (api: Api) =>
  queryOptions({
    queryKey: ['proposals', 'count'],
    queryFn: () => unwrap(api.GET('/proposals/count')),
  })

// What the reviewer edited, if they did: the form's whole body, and the version
// of the record they were looking at, so a change made meanwhile is a 409.
export type Approval = { payload?: Record<string, unknown>; version?: number | null }

export const approveProposal = (api: Api, id: string, body?: Approval) =>
  unwrap(api.POST('/proposals/{proposal_id}/approve', { params: { path: { proposal_id: id } }, body }))

export const rejectProposal = (api: Api, id: string, reason?: string) =>
  unwrap(
    api.POST('/proposals/{proposal_id}/reject', {
      params: { path: { proposal_id: id } },
      body: { rejection_reason: reason || null },
    }),
  )

// The record an update is about, as the edit form needs it: fetched fresh, so
// the version the reviewer approves against is the one they were looking at.
export function targetRecord(queryClient: QueryClient, api: Api, type: ProposalEntity, id: string): Promise<unknown> {
  switch (type) {
    case 'contact':
      return queryClient.fetchQuery(contactQuery(api, id))
    case 'organization':
      return queryClient.fetchQuery(organizationQuery(api, id))
    case 'deal':
      return queryClient.fetchQuery(dealQuery(api, id))
    case 'task':
      return queryClient.fetchQuery(taskQuery(api, id))
    case 'interaction':
      return queryClient.fetchQuery(interactionQuery(api, id))
  }
}

// Which lists change when a proposal is applied, so the pages behind the
// inbox are not left showing the old state.
export const entityKeys: Record<ProposalEntity, string> = {
  contact: 'contacts',
  organization: 'organizations',
  deal: 'deals',
  task: 'tasks',
  interaction: 'interactions',
}

export const entityLabels: Record<ProposalEntity, string> = {
  contact: 'contact',
  organization: 'organization',
  deal: 'deal',
  task: 'task',
  interaction: 'interaction',
}

const fieldNames: Record<string, string> = {
  organization_id: 'Organization',
  contact_id: 'Contact',
  deal_id: 'Deal',
  interaction_id: 'Interaction',
  contact_ids: 'Contacts',
  organization_ids: 'Organizations',
  deal_ids: 'Deals',
  project_ids: 'Projects',
  expected_close_date: 'Expected close',
  due_date: 'Due',
  occurred_at: 'When',
  duration_minutes: 'Duration (minutes)',
}

// "job_title" -> "Job title". A few fields read better than their key does.
export function fieldLabel(_entityType: ProposalEntity, key: string): string {
  const known = fieldNames[key]
  if (known) return known
  const words = key.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const EMPTY = '—'

// A value as a person reads it: names instead of ids, "Yes" instead of true.
export function formatValue(value: unknown, labels: Record<string, string> = {}): string {
  if (value === null || value === undefined || value === '') return EMPTY
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length === 0 ? EMPTY : value.map((v) => formatValue(v, labels)).join(', ')
  if (typeof value === 'string') return labels[value] ?? value
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export type DiffRow = { field: string; current: string | null; proposed: string; changed: boolean }

// One row per proposed field. `current` is null for a create, which has
// nothing to compare against; an update flags the rows that really differ,
// since an agent may well propose a value the record already has.
export function diffRows(proposal: ProposalRead, labels: Record<string, string> = {}): DiffRow[] {
  const proposed = proposal.applied_payload ?? proposal.proposed_payload
  const current = proposal.current
  return Object.entries(proposed).map(([key, value]) => {
    const field = fieldLabel(proposal.entity_type, key)
    if (proposal.action === 'create' || !current) {
      return { field, current: null, proposed: formatValue(value, labels), changed: true }
    }
    return {
      field,
      current: formatValue(current[key], labels),
      proposed: formatValue(value, labels),
      changed: JSON.stringify(current[key] ?? null) !== JSON.stringify(value ?? null),
    }
  })
}

// "New contact", "Update deal", "Archive task".
export function actionTitle(proposal: Pick<ProposalRead, 'action' | 'entity_type'>): string {
  const verb = { create: 'New', update: 'Update', archive: 'Archive' }[proposal.action]
  return `${verb} ${entityLabels[proposal.entity_type]}`
}
