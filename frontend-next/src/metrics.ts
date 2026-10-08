import { queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { MoneyByCurrency, StageMoney } from './api/types'
import { formatMoney } from './deals'

// The Numbers page (#138): GET /metrics/dashboard, the dashboard's aggregates
// in one response. The arithmetic is the backend's (DASHBOARD.md); this file
// only shapes it for display and never adds two amounts together.

export const periodOptions = [
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
] as const

export type PeriodKind = (typeof periodOptions)[number]['value']

export const metricsQuery = (api: Api, period: PeriodKind) =>
  queryOptions({
    queryKey: ['metrics', 'dashboard', period],
    queryFn: () => unwrap(api.GET('/metrics/dashboard', { params: { query: { period } } })),
    // The "now" figures move on their own; refetch when the tab comes back.
    refetchOnWindowFocus: true,
  })

const ISSUES = 'https://github.com/Niecke/tiny-crm/issues'
export const issueUrl = (issue: number) => `${ISSUES}/${issue}`

// "This quarter", for labelling the figures that follow the switch.
export const periodLabel = (kind: string) => `This ${kind}`

// The resolved window the API echoed back. `end` is the first day after the
// period, so the last day shown is the one before it.
export function formatPeriod(start: string, end: string): string {
  const first = localDate(start)
  const last = localDate(end)
  last.setDate(last.getDate() - 1)
  const sameYear = first.getFullYear() === last.getFullYear()
  const day: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
  const from = first.toLocaleDateString(undefined, sameYear ? day : { ...day, year: 'numeric' })
  const to = last.toLocaleDateString(undefined, { ...day, year: 'numeric' })
  return `${from} – ${to}`
}

// Noon, so no timezone offset can move a date-only string across midnight.
const localDate = (isoDate: string) => new Date(`${isoDate}T12:00:00`)

// One money figure as the API sends it: an amount and the deals that have
// none. Open-ended deals are never zero, so they are always said.
export function moneyPair(m: Pick<MoneyByCurrency, 'value' | 'currency' | 'open_ended'>): {
  amount: string
  openEnded: string | null
} {
  return {
    amount: formatMoney(m.value, m.currency),
    openEnded: m.open_ended > 0 ? `${m.open_ended} open-ended` : null,
  }
}

export type CurrencyBlock = {
  currency: string
  rows: StageMoney[]
  count: number
  openEnded: number
}

// The pipeline rows split into one block per currency, in the API's order.
// The total of each block is not computed here: summing decimal strings in
// JavaScript would go through floats, the one thing the API avoids. Only the
// counts are added.
export function byCurrency(rows: StageMoney[]): CurrencyBlock[] {
  const blocks = new Map<string, CurrencyBlock>()
  for (const row of rows) {
    const block = blocks.get(row.currency) ?? { currency: row.currency, rows: [], count: 0, openEnded: 0 }
    block.rows.push(row)
    block.count += row.count
    block.openEnded += row.open_ended
    blocks.set(row.currency, block)
  }
  return [...blocks.values()].sort((a, b) => a.currency.localeCompare(b.currency))
}

// One total per currency over the open pipeline, for the dashboard's summary.
// Decimal strings are added as integer cents in BigInt, so the sum is exact —
// never through a float. Currencies are never added to each other.
export function totalsByCurrency(rows: StageMoney[]): MoneyByCurrency[] {
  const totals = new Map<string, { cents: bigint; count: number; open_ended: number }>()
  for (const row of rows) {
    const t = totals.get(row.currency) ?? { cents: BigInt(0), count: 0, open_ended: 0 }
    t.cents += exactCents(row.value)
    t.count += row.count
    t.open_ended += row.open_ended
    totals.set(row.currency, t)
  }
  return [...totals.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, t]) => ({ currency, value: fromCents(t.cents), count: t.count, open_ended: t.open_ended }))
}

const HUNDRED = BigInt(100)

function exactCents(value: string): bigint {
  const [whole, fraction = ''] = value.trim().split('.')
  return BigInt(whole) * HUNDRED + BigInt(fraction.padEnd(2, '0').slice(0, 2))
}

const fromCents = (cents: bigint) => `${cents / HUNDRED}.${(cents % HUNDRED).toString().padStart(2, '0')}`

// Bar length for an amount, relative to the largest in its own block, without
// turning money into a float for anything but the drawing. Integer cents keep
// the comparison exact up to amounts no solo business reaches.
const cents = (value: string) => {
  const [whole, fraction = ''] = value.split('.')
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0').slice(0, 2))
}

export function share(value: string, max: string): number {
  const top = cents(max)
  return top > 0 ? cents(value) / top : 0
}

export function largest(rows: StageMoney[]): string {
  return rows.reduce((max, r) => (cents(r.value) > cents(max) ? r.value : max), '0.00')
}

// Share of the deals that entered a stage and went further. Null rather than
// 0% when nothing entered: no rate is not a bad rate.
export function conversionRate(entered: number, advanced: number): number | null {
  return entered > 0 ? Math.round((advanced / entered) * 100) : null
}

// A 0 to 1 share from the API, as a whole percent. Null stays null, for the
// same reason: nothing decided is not a win rate of 0%.
export function percent(rate: number | null | undefined): number | null {
  return rate == null ? null : Math.round(rate * 100)
}

// Deals on one side of the outcomes, across currencies. Deals can be counted
// together where their amounts cannot be added.
export const dealCount = (rows: MoneyByCurrency[]) => rows.reduce((n, r) => n + r.count, 0)

export const dealsText = (n: number) => (n === 1 ? '1 deal' : `${n} deals`)

export function daysText(days: number): string {
  return days === 1 ? '1 day' : `${days} days`
}

export function formatMedian(days: number | null | undefined): string {
  if (days == null) return '–'
  return `${Number.isInteger(days) ? days : days.toFixed(1)} d`
}

export type WeekCount = { start: string; count: number; complete: boolean }

// The figures a weekly series is read by: this week so far, last week, and
// the average over the complete weeks — the running one would drag it down
// every Monday.
export function weeklySummary(weeks: WeekCount[]): {
  current: WeekCount | undefined
  previous: WeekCount | undefined
  average: number | null
} {
  const complete = weeks.filter((w) => w.complete)
  const total = complete.reduce((n, w) => n + w.count, 0)
  return {
    current: weeks.find((w) => !w.complete),
    previous: complete.at(-1),
    average: complete.length > 0 ? Math.round((total / complete.length) * 10) / 10 : null,
  }
}

export const formatWeek = (start: string) =>
  localDate(start).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
