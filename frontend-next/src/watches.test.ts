import { describe, expect, test } from 'vitest'
import { watch } from './test/fixtures'
import { cadenceLabel, dueLabel, isDue, safeUrl } from './watches'

const now = Date.parse('2026-10-01T12:00:00Z')

describe('isDue', () => {
  test('due once the date has come', () => {
    expect(isDue(watch({ next_due_at: '2026-10-01T12:00:00Z' }), now)).toBe(true)
    expect(isDue(watch({ next_due_at: '2026-10-02T12:00:00Z' }), now)).toBe(false)
  })

  test('a paused source is never due', () => {
    expect(isDue(watch({ active: false, next_due_at: '2026-09-01T00:00:00Z' }), now)).toBe(false)
  })
})

describe('dueLabel', () => {
  test('never checked comes first', () => {
    expect(dueLabel(watch({ last_checked_at: null, next_due_at: '2026-09-01T00:00:00Z' }), now)).toBe('Never checked')
  })

  test('not yet due shows the day', () => {
    expect(dueLabel(watch({ next_due_at: '2026-10-08T08:00:00Z' }), now)).toBe('Due Oct 8, 2026')
  })

  test.each([
    ['2026-10-01T08:00:00Z', 'Due today'],
    ['2026-09-30T08:00:00Z', '1 day overdue'],
    ['2026-09-28T08:00:00Z', '3 days overdue'],
  ])('due %s reads "%s"', (next_due_at, expected) => {
    expect(dueLabel(watch({ next_due_at }), now)).toBe(expected)
  })
})

describe('cadenceLabel', () => {
  test.each([
    ['weekly', 1, 'Every week'],
    ['monthly', 2, 'Every 2 months'],
    ['daily', 3, 'Every 3 days'],
  ] as const)('%s every %i', (recurrence_rule, recurrence_interval, expected) => {
    expect(cadenceLabel({ recurrence_rule, recurrence_interval })).toBe(expected)
  })
})

describe('safeUrl', () => {
  test('keeps http and https as they are', () => {
    expect(safeUrl('https://example.com/jobs')).toBe('https://example.com/jobs')
    expect(safeUrl('HTTP://example.com')).toBe('HTTP://example.com')
  })

  test('adds https to a bare host', () => {
    expect(safeUrl('example.com/jobs')).toBe('https://example.com/jobs')
  })

  test('never yields a javascript: link', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('https://alert(1)')
    expect(safeUrl('JavaScript:alert(1)')).toMatch(/^https:\/\//)
  })
})
