import { type CalendarDate, isSameDay, startOfMonth, endOfMonth, today } from '@internationalized/date'
import { useQuery } from '@tanstack/react-query'
import { Link, useRouteContext } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Calendar, CalendarCell, CalendarGrid, CalendarGridBody, CalendarGridHeader, CalendarHeaderCell, Dialog, Heading, Popover } from 'react-aria-components'
import type { InteractionRead } from '../api/types'
import { formatTime } from '../format'
import { calendarInteractionsQuery, isPlanned, kindLabel } from '../interactions'
import { RecordName } from './LinksPicker'

// The month at a glance: a dot under each day with something logged (solid)
// or planned (ring); a day opens the list of what is on it. Weeks start on
// Monday. Days are days in the briefing's timezone, the one the times are
// shown in, so an entry sits under the day its displayed time belongs to.
export function InteractionCalendar({ timezone }: { timezone: string }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const zone = timezone
  const dayKey = useMemo(() => new Intl.DateTimeFormat('en-CA', { timeZone: zone }), [zone])
  const [focused, setFocused] = useState<CalendarDate>(() => today(zone))
  const [selected, setSelected] = useState<CalendarDate | null>(null)
  const anchor = useRef<HTMLDivElement>(null)
  const [now, setNow] = useState(() => Date.now())

  // A planned entry turns into a logged one as its time passes, also on a
  // dashboard left open: tick, and catch up when the tab comes back.
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const timer = setInterval(tick, 60_000)
    window.addEventListener('focus', tick)
    return () => {
      clearInterval(timer)
      window.removeEventListener('focus', tick)
    }
  }, [])

  // The whole visible grid, first Monday to last Sunday, so the neighbouring
  // months' days carry their dots too. The end bound is inclusive: stop a
  // millisecond short of the next day (an entry in the last sub-millisecond
  // of the grid is the one thing that can slip through).
  const first = startOfMonth(focused)
  const last = endOfMonth(focused)
  const weekday = (d: CalendarDate) => new Date(Date.UTC(d.year, d.month - 1, d.day)).getUTCDay()
  const gridStart = first.subtract({ days: (weekday(first) + 6) % 7 })
  const gridEnd = last.add({ days: (7 - weekday(last)) % 7 })
  const range = {
    occurred_after: gridStart.toDate(zone).toISOString(),
    occurred_before: new Date(gridEnd.add({ days: 1 }).toDate(zone).getTime() - 1).toISOString(),
  }
  const interactions = useQuery(calendarInteractionsQuery(api, range))

  const byDay = useMemo(() => {
    const days = new Map<string, InteractionRead[]>()
    for (const i of interactions.data?.items ?? []) {
      const day = dayKey.format(new Date(i.occurred_at))
      const list = days.get(day)
      if (list) list.push(i)
      else days.set(day, [i])
    }
    for (const list of days.values()) list.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at))
    return days
  }, [interactions.data, dayKey])

  const dayItems = selected ? (byDay.get(selected.toString()) ?? []) : []

  return (
    <section className="panel interaction-calendar" aria-label="Calendar">
      <div className="panel-body" ref={anchor}>
        {interactions.error && <p className="form-error">{interactions.error.message}</p>}
        <Calendar
          className="calendar"
          aria-label="Interactions"
          firstDayOfWeek="mon"
          focusedValue={focused}
          onFocusChange={setFocused}
          value={selected}
          onChange={setSelected}
        >
          <header className="calendar-header">
            <Button slot="previous" className="button button-quiet" aria-label="Previous month">
              ‹
            </Button>
            <Heading className="calendar-heading" />
            <Button
              slot={null}
              className="button button-quiet"
              onPress={() => setFocused(today(zone))}
              isDisabled={isSameDay(focused, today(zone))}
            >
              Today
            </Button>
            <Button slot="next" className="button button-quiet" aria-label="Next month">
              ›
            </Button>
          </header>
          <CalendarGrid className="calendar-grid">
            <CalendarGridHeader>{(day) => <CalendarHeaderCell>{day}</CalendarHeaderCell>}</CalendarGridHeader>
            <CalendarGridBody>
              {(date) => {
                const items = byDay.get(date.toString()) ?? []
                const logged = items.some((i) => !isPlanned(i, now) || i.done)
                const planned = items.some((i) => isPlanned(i, now) && !i.done)
                const plannedCount = items.filter((i) => isPlanned(i, now) && !i.done).length
                const summary = items.length
                  ? `, ${items.length} ${items.length === 1 ? 'interaction' : 'interactions'}${plannedCount ? `, ${plannedCount} planned` : ''}`
                  : ''
                return (
                  <CalendarCell date={date} className="calendar-cell">
                    {({ formattedDate }) => (
                      <>
                        <span>{formattedDate}</span>
                        {summary && <span className="sr-only">{summary}</span>}
                        <span className="calendar-dots" aria-hidden="true">
                          {logged && <span className="calendar-dot" data-state="logged" />}
                          {planned && <span className="calendar-dot" data-state="planned" />}
                        </span>
                      </>
                    )}
                  </CalendarCell>
                )
              }}
            </CalendarGridBody>
          </CalendarGrid>
        </Calendar>
      </div>
      <Popover
        className="popover day-popover"
        triggerRef={anchor}
        isOpen={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
        placement="bottom"
      >
        <Dialog className="calendar-dialog" aria-label={selected ? `Interactions on ${dayLabel(selected, zone)}` : 'Interactions'}>
          {interactions.isPending || interactions.isPlaceholderData ? (
            <p className="muted small">Loading…</p>
          ) : interactions.isError && !interactions.data ? (
            <p className="form-error">{interactions.error.message}</p>
          ) : dayItems.length === 0 ? (
            <p className="muted small">Nothing on this day.</p>
          ) : (
            <ul className="rows">
              {dayItems.map((i) => (
                <DayItem key={i.id} interaction={i} timezone={timezone} />
              ))}
            </ul>
          )}
        </Dialog>
      </Popover>
    </section>
  )
}

const dayLabel = (date: CalendarDate, zone: string) =>
  date.toDate(zone).toLocaleDateString(undefined, { timeZone: zone, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

function DayItem({ interaction: i, timezone }: { interaction: InteractionRead; timezone: string }) {
  return (
    <li className="interaction-row">
      <span className="row-main">
        <span>
          <span className="badge kind-badge" data-kind={i.kind}>
            {kindLabel(i.kind)}
          </span>{' '}
          <Link to="/interactions/$interactionId" params={{ interactionId: i.id }} className="row-link">
            {i.subject}
          </Link>
        </span>
        <span className="row-meta">
          {formatTime(i.occurred_at, timezone)}
          {[
            ...i.contact_ids.map((id) => ({ kind: 'contact' as const, id })),
            ...i.organization_ids.map((id) => ({ kind: 'organization' as const, id })),
          ].map((r, n) => (
            <span key={r.id}>
              {n === 0 ? ' · ' : ', '}
              {r.kind === 'contact' ? (
                <Link to="/contacts/$contactId" params={{ contactId: r.id }} className="row-link">
                  <RecordName kind="contact" id={r.id} />
                </Link>
              ) : (
                <Link to="/organizations/$organizationId" params={{ organizationId: r.id }} className="row-link">
                  <RecordName kind="organization" id={r.id} />
                </Link>
              )}
            </span>
          ))}
        </span>
      </span>
    </li>
  )
}
