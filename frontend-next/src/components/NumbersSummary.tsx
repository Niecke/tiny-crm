import { useQuery } from '@tanstack/react-query'
import { Link, type LinkProps, useRouteContext } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import type { MoneyByCurrency } from '../api/types'
import { formatMedian, metricsQuery, moneyPair, totalsByCurrency } from '../metrics'
import { WeeklyDeals } from './WeeklyDeals'

// The dashboard's headline numbers (#138): four figures from
// GET /metrics/dashboard above today's list, each a link into the page that
// explains it. Quarter, as /numbers opens with, so a click lands on the same
// figure. A failure here stays here: today's list does not depend on it.
export function NumbersSummary() {
  const { api } = useRouteContext({ from: '/_authed' })
  const metrics = useQuery(metricsQuery(api, 'quarter'))

  if (metrics.error) {
    return (
      <p className="muted small">
        Numbers unavailable: {metrics.error.message}. <Link to="/numbers">Open Numbers</Link>
      </p>
    )
  }

  const data = metrics.data
  const won = data?.velocity.entered.find((e) => e.stage === 'won')?.count ?? 0
  const lost = data?.velocity.entered.find((e) => e.stage === 'lost')?.count ?? 0
  const stalled = data?.attention.stalled_deals.count ?? 0
  const overdue = data?.attention.overdue_deals.count ?? 0
  const cycle = data?.velocity.sales_cycle

  return (
    <section className="summary" aria-label="Numbers" aria-busy={metrics.isPending}>
      <Tile label="Open pipeline" when="Now" link={{ to: '/numbers' }} loading={!data}>
        {data && <Money totals={totalsByCurrency(data.pipeline.by_stage)} empty="No open deals" />}
      </Tile>

      <Tile label="Committed, not delivered" when="Now" link={{ to: '/numbers' }} loading={!data}>
        {data && <Money totals={data.pipeline.committed} empty="Nothing agreed and open" />}
      </Tile>

      <Tile label="Won" when="This quarter" link={{ to: '/numbers' }} loading={!data}>
        <span className="summary-value">
          {won} {won === 1 ? 'deal' : 'deals'}
        </span>
        <span className="summary-foot">
          {lost} lost
          {cycle?.median_days != null && ` · median ${formatMedian(cycle.median_days)} to win`}
        </span>
      </Tile>

      <Tile
        label="Deals needing a look"
        when="Now"
        link={{ to: '/deals', search: { scope: stalled || !overdue ? 'stalled' : 'overdue', view: 'list' } }}
        loading={!data}
        tone={stalled + overdue > 0 ? 'warning' : undefined}
      >
        <span className="summary-value">{stalled} stalled</span>
        <span className="summary-foot">no next step · {overdue} past expected close</span>
      </Tile>
    </section>
  )
}

function Tile({
  label,
  when,
  link,
  loading,
  tone,
  children,
}: {
  label: string
  when: string
  link: Pick<LinkProps, 'to' | 'search'>
  loading: boolean
  tone?: 'warning'
  children: ReactNode
}) {
  return (
    <Link {...link} className="summary-tile" data-tone={tone}>
      <span className="summary-when">{when}</span>
      <span className="summary-label">{label}</span>
      {loading ? (
        <span className="skeleton" aria-hidden="true">
          <span className="skeleton-line" style={{ width: '70%' }} />
          <span className="skeleton-line" style={{ width: '45%' }} />
        </span>
      ) : (
        children
      )}
    </Link>
  )
}

// One line per currency, never one sum: the open-ended deals are said beside
// each amount rather than counted as nothing.
function Money({ totals, empty }: { totals: MoneyByCurrency[]; empty: string }) {
  if (totals.length === 0) return <span className="summary-foot">{empty}</span>
  const deals = totals.reduce((n, t) => n + t.count, 0)
  const openEnded = totals.reduce((n, t) => n + t.open_ended, 0)
  return (
    <>
      {totals.map((t) => (
        <span key={t.currency} className="summary-value">
          {moneyPair(t).amount}
        </span>
      ))}
      <span className="summary-foot">
        {deals} {deals === 1 ? 'deal' : 'deals'}
        {openEnded > 0 && ` · ${openEnded} open-ended`}
      </span>
    </>
  )
}

// New deals per week beside today's list: whether the top of the funnel is
// being fed, week by week. The same cached request as the tiles.
export function WeeklyDealsPanel() {
  const { api } = useRouteContext({ from: '/_authed' })
  const metrics = useQuery(metricsQuery(api, 'quarter'))
  if (metrics.error) return null
  return (
    <section className="panel" aria-label="New deals per week">
      <div className="panel-header weekly-header">
        <h2>New deals per week</h2>
        <Link to="/deals" search={{ scope: 'all', view: 'list' }} className="small">
          Deals
        </Link>
      </div>
      <div className="panel-body">
        {metrics.data ? (
          <WeeklyDeals weeks={metrics.data.trends.deals_opened_weekly} />
        ) : (
          <span className="skeleton" aria-hidden="true">
            <span className="skeleton-line" style={{ width: '80%' }} />
            <span className="skeleton-line" style={{ width: '60%' }} />
          </span>
        )}
      </div>
    </section>
  )
}
