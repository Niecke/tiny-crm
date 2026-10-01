import { describe, expect, test } from 'vitest'
import { freelancerAnswer, labelOf, sourceOptions } from './contacts'

describe('labelOf', () => {
  test('labels a known value, passes an unknown one through, blanks a missing one', () => {
    expect(labelOf(sourceOptions, 'job_board')).toBe('Job board')
    expect(labelOf(sourceOptions, 'carrier_pigeon')).toBe('carrier_pigeon')
    expect(labelOf(sourceOptions, null)).toBe('')
  })
})

describe('freelancerAnswer', () => {
  test('three answers, and "never asked" stands out', () => {
    expect(freelancerAnswer(true)).toEqual({ label: 'Works with freelancers', tone: 'success' })
    expect(freelancerAnswer(false)).toEqual({ label: 'Does not use freelancers' })
    expect(freelancerAnswer(null)).toEqual({ label: 'Never asked about freelancers', tone: 'accent' })
    expect(freelancerAnswer(undefined)).toEqual(freelancerAnswer(null))
  })
})
