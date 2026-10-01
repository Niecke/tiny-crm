import { describe, expect, test } from 'vitest'
import { formatDay } from './format'
import { isOverdue, recurrenceLabel } from './tasks'

describe('recurrenceLabel', () => {
  const task = { recurrence_rule: null, recurrence_interval: 1, recurrence_until: null }

  test('a one-off task has none', () => {
    expect(recurrenceLabel(task, formatDay)).toBeNull()
  })

  test('every single period reads as the rule', () => {
    expect(recurrenceLabel({ ...task, recurrence_rule: 'weekly' }, formatDay)).toBe('Repeats weekly')
  })

  test('larger intervals and an end date', () => {
    expect(
      recurrenceLabel(
        { recurrence_rule: 'monthly', recurrence_interval: 2, recurrence_until: '2026-12-31' },
        formatDay,
      ),
    ).toBe('Repeats every 2 months until Dec 31, 2026')
  })
})

describe('isOverdue', () => {
  const now = Date.parse('2026-10-01T12:00:00Z')

  test('past due and not done', () => {
    expect(isOverdue({ done: false, due_date: '2026-09-30T21:59:00Z' }, now)).toBe(true)
  })

  test('due later today is not late yet', () => {
    expect(isOverdue({ done: false, due_date: '2026-10-01T21:59:00Z' }, now)).toBe(false)
  })

  test('done or undated is never overdue', () => {
    expect(isOverdue({ done: true, due_date: '2026-09-01T21:59:00Z' }, now)).toBe(false)
    expect(isOverdue({ done: false, due_date: null }, now)).toBe(false)
    expect(isOverdue({ done: false }, now)).toBe(false)
  })
})
