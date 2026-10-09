import { HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { ApiError } from './api/client'
import { isMfaChallenge, login, verifyMfa } from './auth'
import { http, server, testApi } from './test/server'

const tokens = { access_token: 'a1', refresh_token: 'r1', token_type: 'bearer' as const, expires_in: 900 }
const challenge = { mfa_required: true as const, mfa_token: 'm1', expires_in: 300 }

describe('login', () => {
  test('hands back the tokens of an account without MFA', async () => {
    server.use(http.post('/auth/jwt/login', ({ response }) => response(200).json(tokens)))

    const result = await login(testApi(), 'me@example.com', 'pw')

    expect(isMfaChallenge(result)).toBe(false)
    expect(result).toEqual(tokens)
  })

  test('hands back the challenge of an account with MFA on', async () => {
    server.use(http.post('/auth/jwt/login', ({ response }) => response(200).json(challenge)))

    const result = await login(testApi(), 'me@example.com', 'pw')

    expect(isMfaChallenge(result)).toBe(true)
  })
})

describe('verifyMfa', () => {
  test('trades the challenge and a code for tokens', async () => {
    let sent: unknown
    server.use(
      http.post('/auth/jwt/mfa', async ({ request, response }) => {
        sent = await request.json()
        return response(200).json(tokens)
      }),
    )

    await expect(verifyMfa(testApi(), 'm1', '123456')).resolves.toEqual(tokens)
    expect(sent).toEqual({ mfa_token: 'm1', code: '123456' })
  })

  test('a wrong code is a 400 with its reason', async () => {
    server.use(
      http.post('/auth/jwt/mfa', ({ response }) =>
        response.untyped(HttpResponse.json({ detail: 'MFA_CODE_INVALID' }, { status: 400 })),
      ),
    )

    const error = await verifyMfa(testApi(), 'm1', '000000').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(400)
    expect((error as ApiError).detail).toBe('MFA_CODE_INVALID')
  })
})
