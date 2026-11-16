import { describe, expect, test } from 'vitest'
import type { ProposalRead } from './api/types'
import { actionTitle, diffRows, fieldLabel, formatValue } from './proposals'

const proposal = (over: Partial<ProposalRead>): ProposalRead => ({
  id: 'p1',
  entity_type: 'contact',
  action: 'update',
  target_id: 'c1',
  proposed_payload: {},
  applied_payload: null,
  reason: 'why',
  status: 'pending',
  rejection_reason: null,
  created_at: '2026-11-16T10:00:00Z',
  reviewed_at: null,
  token_name: 'claude-code',
  current: null,
  target_label: null,
  ...over,
})

describe('fieldLabel', () => {
  test('words a key for a person', () => {
    expect(fieldLabel('contact', 'job_title')).toBe('Job title')
    expect(fieldLabel('contact', 'city')).toBe('City')
  })

  test('has its own wording for ids and dates', () => {
    expect(fieldLabel('contact', 'organization_id')).toBe('Organization')
    expect(fieldLabel('interaction', 'contact_ids')).toBe('Contacts')
    expect(fieldLabel('task', 'due_date')).toBe('Due')
  })
})

describe('formatValue', () => {
  const labels = { 'o-1': 'ACME GmbH', 'c-1': 'Maria' }

  test('blank values show a dash', () => {
    expect(formatValue(null)).toBe('—')
    expect(formatValue(undefined)).toBe('—')
    expect(formatValue('')).toBe('—')
    expect(formatValue([])).toBe('—')
  })

  test('booleans read as yes and no', () => {
    expect(formatValue(true)).toBe('Yes')
    expect(formatValue(false)).toBe('No')
  })

  test('ids become names, and arrays are joined', () => {
    expect(formatValue('o-1', labels)).toBe('ACME GmbH')
    expect(formatValue(['c-1', 'x-9'], labels)).toBe('Maria, x-9')
    expect(formatValue(['vip', 'lead'])).toBe('vip, lead')
  })

  test('numbers pass through', () => {
    expect(formatValue(40)).toBe('40')
    expect(formatValue(0)).toBe('0')
  })
})

describe('diffRows', () => {
  test('an update marks what changes and what does not', () => {
    const rows = diffRows(
      proposal({
        proposed_payload: { job_title: 'CTO', city: 'Wien', organization_id: 'o-1' },
        current: { job_title: 'Engineer', city: 'Wien', organization_id: null, version: 3 },
      }),
      { 'o-1': 'ACME GmbH' },
    )
    expect(rows).toEqual([
      { field: 'Job title', current: 'Engineer', proposed: 'CTO', changed: true },
      { field: 'City', current: 'Wien', proposed: 'Wien', changed: false },
      { field: 'Organization', current: '—', proposed: 'ACME GmbH', changed: true },
    ])
  })

  test('a create has nothing to compare against', () => {
    const rows = diffRows(
      proposal({ action: 'create', target_id: null, proposed_payload: { name: 'Maria', tags: ['vip'] } }),
    )
    expect(rows).toEqual([
      { field: 'Name', current: null, proposed: 'Maria', changed: true },
      { field: 'Tags', current: null, proposed: 'vip', changed: true },
    ])
  })

  test('shows what was applied once the reviewer edited it', () => {
    const rows = diffRows(
      proposal({ action: 'create', proposed_payload: { name: 'Maria Hubr' }, applied_payload: { name: 'Maria Huber' } }),
    )
    expect(rows[0].proposed).toBe('Maria Huber')
  })
})

describe('actionTitle', () => {
  test('says what and to which kind of record', () => {
    expect(actionTitle({ action: 'create', entity_type: 'contact' })).toBe('New contact')
    expect(actionTitle({ action: 'update', entity_type: 'deal' })).toBe('Update deal')
    expect(actionTitle({ action: 'archive', entity_type: 'task' })).toBe('Archive task')
  })
})
