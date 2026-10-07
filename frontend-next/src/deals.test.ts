import { describe, expect, test } from 'vitest'
import { dealValue, formatMoney, isDecided, scopeOf, stageLabel, stageOptions, stageTone, valueSummary } from './deals'
import { deal } from './test/fixtures'

describe('stages', () => {
  test('labels known stages and passes unknown ones through', () => {
    expect(stageLabel('negotiation')).toBe('Negotiation')
    expect(stageLabel('mystery')).toBe('mystery')
  })

  test('won, running, completed and lost are decided', () => {
    expect(['won', 'running', 'completed', 'lost'].every(isDecided)).toBe(true)
    expect(['draft', 'lead', 'qualified', 'proposal', 'negotiation'].some(isDecided)).toBe(false)
  })

  test('draft is the first stage of the pipeline', () => {
    expect(stageOptions[0]).toEqual({ value: 'draft', label: 'Draft' })
  })

  test('tones', () => {
    expect(stageTone('lost')).toBe('danger')
    expect(stageTone('running')).toBe('success')
    expect(stageTone('proposal')).toBe('accent')
    expect(stageTone('draft')).toBeUndefined()
  })
})

describe('scopeOf', () => {
  test('defaults to "On my plate"', () => {
    expect(scopeOf(undefined).value).toBe('plate')
    expect(scopeOf('nonsense').value).toBe('plate')
  })

  test('"On my plate" starts at draft and keeps won and running work on the board', () => {
    expect(scopeOf('plate').columns).toEqual(['draft', 'lead', 'qualified', 'proposal', 'negotiation', 'won', 'running'])
  })

  test('the attention scopes are deals in play with a flag, so no draft column', () => {
    const inPlay = ['lead', 'qualified', 'proposal', 'negotiation']
    expect(scopeOf('stalled')).toMatchObject({ stalled: true, columns: inPlay })
    expect(scopeOf('overdue')).toMatchObject({ overdue: true, columns: inPlay })
  })

  test('a draft has a stage scope of its own', () => {
    expect(scopeOf('stage-draft')).toMatchObject({ stage: 'draft', columns: ['draft'] })
  })

  test('a single stage scope asks for that stage only', () => {
    expect(scopeOf('stage-lost')).toMatchObject({ stage: 'lost', columns: ['lost'] })
  })
})

describe('formatMoney', () => {
  test.each([
    ['1234567.5', '1,234,567.50 EUR'],
    ['999', '999.00 EUR'],
    ['-1000', '-1,000.00 EUR'],
    ['0.1', '0.10 EUR'],
    // Never through a float: the API's precision is kept as sent.
    ['12.345', '12.345 EUR'],
    ['  42.00 ', '42.00 EUR'],
  ])('%s', (amount, expected) => {
    expect(formatMoney(amount, 'EUR')).toBe(expected)
  })

  test('shows what it cannot parse as it came', () => {
    expect(formatMoney('n/a', 'EUR')).toBe('n/a EUR')
  })
})

describe('dealValue', () => {
  test('a fixed price is its total', () => {
    expect(dealValue(deal({ fixed_value: '15000', expected_value: '15000' }))).toEqual({
      headline: '15,000.00 EUR',
      detail: null,
    })
  })

  test('a rate-based deal shows the total and how it was derived', () => {
    const d = deal({
      value_type: 'rate_based',
      rate: '100',
      rate_unit: 'hour',
      estimated_volume: '120',
      volume_unit: 'hour',
      expected_value: '12000',
    })
    expect(dealValue(d)).toEqual({ headline: '12,000.00 EUR', detail: '100.00 EUR/hour × 120 hours' })
  })

  test('mismatched units show the rate and say why there is no total', () => {
    const d = deal({ value_type: 'rate_based', rate: '800', rate_unit: 'day', estimated_volume: '3', volume_unit: 'month' })
    expect(dealValue(d)).toEqual({
      headline: '800.00 EUR/day',
      detail: 'Estimated in months at a day rate — no total derived',
    })
  })

  test('an open-ended retainer shows its rate and says so', () => {
    const d = deal({ value_type: 'retainer', rate: '5000', rate_unit: 'month', is_open_ended: true })
    expect(dealValue(d)).toEqual({ headline: '5,000.00 EUR/month', detail: 'Open-ended — no total to forecast' })
    expect(valueSummary(d)).toBe('5,000.00 EUR/month · open-ended')
  })

  test('an unpriced deal has no value', () => {
    expect(dealValue(deal())).toEqual({ headline: null, detail: null })
    expect(valueSummary(deal({ is_open_ended: true }))).toBeNull()
  })
})
