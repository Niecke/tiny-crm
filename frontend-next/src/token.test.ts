import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { fakeJwt } from './test/jwt'
import { clearTokens, expiresSoon, getRefreshToken, getToken, setTokens } from './token'

describe('token storage', () => {
  afterEach(() => vi.restoreAllMocks())

  test('stores, reads and clears both tokens', () => {
    expect(getToken()).toBeNull()
    setTokens({ access_token: 'access', refresh_token: 'refresh' })
    expect(getToken()).toBe('access')
    expect(getRefreshToken()).toBe('refresh')
    clearTokens()
    expect(getToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  test('blocked storage reads as signed out and does not throw', () => {
    for (const method of ['getItem', 'setItem', 'removeItem'] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new DOMException('blocked', 'SecurityError')
      })
    }
    expect(() => setTokens({ access_token: 'access', refresh_token: 'refresh' })).not.toThrow()
    expect(getToken()).toBeNull()
    expect(() => clearTokens()).not.toThrow()
  })
})

describe('expiresSoon', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-01T12:00:00Z'))
  })
  afterEach(() => vi.useRealTimers())

  test('a fresh token is fine', () => {
    expect(expiresSoon(fakeJwt(15 * 60))).toBe(false)
  })

  test('renews within the last 30 seconds', () => {
    expect(expiresSoon(fakeJwt(31))).toBe(false)
    expect(expiresSoon(fakeJwt(30))).toBe(true)
  })

  test('an expired token expires soon', () => {
    expect(expiresSoon(fakeJwt(-60))).toBe(true)
  })

  test('reads base64url payloads', () => {
    // Claims chosen so the encoded payload contains "-" and "_", which plain
    // atob rejects.
    const token = fakeJwt(15 * 60, { n: '>>>???~~~' })
    expect(token.split('.')[1]).toMatch(/[-_]/)
    expect(expiresSoon(token)).toBe(false)
  })

  test.each([
    ['not a JWT', 'garbage'],
    ['a payload that is not JSON', 'eyJhbGciOiJIUzI1NiJ9.bm90IGpzb24.sig'],
    ['no exp', `x.${btoa(JSON.stringify({ sub: 'user' }))}.sig`],
    ['a non-numeric exp', `x.${btoa(JSON.stringify({ exp: 'tomorrow' }))}.sig`],
  ])('%s counts as expiring', (_, token) => {
    expect(expiresSoon(token)).toBe(true)
  })
})
