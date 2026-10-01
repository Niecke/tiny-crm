import { describe, expect, test } from 'vitest'
import { statusOf } from './projects'

describe('statusOf', () => {
  const on = '2026-10-01'

  test.each([
    [{ start_date: '2026-01-01', end_date: '2026-09-30' }, 'completed'],
    [{ start_date: '2026-10-02', end_date: null }, 'upcoming'],
    [{ start_date: '2026-10-01', end_date: null }, 'active'],
    [{ start_date: '2026-01-01', end_date: '2026-10-01' }, 'active'],
  ])('%o is %s', (project, expected) => {
    expect(statusOf(project, on)).toBe(expected)
  })
})
