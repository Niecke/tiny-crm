import { queryOptions, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { type Api, unwrap } from '../../api/client'
import type { BriefingInteraction, BriefingRead, BriefingTask } from '../../api/types'
import { PriorityBadge } from '../../components/PriorityBadge'

// The morning briefing, as data (GET /briefing). The same function builds the
// 07:00 Slack message, so this page and that message agree on what today is
// and what is late — the day counts come from the server, in its timezone.
const briefingQuery = (api: Api) =>
  queryOptions({
    queryKey: ['briefing'],
    queryFn: () => unwrap(api.GET('/briefing/')),
    // "Today" moves on its own; refetch when the tab comes back into view.
    refetchOnWindowFocus: true,
  })

const openDealsQuery = (api: Api) =>
  queryOptions({
    queryKey: ['count', 'deals', 'open'],
    queryFn: async () => (await unwrap(api.GET('/deals/', { params: { query: { limit: 1, status: 'open' } } }))).total,
  })

export const Route = createFileRoute('/_authed/')({
  component: Dashboard,
})

function Dashboard() {
  const { api } = Route.useRouteContext()
  const briefing = useQuery(briefingQuery(api))

  return (
    <div className="page">
      <header className="page-header">
        <h1>Today</h1>
        {briefing.data && <p>{formatDay(briefing.data.date)}</p>}
      </header>

      <div className="dashboard">
        <section className="panel" aria-label="Today">
          <div className="panel-body">
            {briefing.isPending ? (
              <p className="muted">Loading…</p>
            ) : briefing.error ? (
              <p className="form-error">{briefing.error.message}</p>
            ) : (
              <TodayList briefing={briefing.data} />
            )}
          </div>
        </section>

        <Queues briefing={briefing.data} />
      </div>
    </div>
  )
}

// Your own commitments for the day: tasks, what is planned, and the entries
// that were planned and never confirmed.
function TodayList({ briefing }: { briefing: BriefingRead }) {
  const { overdue_tasks, tasks_today, interactions_today, unconfirmed_interactions, timezone } = briefing
  const tasks = [...overdue_tasks, ...tasks_today]

  if (tasks.length === 0 && interactions_today.length === 0 && unconfirmed_interactions.length === 0) {
    return <p className="today-clear">Nothing due today.</p>
  }

  return (
    <div className="today">
      {tasks.length > 0 && (
        <Group title="Tasks" count={tasks.length}>
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </Group>
      )}

      {interactions_today.length > 0 && (
        <Group title="Planned today" count={interactions_today.length}>
          {interactions_today.map((i) => (
            <InteractionRow key={i.id} interaction={i} when={formatTime(i.occurred_at, timezone)} />
          ))}
        </Group>
      )}

      {unconfirmed_interactions.length > 0 && (
        <Group
          title="Not confirmed"
          count={unconfirmed_interactions.length}
          note="Planned, the time has passed, never marked as happened. Until they are, the log is wrong."
        >
          {unconfirmed_interactions.map((i) => (
            <InteractionRow
              key={i.id}
              interaction={i}
              when={formatShortDate(i.occurred_at, timezone)}
              late={daysText(i.days_late, 'ago')}
            />
          ))}
        </Group>
      )}
    </div>
  )
}

function Group({ title, count, note, children }: { title: string; count: number; note?: string; children: ReactNode }) {
  return (
    <section className="today-group">
      <h2>
        {title} <span className="tab-count">{count}</span>
      </h2>
      {note && <p className="muted small">{note}</p>}
      <ul className="rows">{children}</ul>
    </section>
  )
}

function TaskRow({ task }: { task: BriefingTask }) {
  const about = [task.contact_name, task.deal_title, task.repeats && 'repeats'].filter(Boolean).join(' · ')
  return (
    <li>
      <span className="row-main">
        <span>
          {task.title}
          {task.priority > 0 && (
            <>
              {' '}
              <PriorityBadge priority={task.priority} />
            </>
          )}
        </span>
        {about && <span className="row-meta">{about}</span>}
      </span>
      {task.days_late > 0 ? (
        <span className="row-side late">{daysText(task.days_late, 'late')}</span>
      ) : (
        <span className="row-side muted">today</span>
      )}
    </li>
  )
}

function InteractionRow({
  interaction,
  when,
  late,
}: {
  interaction: BriefingInteraction
  when: string
  late?: string
}) {
  const meta = [
    when,
    interaction.kind,
    interaction.with_names.length > 0 && `with ${interaction.with_names.join(', ')}`,
    interaction.duration_minutes && `${interaction.duration_minutes} min`,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <li>
      <span className="row-main">
        <span>{interaction.subject}</span>
        <span className="row-meta">{meta}</span>
      </span>
      {late && <span className="row-side late">{late}</span>}
    </li>
  )
}

// Queues worked elsewhere: counted here, not listed. Amber when something is
// waiting, grey when it is clear.
function Queues({ briefing }: { briefing: BriefingRead | undefined }) {
  const { api } = Route.useRouteContext()
  const openDeals = useQuery(openDealsQuery(api))

  const captures = briefing?.captures_waiting
  const oldest = captures?.reduce((max, c) => Math.max(max, c.days_waiting), 0)
  const watches = briefing?.watches_due
  const neverSwept = watches?.filter((w) => w.never_swept).length

  return (
    <aside className="panel queues" aria-label="Waiting">
      <ul className="rows">
        <Queue
          label="Inbox"
          count={captures?.length}
          hint={oldest ? `oldest waiting ${daysText(oldest)}` : undefined}
          alert
        />
        <Queue
          label="Sources to sweep"
          count={watches?.length}
          hint={neverSwept ? `${neverSwept} never swept` : undefined}
          alert
        />
        <Queue label="Open deals" count={openDeals.data} />
      </ul>
    </aside>
  )
}

function Queue({ label, count, hint, alert }: { label: string; count: number | undefined; hint?: string; alert?: boolean }) {
  return (
    <li className="queue" data-tone={alert && count ? 'warning' : undefined}>
      <span className="row-main">
        <span>{label}</span>
        {hint && <span className="row-meta">{hint}</span>}
      </span>
      <span className="queue-count">{count ?? '–'}</span>
    </li>
  )
}

function daysText(days: number, suffix?: string): string {
  const text = days === 1 ? '1 day' : `${days} days`
  return suffix ? `${text} ${suffix}` : text
}

// The briefing's own date and timezone, so "today" and the times shown are
// the operator's — the same ones the Slack message printed.
function formatDay(isoDate: string): string {
  // Noon, so no timezone offset can move the date across midnight.
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

const formatTime = (iso: string, timeZone: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', timeZone })

const formatShortDate = (iso: string, timeZone: string) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', timeZone })
