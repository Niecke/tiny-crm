import { describe, expect, test } from 'vitest'
import {
  daysSince,
  endOfLocalDay,
  formatBytes,
  formatDate,
  formatDateTime,
  formatDay,
  formatTimeAgo,
  fromLocalDateTime,
  localDay,
  splitTags,
  toLocalDateTime,
} from './format'

// The suite runs in America/New_York (vite.config.ts): UTC-4 until summer time
// ends on 1 Nov 2026, UTC-5 after. Early morning UTC is still the day before
// there, and UTC midnight is the evening before — the mistakes these helpers
// exist to avoid.

describe('formatDate / formatDateTime', () => {
  test('show the local day, not the UTC one', () => {
    expect(formatDate('2026-09-27T02:30:00Z')).toBe('Sep 26, 2026')
  })

  test('include the local time', () => {
    expect(formatDateTime('2026-09-26T18:30:00Z')).toMatch(/^Sep 26, 2026,? (at )?2:30\sPM$/)
  })
})

describe('formatDay', () => {
  test('reads a bare date as that day, not the UTC midnight before it', () => {
    expect(formatDay('2026-09-26')).toBe('Sep 26, 2026')
  })

  test('ignores a time part', () => {
    expect(formatDay('2026-09-26T00:00:00Z')).toBe('Sep 26, 2026')
  })
})

describe('formatTimeAgo', () => {
  const now = new Date('2026-10-01T12:00:00Z')
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString()

  test.each([
    [30, 'now'],
    [5 * 60, '5 minutes ago'],
    [3 * 3_600, '3 hours ago'],
    [86_400, 'yesterday'],
    [8 * 86_400, 'last week'],
    [400 * 86_400, 'last year'],
  ])('%i seconds ago reads "%s"', (seconds, expected) => {
    expect(formatTimeAgo(ago(seconds), now)).toBe(expected)
  })

  test('truncates rather than rounds up', () => {
    expect(formatTimeAgo(ago(23 * 3_600 + 59 * 60), now)).toBe('23 hours ago')
  })

  test('handles the future', () => {
    expect(formatTimeAgo(ago(-2 * 86_400), now)).toBe('in 2 days')
  })
})

describe('formatBytes', () => {
  test.each([
    [0, '0 B'],
    [1023, '1023 B'],
    [1024, '1 KB'],
    [250 * 1024, '250 KB'],
    [1.5 * 1024 * 1024, '1.5 MB'],
  ])('%i bytes', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected)
  })
})

describe('daysSince', () => {
  const now = new Date(2026, 9, 1, 8, 0)

  test('counts calendar days, not 24-hour spans', () => {
    expect(daysSince(new Date(2026, 8, 30, 23, 50).toISOString(), now)).toBe(1)
  })

  test('is 0 earlier the same day', () => {
    expect(daysSince(new Date(2026, 9, 1, 0, 5).toISOString(), now)).toBe(0)
  })

  test('is never negative', () => {
    expect(daysSince(new Date(2026, 9, 3).toISOString(), now)).toBe(0)
  })

  test('is not thrown off by the 25-hour day when summer time ends', () => {
    expect(daysSince(new Date(2026, 9, 31, 12).toISOString(), new Date(2026, 10, 2, 12))).toBe(2)
  })
})

describe('splitTags', () => {
  test('trims and drops blanks', () => {
    expect(splitTags(' cloud, ,devops ,, k8s ')).toEqual(['cloud', 'devops', 'k8s'])
  })

  test('is empty for an empty field', () => {
    expect(splitTags('')).toEqual([])
  })
})

describe('local days and deadlines', () => {
  test('localDay is the day here, not in UTC', () => {
    expect(localDay('2026-09-27T02:30:00Z')).toBe('2026-09-26')
  })

  test('endOfLocalDay is 23:59 local, in UTC', () => {
    expect(endOfLocalDay('2026-09-26')).toBe('2026-09-27T03:59:00.000Z')
    expect(endOfLocalDay('2026-12-01')).toBe('2026-12-02T04:59:00.000Z')
  })

  test('a deadline stays on its day', () => {
    expect(localDay(endOfLocalDay('2026-09-26'))).toBe('2026-09-26')
  })

  test('toLocalDateTime and fromLocalDateTime round-trip', () => {
    expect(toLocalDateTime('2026-09-27T03:59:00.000Z')).toBe('2026-09-26T23:59')
    expect(fromLocalDateTime('2026-09-26T23:59')).toBe('2026-09-27T03:59:00.000Z')
  })
})
