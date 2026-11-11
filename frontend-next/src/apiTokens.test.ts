import { describe, expect, test } from 'vitest'
import { expiresAt, statusLabel, statusTone } from './apiTokens'

describe('expiresAt', () => {
  const now = new Date('2026-11-11T10:00:00.000Z')

  test('never sends nothing', () => {
    expect(expiresAt('', now)).toBeNull()
  })

  test('counts the days from now', () => {
    expect(expiresAt('30', now)).toBe('2026-12-11T10:00:00.000Z')
    expect(expiresAt('365', now)).toBe('2027-11-11T10:00:00.000Z')
  })
})

describe('status', () => {
  test('is worded for the list', () => {
    expect(statusLabel('active')).toBe('Active')
    expect(statusLabel('expired')).toBe('Expired')
    expect(statusLabel('revoked')).toBe('Revoked')
  })

  test('only an active token reads as good', () => {
    expect(statusTone('active')).toBe('success')
    expect(statusTone('expired')).toBe('warning')
    expect(statusTone('revoked')).toBe('danger')
  })
})
