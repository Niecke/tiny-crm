import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { InteractionRead } from '../api/types'
import { withQueryClient } from '../test/query'
import { http, server, testApi } from '../test/server'
import { InteractionCalendar } from './InteractionCalendar'

vi.mock('@tanstack/react-router', () => ({
  useRouteContext: () => ({ api: testApi() }),
  Link: ({ children, params, className }: { children: ReactNode; params?: Record<string, string>; className?: string }) => (
    <a href={`/${Object.values(params ?? {}).join('/')}`} className={className}>
      {children}
    </a>
  ),
}))

const interaction = (overrides: Partial<InteractionRead>): InteractionRead =>
  ({
    id: 'i-1',
    kind: 'call',
    subject: 'Kickoff call',
    occurred_at: '2026-06-10T10:00:00',
    done: false,
    notes: null,
    tags: [],
    contact_ids: [],
    organization_ids: [],
    deal_ids: [],
    project_ids: [],
    ...overrides,
  }) as InteractionRead

// Local noon, so the timezone cannot move an entry onto another day.
const at = (day: number) => new Date(2026, 5, day, 12, 0).toISOString()

const heading = () => document.querySelector('.calendar-heading')?.textContent

function serve(items: InteractionRead[]) {
  const ranges: { after: string | null; before: string | null }[] = []
  server.use(
    http.get('/interactions/', ({ query, response }) => {
      ranges.push({ after: query.get('occurred_after'), before: query.get('occurred_before') })
      return response(200).json({ items, total: items.length, skip: 0, limit: 200 })
    }),
    http.get('/contacts/{contact_id}', ({ response }) =>
      response(200).json({ id: 'c-1', name: 'Ada Lovelace' } as never),
    ),
  )
  return ranges
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 5, 15, 9, 0) })
})
afterEach(() => vi.useRealTimers())

describe('InteractionCalendar', () => {
  test('starts the week on Monday', async () => {
    serve([])
    const { wrapper } = withQueryClient()
    render(<InteractionCalendar />, { wrapper })

    const headers = [...document.querySelectorAll('.calendar-grid th')].map((h) => h.textContent)
    expect(headers[0]).toMatch(/^M/)
    expect(headers[6]).toMatch(/^S/)
    expect(headers).toHaveLength(7)
    // 1 June 2026 is a Monday: it sits in the first column of the first row.
    const first = screen.getAllByRole('row')[0]
    expect(within(first).getAllByRole('gridcell')[0]).toHaveTextContent('1')
  })

  test('marks logged and planned days differently', async () => {
    serve([
      interaction({ id: 'a', occurred_at: at(10) }),
      interaction({ id: 'b', occurred_at: at(20) }),
    ])
    const { wrapper } = withQueryClient()
    render(<InteractionCalendar />, { wrapper })

    await screen.findAllByRole('button', { name: /June 10, 2026/ })
    await vi.waitFor(() => expect(document.querySelectorAll('.calendar-dot')).toHaveLength(2))
    const logged = document.querySelector('.calendar-dot[data-state="logged"]')
    const planned = document.querySelector('.calendar-dot[data-state="planned"]')
    expect(logged?.closest('.calendar-cell')).toHaveTextContent('10')
    expect(planned?.closest('.calendar-cell')).toHaveTextContent('20')
  })

  test('moves between months and back with Today', async () => {
    const ranges = serve([])
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const { wrapper } = withQueryClient()
    render(<InteractionCalendar />, { wrapper })

    expect(heading()).toBe('June 2026')
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(heading()).toBe('July 2026')
    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    expect(heading()).toBe('May 2026')
    await user.click(screen.getByRole('button', { name: 'Today' }))
    expect(heading()).toBe('June 2026')

    // Each month asks for its own window.
    await vi.waitFor(() => expect(ranges.length).toBeGreaterThanOrEqual(3))
    expect(new Date(ranges[0].after as string).getMonth()).toBe(5)
  })

  test('opens a day with its interactions and links', async () => {
    serve([interaction({ id: 'a', occurred_at: at(10), subject: 'Kickoff call', contact_ids: ['c-1'] })])
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const { wrapper } = withQueryClient()
    render(<InteractionCalendar />, { wrapper })

    await vi.waitFor(() => expect(document.querySelector('.calendar-dot')).not.toBeNull())
    await user.click(screen.getByRole('button', { name: /June 10, 2026/ }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('link', { name: 'Kickoff call' })).toHaveAttribute('href', '/a')
    expect(within(dialog).getByText('Call')).toBeInTheDocument()
    expect(await within(dialog).findByRole('link', { name: 'Ada Lovelace' })).toHaveAttribute('href', '/c-1')
  })
})
