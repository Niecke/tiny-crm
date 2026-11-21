import { render, screen, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import type { ProposalRead } from '../api/types'
import { ProposalCard } from './ProposalCard'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a href="/">{children}</a>,
  useRouteContext: () => ({}),
}))

const notes = 'First paragraph with several words.\n\nSecond paragraph with more words.'

const update: ProposalRead = {
  id: 'p1',
  entity_type: 'organization',
  action: 'update',
  target_id: 'o1',
  proposed_payload: { notes: `${notes}\n\nAdded.`, city: 'Vienna' },
  reason: 'Refresh the notes',
  status: 'pending',
  created_at: '2026-11-21T10:00:00Z',
  token_name: 'agent',
  target_label: 'andromeda Software GmbH',
  current: { version: 1, notes, city: 'Vienna' },
} as ProposalRead

describe('ProposalCard update diff', () => {
  test('gives the field column its own col and labels the value cells', () => {
    const { container } = render(
      <ul>
        <ProposalCard proposal={update} labels={{}} onApprove={() => {}} onReject={() => {}} />
      </ul>,
    )
    const table = container.querySelector('table.proposal-diff') as HTMLElement
    expect(table.querySelectorAll('colgroup > col')).toHaveLength(3)
    expect(table.querySelector('col.proposal-diff-field')).not.toBeNull()
    const cells = table.querySelectorAll('tbody td')
    expect(cells.length).toBeGreaterThan(0)
    cells.forEach((td, i) => expect(td.getAttribute('data-label')).toBe(i % 2 === 0 ? 'Current' : 'Proposed'))
  })

  test('marks only the rows that change', () => {
    render(
      <ul>
        <ProposalCard proposal={update} labels={{}} onApprove={() => {}} onReject={() => {}} />
      </ul>,
    )
    const notesRow = screen.getByRole('rowheader', { name: 'Notes' }).closest('tr') as HTMLElement
    const cityRow = screen.getByRole('rowheader', { name: 'City' }).closest('tr') as HTMLElement
    expect(notesRow).toHaveAttribute('data-changed')
    expect(cityRow).not.toHaveAttribute('data-changed')
    expect(within(notesRow).getAllByRole('cell')[1]).toHaveTextContent('Added.')
  })
})
