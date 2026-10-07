import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { DealCreate, DealRead, DealUpdate } from './api/types'
import { PAGE_SIZE } from './contacts'

export type Stage = DealRead['stage']
type Status = 'open' | 'active' | 'won' | 'finished'

// The pipeline, left to right. Won starts the work rather than ending the
// deal, so a running engagement has somewhere to sit. Draft comes before
// anything is sent: the research and the letter, moved to Lead once it is out.
export const stageOptions: { value: Stage; label: string }[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'lead', label: 'Lead' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'proposal', label: 'Proposal' },
  { value: 'negotiation', label: 'Negotiation' },
  { value: 'won', label: 'Won' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'lost', label: 'Lost' },
]

export const stageLabel = (stage: string) => stageOptions.find((o) => o.value === stage)?.label ?? stage

// Groupings from models/deal.py. A draft is open but not in play: the numbers
// and the attention lists start at lead.
export const IN_PLAY: Stage[] = ['lead', 'qualified', 'proposal', 'negotiation']
const OPEN: Stage[] = ['draft', ...IN_PLAY]
const WON: Stage[] = ['won', 'running', 'completed']
export const DECIDED: Stage[] = [...WON, 'lost']
export const isDecided = (stage: string) => DECIDED.includes(stage as Stage)

// A draft stays plain: nothing has gone out yet.
export const stageTone = (stage: string): 'success' | 'danger' | 'accent' | undefined =>
  stage === 'draft' ? undefined : stage === 'lost' ? 'danger' : WON.includes(stage as Stage) ? 'success' : 'accent'

// What the list is asked for, as the Flutter app's scope menu offers it: four
// status questions and one per stage. "On my plate" is the default — it keeps
// won and running work in view, which is what the running stage exists for.
type Scope = {
  value: string
  label: string
  status?: Status
  stage?: Stage
  // The deals in play that need looking at: no next step, or past their
  // expected close date. What the Numbers page's counts link to.
  stalled?: true
  overdue?: true
  columns: Stage[]
}

export const scopeOptions: Scope[] = [
  { value: 'plate', label: 'On my plate', status: 'active', columns: [...OPEN, 'won', 'running'] },
  { value: 'competing', label: 'Still competing', status: 'open', columns: OPEN },
  { value: 'won', label: 'Won (any state)', status: 'won', columns: WON },
  { value: 'finished', label: 'Finished', status: 'finished', columns: ['completed', 'lost'] },
  { value: 'stalled', label: 'No next step', stalled: true, columns: IN_PLAY },
  { value: 'overdue', label: 'Past expected close', overdue: true, columns: IN_PLAY },
  { value: 'all', label: 'All deals', columns: stageOptions.map((o) => o.value) },
  ...stageOptions.map((o) => ({ value: `stage-${o.value}`, label: `· ${o.label}`, stage: o.value, columns: [o.value] })),
]

export const scopeOf = (value: string | undefined) => scopeOptions.find((o) => o.value === value) ?? scopeOptions[0]

export const valueTypeOptions = [
  { value: 'fixed', label: 'Fixed price' },
  { value: 'rate_based', label: 'By rate' },
  { value: 'retainer', label: 'Retainer' },
] as const

export const unitOptions = [
  { value: 'hour', label: 'hour', plural: 'hours' },
  { value: 'day', label: 'day', plural: 'days' },
  { value: 'week', label: 'week', plural: 'weeks' },
  { value: 'month', label: 'month', plural: 'months' },
] as const

// Money comes as the exact decimal string the API sent and is never turned
// into a float: grouped thousands, two decimals, the currency code after.
export function formatMoney(amount: string, currency: string): string {
  const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(amount.trim())
  if (!match) return `${amount} ${currency}`
  const [, sign, whole, fraction = ''] = match
  return `${sign}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')} ${currency}`
}

// What a deal is worth, in the shape it is priced in: the total when one can
// be derived, else the rate. An open-ended engagement shows its rate and says
// so, rather than reading as unpriced.
export function dealValue(d: DealRead): { headline: string | null; detail: string | null } {
  const unit = unitOptions.find((u) => u.value === d.rate_unit)
  const volumeUnit = unitOptions.find((u) => u.value === d.volume_unit)
  const total = d.expected_value ? formatMoney(d.expected_value, d.currency) : null
  const rate = d.rate && unit ? `${formatMoney(d.rate, d.currency)}/${unit.label}` : null
  let detail: string | null = null
  if (d.is_open_ended) detail = 'Open-ended — no total to forecast'
  else if (total && rate && d.estimated_volume) detail = `${rate} × ${d.estimated_volume} ${volumeUnit?.plural ?? ''}`.trim()
  else if (!total && d.estimated_volume && unit && volumeUnit)
    detail = `Estimated in ${volumeUnit.plural} at a ${unit.label} rate — no total derived`
  return { headline: total ?? rate, detail }
}

// A short form for a card or a row.
export function valueSummary(d: DealRead): string | null {
  const { headline } = dealValue(d)
  return d.is_open_ended && headline ? `${headline} · open-ended` : headline
}

export type DealFilters = { q?: string; scope?: string; archived?: boolean; page?: number }

const scopeQuery = (scope: string | undefined) => {
  const s = scopeOf(scope)
  return { status: s.status, stage: s.stage, stalled: s.stalled, overdue: s.overdue }
}

// Soonest expected close first — the API's order.
export const dealsQuery = (api: Api, { q, scope, archived, page = 1 }: DealFilters) =>
  queryOptions({
    queryKey: ['deals', 'list', { q, scope, archived, page }],
    queryFn: () =>
      unwrap(
        api.GET('/deals/', {
          params: {
            query: {
              search: q || undefined,
              // The archive is read whole: a scope is a question about the pipeline.
              ...(archived ? { archived: true } : scopeQuery(scope)),
              skip: (page - 1) * PAGE_SIZE,
              limit: PAGE_SIZE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

// The board shows every deal in scope at once, grouped by stage in the page.
// 200 is the API's page cap; past that the board says what it is not showing.
export const BOARD_LIMIT = 200

export const boardQuery = (api: Api, { q, scope }: DealFilters) =>
  queryOptions({
    queryKey: ['deals', 'board', { q, scope }],
    queryFn: () =>
      unwrap(api.GET('/deals/', { params: { query: { search: q || undefined, ...scopeQuery(scope), limit: BOARD_LIMIT } } })),
    placeholderData: keepPreviousData,
  })

export const dealQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['deals', 'detail', id],
    queryFn: () => unwrap(api.GET('/deals/{deal_id}', { params: { path: { deal_id: id } } })),
  })

// Suggestions for a deal picker, by title. Ten is plenty for a dropdown.
export const dealOptionsQuery = (api: Api, search: string) =>
  queryOptions({
    queryKey: ['deals', 'options', search],
    queryFn: () => unwrap(api.GET('/deals/', { params: { query: { search: search || undefined, limit: 10 } } })),
    placeholderData: keepPreviousData,
  })

export const createDeal = (api: Api, body: DealCreate) => unwrap(api.POST('/deals/', { body }))

// `version` makes the save conditional — see useEditVersion (#142).
export const updateDeal = (api: Api, id: string, body: DealUpdate, version?: number) =>
  unwrap(api.PATCH('/deals/{deal_id}', { params: { path: { deal_id: id } }, body: { ...body, version } }))

export const deleteDeal = (api: Api, id: string) =>
  unwrap(api.DELETE('/deals/{deal_id}', { params: { path: { deal_id: id } } }))

export const archiveDeal = (api: Api, id: string) =>
  unwrap(api.POST('/deals/{deal_id}/archive', { params: { path: { deal_id: id } } }))

export const restoreDeal = (api: Api, id: string) =>
  unwrap(api.POST('/deals/{deal_id}/restore', { params: { path: { deal_id: id } } }))

// The one move the pipeline is made of. The server stamps or clears the close
// date, pins probability to 100 or 0 once decided, and keeps a lost reason
// only on a lost deal.
export const moveDeal = (api: Api, id: string, stage: Stage, lostReason?: string | null) =>
  unwrap(
    api.POST('/deals/{deal_id}/stage', {
      params: { path: { deal_id: id } },
      body: { stage, lost_reason: stage === 'lost' ? lostReason || null : null },
    }),
  )

// Deal titles also show on tasks and in the briefing.
export const invalidateDeals = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries({ queryKey: ['deals'] }),
    queryClient.invalidateQueries({ queryKey: ['briefing'] }),
    queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  ])
