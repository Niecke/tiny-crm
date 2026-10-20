import { type CalendarDate, getLocalTimeZone, isSameDay, startOfMonth, endOfMonth, today } from '@internationalized/date'
import { useQuery } from '@tanstack/react-query'
import { Link, useRouteContext } from '@tanstack/react-router'
import { useMemo, useRef, useState } from 'react'
import { Button, Calendar, CalendarCell, CalendarGrid, CalendarGridBody, CalendarGridHeader, CalendarHeaderCell, Dialog, Heading, Popover } from 'react-aria-components'
import type { InteractionRead } from '../api/types'
import { localDay } from '../format'
import { calendarInteractionsQuery, isPlanned, kindLabel } from '../interactions'
import { RecordName } from './LinksPicker'

const formatTime = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

// The month at a glance: a dot under each day with something logged (solid)
// or planned (ring); a day opens the list of what is on it. Weeks start on
// Monday. Days are the operator's local days, as everywhere else.
export function InteractionCalendar() {
  const { api } = useRouteContext({ from: '/_authed' })
  const zone = getLocalTimeZone()
  const [focused, setFocused] = useState<CalendarDate>(() => today(zone))
  const [selected, setSelected] = useState<CalendarDate | null>(null)
  const anchor = useRef<HTMLDivElement>(null)
  // Fixed per render of the page, like the lists: a dot does not flip as the
  // clock ticks.
  const [now] = useState(() => Date.now())

  // The end bound is inclusive: stop a millisecond short of the next month.
  const range = {
    occurred_after: startOfMonth(focused).toDate(zone).toISOString(),
    occurred_before: new Date(endOfMonth(focused).add({ days: 1 }).toDate(zone).getTime() - 1).toISOString(),
  }
  const interactions = useQuery(calendarInteractionsQuery(api, range))

  const byDay = useMemo(() => {
    const days = new Map<string, InteractionRead[]>()
    for (const i of interactions.data?.items ?? []) {
      const day = localDay(i.occurred_at)
      days.set(day, [...(days.get(day) ?? []), i])
    }
    for (const list of days.values()) list.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at))
    return days
  }, [interactions.data])

  const dayItems = selected ? (byDay.get(selected.toString()) ?? []) : []

  return (
    <section className="panel interaction-calendar" aria-label="Calendar">
      <div className="panel-body" ref={anchor}>
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
              isDisabled={isSameDay(startOfMonth(focused), startOfMonth(today(zone)))}
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
                return (
                  <CalendarCell
                    date={date}
                    className="calendar-cell"
                    data-current={isSameDay(date, today(zone)) || undefined}
                  >
                    {({ formattedDate }) => (
                      <>
                        <span>{formattedDate}</span>
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
        <Dialog className="calendar-dialog" aria-label={selected ? `Interactions on ${selected.toString()}` : 'Interactions'}>
          {dayItems.length === 0 ? (
            <p className="muted small">Nothing on this day.</p>
          ) : (
            <ul className="rows">
              {dayItems.map((i) => (
                <DayItem key={i.id} interaction={i} />
              ))}
            </ul>
          )}
        </Dialog>
      </Popover>
    </section>
  )
}

function DayItem({ interaction: i }: { interaction: InteractionRead }) {
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
          {formatTime(i.occurred_at)}
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
