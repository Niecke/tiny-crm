import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, type LinkProps } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { z } from 'zod'
import type { AttentionRow, DashboardMetrics, MoneyByCurrency } from '../../api/types'
import { Segmented } from '../../components/ui/Segmented'
import { WeeklyDeals } from '../../components/WeeklyDeals'
import { IN_PLAY, stageLabel } from '../../deals'
import {
  byCurrency,
  conversionRate,
  daysText,
  dealCount,
  dealsText,
  formatMedian,
  formatPeriod,
  issueUrl,
  largest,
  metricsQuery,
  moneyPair,
  type PeriodKind,
  percent,
  periodLabel,
  periodOptions,
  share,
} from '../../metrics'

// The period is view state: it survives a reload and a shared link. Quarter
// is the default and stays out of the URL.
const searchSchema = z.object({
  period: z.enum(['week', 'month', 'year']).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/numbers')({
  validateSearch: searchSchema,
  component: Numbers,
})

// The dashboard's aggregates (#138, DASHBOARD.md). Each panel answers one
// question and says whether it shows now or the chosen period. What cannot be
// measured yet is a placeholder naming the issue it waits on — never a zero,
// which would claim something the data cannot say.
function Numbers() {
  const { api } = Route.useRouteContext()
  const { period: chosen } = Route.useSearch()
  const navigate = Route.useNavigate()
  const period: PeriodKind = chosen ?? 'quarter'
  const metrics = useQuery(metricsQuery(api, period))
  const data = metrics.data

  return (
    <div className="page numbers">
      <header className="page-header numbers-header">
        <div className="page-header">
          <h1>Numbers</h1>
          {data && (
            <p>
              {formatPeriod(data.period.start, data.period.end)} · {data.period.timezone}
            </p>
          )}
        </div>
        <Segmented
          label="Period"
          value={period}
          onChange={(v) =>
            void navigate({ search: { period: v === 'quarter' ? undefined : v }, replace: true })
          }
          options={periodOptions.map((o) => ({ value: o.value, label: o.label }))}
        />
      </header>

      {metrics.isPending ? (
        <p className="muted">Loading…</p>
      ) : metrics.error ? (
        <p className="form-error">{metrics.error.message}</p>
      ) : (
        <>
          <Pipeline data={data!} />
          <Velocity data={data!} />
          <div className="numbers-pair">
            <Outcomes data={data!} />
            <Attention data={data!} />
          </div>
          <Activity data={data!} />
          <Delivery />
        </>
      )}
    </div>
  )
}

function Panel({
  title,
  when,
  children,
  pending,
}: {
  title: string
  when: string
  children: ReactNode
  pending?: boolean
}) {
  return (
    <section className="panel numbers-panel" data-pending={pending || undefined} aria-label={title}>
      <div className="panel-header numbers-panel-header">
        <h2>{title}</h2>
        <span className="numbers-when">{when}</span>
      </div>
      <div className="panel-body numbers-panel-body">{children}</div>
    </section>
  )
}

// A figure that is planned and cannot be computed yet: a static skeleton in
// the shape it will take, and the issue it waits on.
function Pending({ what, why, issue, lines = 2 }: { what: string; why: string; issue: number; lines?: number }) {
  return (
    <div className="pending">
      <div className="skeleton" aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <span key={i} className="skeleton-line" style={{ width: `${90 - i * 22}%` }} />
        ))}
      </div>
      <p className="small">
        <strong>{what}</strong> <span className="muted">· not measured yet. {why}</span>{' '}
        <a href={issueUrl(issue)} target="_blank" rel="noreferrer">
          #{issue}
        </a>
      </p>
    </div>
  )
}

// --- A · What is in play ------------------------------------------------------

function Pipeline({ data }: { data: DashboardMetrics }) {
  const blocks = byCurrency(data.pipeline.by_stage)
  const { committed } = data.pipeline

  return (
    <Panel title="What is in play" when="Now">
      <p className="muted small">
        One block per currency; amounts are never added across them. Deals priced by rate with no volume estimate are
        counted as open-ended next to the amount, never as zero.
      </p>
      {blocks.length === 0 && <p className="muted">No deals in play.</p>}
      {blocks.map((block) => {
        const max = largest(block.rows)
        return (
          <div key={block.currency} className="numbers-scroll">
            <table className="numbers-table">
              <caption>
                {block.currency} · {block.count} open {block.count === 1 ? 'deal' : 'deals'}
                {block.openEnded > 0 && `, ${block.openEnded} open-ended`}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Stage</th>
                  <th scope="col" className="numbers-bar-col" aria-label="Share of the largest" />
                  <th scope="col" className="col-num">
                    Deals
                  </th>
                  <th scope="col" className="col-num">
                    Value
                  </th>
                  <th scope="col" className="col-num">
                    Open-ended
                  </th>
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row) => {
                  const pair = moneyPair(row)
                  return (
                    <tr key={row.stage}>
                      <th scope="row">{stageLabel(row.stage)}</th>
                      <td className="numbers-bar-col">
                        <Bar ratio={share(row.value, max)} />
                      </td>
                      <td className="col-num">{row.count}</td>
                      <td className="col-num">{pair.amount}</td>
                      <td className="col-num">
                        {row.open_ended > 0 ? (
                          <span className="badge" data-tone="warning">
                            {row.open_ended}
                          </span>
                        ) : (
                          <span className="muted">–</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      })}

      <ul className="rows">
        <li>
          <span className="label">Committed, not delivered (won and running)</span>
          <span className="row-side">
            {committed.length === 0 ? (
              <span className="muted">nothing</span>
            ) : (
              committed.map((m) => {
                const pair = moneyPair(m)
                return (
                  <span key={m.currency} className="numbers-money">
                    {pair.amount}
                    {pair.openEnded && <span className="muted"> · {pair.openEnded}</span>}
                  </span>
                )
              })
            )}
          </span>
        </li>
      </ul>
      <Pending
        what="Weighted pipeline"
        why="Needs a default probability per stage; today it would be a sum over whichever deals happen to have one."
        issue={120}
        lines={1}
      />
    </Panel>
  )
}

function Bar({ ratio }: { ratio: number }) {
  return (
    <span className="numbers-bar" aria-hidden="true">
      {ratio > 0 && <span style={{ width: `${Math.max(ratio * 100, 1)}%` }} />}
    </span>
  )
}

// --- B · Is it moving ---------------------------------------------------------

function Velocity({ data }: { data: DashboardMetrics }) {
  const { velocity } = data
  const label = periodLabel(data.period.kind)
  const entered = (stage: string) => velocity.entered.find((e) => e.stage === stage)?.count ?? 0
  const cycle = velocity.sales_cycle

  // Won and lost are not rows here: "Did it come off" has them, with their
  // value, and two counts of the same thing would sooner or later disagree.
  return (
    <Panel title="Is it moving" when={`Now · ${label}`}>
      <div className="numbers-scroll">
        <table className="numbers-table">
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col" className="col-num">
                Median in stage
              </th>
              <th scope="col">Oldest open deal</th>
              <th scope="col" className="col-num">
                Entered · {label.toLowerCase()}
              </th>
              <th scope="col" className="col-num">
                Went further
              </th>
            </tr>
          </thead>
          <tbody>
            {IN_PLAY.map((stage) => {
              const now = velocity.by_stage.find((s) => s.stage === stage)
              const conversion = velocity.conversion.find((c) => c.stage === stage)
              const rate = conversion && conversionRate(conversion.entered, conversion.advanced)
              return (
                <tr key={stage}>
                  <th scope="row">
                    {stageLabel(stage)}
                    {now && <span className="muted"> · {now.count}</span>}
                  </th>
                  <td className="col-num">{formatMedian(now?.median_days_in_stage)}</td>
                  <td>
                    {now ? (
                      <span className="row-main">
                        <Link to="/deals/$dealId" params={{ dealId: now.oldest.id }} className="row-link">
                          {now.oldest.title}
                        </Link>
                        <span className="row-meta">{daysText(now.oldest.days_in_stage)} in stage</span>
                      </span>
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                  <td className="col-num">{entered(stage)}</td>
                  <td className="col-num">
                    {rate == null ? (
                      <span className="muted">–</span>
                    ) : (
                      <span title={`${conversion!.advanced} of ${conversion!.entered} deals, all time`}>
                        {rate}%
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <ul className="rows">
        <li>
          <span className="label">Median days from opening a deal to winning it</span>
          <span className="row-side">
            {cycle.median_days == null ? (
              <span className="muted">no deal won {label.toLowerCase()}</span>
            ) : (
              <>
                {formatMedian(cycle.median_days)}{' '}
                <span className="muted">
                  over {cycle.deals} {cycle.deals === 1 ? 'deal' : 'deals'}
                </span>
              </>
            )}
          </span>
        </li>
      </ul>
      <p className="muted small">
        Medians, not means: one deal parked for a year would drag a mean. “Went further” counts every deal that ever
        entered the stage and later reached one further along; moving to lost does not count.
      </p>
    </Panel>
  )
}

// --- C · Did it come off ------------------------------------------------------

function Outcomes({ data }: { data: DashboardMetrics }) {
  const { outcomes } = data
  const label = periodLabel(data.period.kind)
  const won = dealCount(outcomes.won)
  const decided = won + dealCount(outcomes.lost)
  const byCount = percent(outcomes.win_rate_by_count)

  return (
    <Panel title="Did it come off" when={label}>
      <ul className="rows">
        <li>
          <span className="label">Won</span>
          <span className="row-side">
            <OutcomeSide rows={outcomes.won} />
          </span>
        </li>
        <li>
          <span className="label">Lost</span>
          <span className="row-side">
            <OutcomeSide rows={outcomes.lost} />
          </span>
        </li>
        <li>
          <span className="label">Win rate by count</span>
          <span className="row-side">
            {byCount == null ? (
              <span className="muted">nothing decided {label.toLowerCase()}</span>
            ) : (
              <>
                {byCount}%{' '}
                <span className="muted">
                  {won} of {dealsText(decided)}
                </span>
              </>
            )}
          </span>
        </li>
        <li>
          <span className="label">Win rate by value</span>
          <span className="row-side">
            {outcomes.win_rate_by_value.length === 0 ? (
              <span className="muted">nothing decided {label.toLowerCase()}</span>
            ) : (
              outcomes.win_rate_by_value.map((r) => {
                const rate = percent(r.rate)
                return (
                  <span key={r.currency} className="numbers-money">
                    {rate == null ? <span className="muted">no amounts in {r.currency}</span> : `${rate}% ${r.currency}`}
                  </span>
                )
              })
            )}
          </span>
        </li>
      </ul>
      <p className="muted small">
        Deals decided in the period, as they stand now: one lost and then won after all is a win, one reopened is in
        neither. The two rates differ when the big deals are the lost ones. Open-ended deals count, and have no amount
        to weigh.
      </p>
      <Pending
        what="Lost reasons, win rate by source"
        why="Free-text reasons cannot be grouped, and a deal has no source yet."
        issue={118}
      />
    </Panel>
  )
}

// One side of the outcomes: per currency the deals and what they were worth.
function OutcomeSide({ rows }: { rows: MoneyByCurrency[] }) {
  if (rows.length === 0) return <span className="muted">none</span>
  return (
    <>
      {rows.map((m) => {
        const pair = moneyPair(m)
        return (
          <span key={m.currency} className="numbers-money">
            {dealsText(m.count)} <span className="muted">·</span> {pair.amount}
            {pair.openEnded && <span className="muted"> · {pair.openEnded}</span>}
          </span>
        )
      })}
    </>
  )
}

// --- D · What is rotting ------------------------------------------------------

function Attention({ data }: { data: DashboardMetrics }) {
  const { attention } = data
  const captureAge = attention.captures_waiting.oldest_days

  return (
    <Panel title="What is rotting" when="Now">
      <ul className="rows numbers-attention">
        <AttentionItem
          row={attention.stalled_deals}
          label="Open deals with no next step"
          link={{ to: '/deals', search: { scope: 'stalled', view: 'list' } }}
        />
        <AttentionItem
          row={attention.overdue_deals}
          label="Open deals past their expected close"
          link={{ to: '/deals', search: { scope: 'overdue', view: 'list' } }}
        />
        <AttentionItem row={attention.overdue_tasks} label="Overdue tasks" link={{ to: '/' }} tone="danger" />
        <AttentionItem
          row={attention.unconfirmed_interactions}
          label="Planned interactions never confirmed"
          link={{ to: '/' }}
        />
        <AttentionItem
          row={attention.captures_waiting}
          label="Captures waiting"
          hint={captureAge != null && captureAge > 0 ? `oldest ${daysText(captureAge)}` : undefined}
          link={{ to: '/inbox' }}
        />
      </ul>
      <Pending
        what="Lost deals due to be revisited"
        why="Needs a revisit date on lost deals."
        issue={118}
        lines={1}
      />
      <Pending
        what="Contacts awaiting a reply"
        why="Needs a direction on interactions."
        issue={135}
        lines={1}
      />
      <Pending
        what="Contacts untouched for 90 days"
        why="Waits on deciding which contacts are worth touching."
        issue={271}
        lines={1}
      />
    </Panel>
  )
}

function AttentionItem({
  row,
  label,
  hint,
  link,
  tone = 'warning',
}: {
  row: AttentionRow
  label: string
  hint?: string
  link: Pick<LinkProps, 'to' | 'search'>
  tone?: 'warning' | 'danger'
}) {
  return (
    <li className="numbers-attention-row" data-tone={row.count > 0 ? tone : undefined}>
      <span className="queue-count">{row.count}</span>
      <span className="row-main">
        <Link {...link} className="row-link">
          {label}
        </Link>
        {hint && <span className="row-meta">{hint}</span>}
      </span>
    </li>
  )
}

// --- E · Am I doing the work --------------------------------------------------

function Activity({ data }: { data: DashboardMetrics }) {
  const { activity } = data
  const label = periodLabel(data.period.kind)
  const kinds = [...activity.interactions_by_kind].sort((a, b) => b.count - a.count)
  const most = Math.max(1, ...kinds.map((k) => k.count))

  return (
    <Panel title="Am I doing the work" when={label}>
      <div className="numbers-activity">
        <div className="numbers-activity-col">
          <h3>Interactions that happened, by kind</h3>
          <ul className="numbers-kinds">
            {kinds.map((k) => (
              <li key={k.kind}>
                <span className="numbers-kind">{k.kind}</span>
                <Bar ratio={k.count / most} />
                <span className="col-num">{k.count}</span>
              </li>
            ))}
          </ul>
          <Pending
            what="Outbound vs inbound"
            why="Needs a direction on interactions."
            issue={135}
            lines={1}
          />
        </div>
        <div className="numbers-activity-col">
          <h3>Throughput</h3>
          <ul className="rows">
            <li>
              <span className="label">Deals opened</span>
              <span className="row-side">{activity.deals_opened}</span>
            </li>
            <li>
              <span className="label">Captures converted</span>
              <span className="row-side">{activity.captures_converted}</span>
            </li>
            <li>
              <span className="label">Captures dismissed</span>
              <span className="row-side">{activity.captures_dismissed}</span>
            </li>
            <li>
              <span className="label">Tasks created</span>
              <span className="row-side">{activity.tasks_created}</span>
            </li>
            <li>
              <span className="label">Tasks completed</span>
              <span className="row-side">{activity.tasks_completed}</span>
            </li>
          </ul>
        </div>
      </div>
      <div className="numbers-activity-col">
        <h3>New deals per week · last 10 weeks</h3>
        <WeeklyDeals weeks={data.trends.deals_opened_weekly} />
      </div>
    </Panel>
  )
}

// --- F · Delivery -------------------------------------------------------------

function Delivery() {
  return (
    <Panel title="Delivery" when="Not measured yet" pending>
      <Pending
        what="Running engagements, completed projects, projects without activity"
        why="Needs a project to link to the deal that paid for it."
        issue={119}
        lines={3}
      />
    </Panel>
  )
}
