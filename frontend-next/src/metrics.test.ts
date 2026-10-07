import { describe, expect, test } from 'vitest'
import type { StageMoney } from './api/types'
import { byCurrency, conversionRate, formatMedian, largest, moneyPair, share, totalsByCurrency } from './metrics'

const row = (stage: StageMoney['stage'], currency: string, value: string, count = 1, open_ended = 0): StageMoney => ({
  stage,
  currency,
  value,
  count,
  open_ended,
})

describe('moneyPair', () => {
  test('says the open-ended deals beside the amount', () => {
    expect(moneyPair({ value: '48000.50', currency: 'EUR', open_ended: 2 })).toEqual({
      amount: '48,000.50 EUR',
      openEnded: '2 open-ended',
    })
  })

  test('says nothing extra when every deal has an amount', () => {
    expect(moneyPair({ value: '0.00', currency: 'USD', open_ended: 0 }).openEnded).toBeNull()
  })
})

describe('byCurrency', () => {
  test('keeps currencies apart and adds only counts', () => {
    const blocks = byCurrency([
      row('lead', 'EUR', '0.00', 1, 1),
      row('proposal', 'EUR', '48000.00', 3, 1),
      row('proposal', 'USD', '12000.00'),
    ])
    expect(blocks.map((b) => [b.currency, b.count, b.openEnded, b.rows.length])).toEqual([
      ['EUR', 4, 2, 2],
      ['USD', 1, 0, 1],
    ])
  })
})

describe('share and largest', () => {
  test('measure against the largest amount in the block, exactly', () => {
    const rows = [row('lead', 'EUR', '9400.00'), row('proposal', 'EUR', '48000.00'), row('negotiation', 'EUR', '0.10')]
    expect(largest(rows)).toBe('48000.00')
    expect(share('24000.00', '48000.00')).toBe(0.5)
    expect(share('0.1', '0.20')).toBe(0.5)
  })

  test('is zero against an empty block rather than NaN', () => {
    expect(share('0.00', '0.00')).toBe(0)
    expect(largest([])).toBe('0.00')
  })
})

describe('conversionRate', () => {
  test('rounds to a whole percent', () => {
    expect(conversionRate(3, 2)).toBe(67)
  })

  test('is no rate, not 0%, when nothing entered', () => {
    expect(conversionRate(0, 0)).toBeNull()
  })
})

describe('formatMedian', () => {
  test('shows whole days plainly and halves with one decimal', () => {
    expect(formatMedian(10)).toBe('10 d')
    expect(formatMedian(6.5)).toBe('6.5 d')
    expect(formatMedian(null)).toBe('–')
  })
})

describe('totalsByCurrency', () => {
  test('adds exactly, per currency, and keeps the open-ended count', () => {
    const totals = totalsByCurrency([
      row('lead', 'EUR', '0.10', 2, 1),
      row('proposal', 'EUR', '0.20', 1, 0),
      row('proposal', 'USD', '12000.00', 1, 0),
      row('negotiation', 'EUR', '999999999999.99', 1, 0),
    ])
    expect(totals).toEqual([
      { currency: 'EUR', value: '1000000000000.29', count: 4, open_ended: 1 },
      { currency: 'USD', value: '12000.00', count: 1, open_ended: 0 },
    ])
  })

  test('is empty for an empty pipeline', () => {
    expect(totalsByCurrency([])).toEqual([])
  })
})
