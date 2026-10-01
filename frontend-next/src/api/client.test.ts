import { HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { deal } from '../test/fixtures'
import { fakeJwt } from '../test/jwt'
import { http, server, testApi } from '../test/server'
import { getRefreshToken, getToken, setTokens } from '../token'
import { ApiError, unwrap } from './client'

const user = { id: 'user-1', email: 'me@example.com', is_active: true, is_superuser: false, is_verified: true }

const pair = (access_token: string, refresh_token: string) => ({
  access_token,
  refresh_token,
  token_type: 'bearer' as const,
  expires_in: 900,
})

// GET /users/me as the backend answers it: 200 for the one token it accepts,
// 401 for anything else. Records the Authorization header of every call.
function me(accepted: string) {
  const seen: (string | null)[] = []
  const handler = http.get('/users/me', ({ request, response }) => {
    const auth = request.headers.get('Authorization')
    seen.push(auth)
    if (auth === `Bearer ${accepted}`) return response(200).json(user)
    return response.untyped(HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }))
  })
  return { handler, seen }
}

// POST /auth/jwt/refresh, answering with `answer` and counting the calls.
function refresh(answer: (refreshToken: string) => Response | Promise<Response>) {
  const calls: string[] = []
  const handler = http.post('/auth/jwt/refresh', async ({ request, response }) => {
    const { refresh_token } = await request.json()
    calls.push(refresh_token)
    return response.untyped(await answer(refresh_token))
  })
  return { handler, calls }
}

describe('auth middleware', () => {
  test('sends the stored token', async () => {
    const token = fakeJwt(900)
    setTokens({ access_token: token, refresh_token: 'r1' })
    const backend = me(token)
    server.use(backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).resolves.toEqual(user)
    expect(backend.seen).toEqual([`Bearer ${token}`])
  })

  test('sends no header when signed out', async () => {
    const backend = me('whatever')
    server.use(backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).rejects.toMatchObject({ status: 401 })
    expect(backend.seen).toEqual([null])
  })

  test('renews a token about to expire before the request leaves', async () => {
    const fresh = fakeJwt(900)
    setTokens({ access_token: fakeJwt(10), refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json(pair(fresh, 'r2')))
    const backend = me(fresh)
    server.use(renewal.handler, backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).resolves.toEqual(user)
    expect(renewal.calls).toEqual(['r1'])
    expect(backend.seen).toEqual([`Bearer ${fresh}`])
    expect(getToken()).toBe(fresh)
    expect(getRefreshToken()).toBe('r2')
  })

  test('requests that need a renewal at the same time share one', async () => {
    const fresh = fakeJwt(900)
    setTokens({ access_token: fakeJwt(10), refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json(pair(fresh, 'r2')))
    const backend = me(fresh)
    server.use(renewal.handler, backend.handler)

    const api = testApi()
    await Promise.all([1, 2, 3].map(() => unwrap(api.GET('/users/me'))))
    expect(renewal.calls).toHaveLength(1)
    expect(backend.seen).toEqual(Array(3).fill(`Bearer ${fresh}`))
  })

  test('a refused token is renewed and the request sent again, body and all', async () => {
    const rejected = fakeJwt(900, { v: 1 })
    const fresh = fakeJwt(900, { v: 2 })
    setTokens({ access_token: rejected, refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json(pair(fresh, 'r2')))
    const bodies: unknown[] = []
    server.use(
      renewal.handler,
      http.post('/deals/{deal_id}/stage', async ({ request, params, response }) => {
        bodies.push(await request.json())
        if (request.headers.get('Authorization') !== `Bearer ${fresh}`)
          return response.untyped(HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }))
        return response(200).json(deal({ id: params.deal_id, stage: 'won' }))
      }),
    )

    const moved = await unwrap(
      testApi().POST('/deals/{deal_id}/stage', { params: { path: { deal_id: 'deal-1' } }, body: { stage: 'won' } }),
    )
    expect(moved.stage).toBe('won')
    expect(renewal.calls).toEqual(['r1'])
    expect(bodies).toEqual([{ stage: 'won' }, { stage: 'won' }])
  })

  test('tries only once more: a second refusal ends the session', async () => {
    setTokens({ access_token: fakeJwt(900, { v: 1 }), refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json(pair(fakeJwt(900, { v: 2 }), 'r2')))
    const backend = me('nothing is accepted')
    server.use(renewal.handler, backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).rejects.toBeInstanceOf(ApiError)
    expect(backend.seen).toHaveLength(2)
    expect(getToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  test('a token another request renewed meanwhile is used without renewing again', async () => {
    const old = fakeJwt(900, { v: 1 })
    const newer = fakeJwt(900, { v: 2 })
    setTokens({ access_token: old, refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json(pair(fakeJwt(900, { v: 3 }), 'r3')))
    server.use(
      renewal.handler,
      http.get('/users/me', ({ request, response }) => {
        if (request.headers.get('Authorization') === `Bearer ${newer}`) return response(200).json(user)
        // While this one was on its way, another tab renewed the session.
        setTokens({ access_token: newer, refresh_token: 'r2' })
        return response.untyped(HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }))
      }),
    )

    await expect(unwrap(testApi().GET('/users/me'))).resolves.toEqual(user)
    expect(renewal.calls).toEqual([])
  })

  test('a refused renewal ends the session', async () => {
    setTokens({ access_token: fakeJwt(10), refresh_token: 'r1' })
    const renewal = refresh(() => HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }))
    const backend = me('nothing is accepted')
    server.use(renewal.handler, backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(backend.seen).toEqual([null])
  })

  test('a renewal refused after another tab rotated the pair keeps the newer pair', async () => {
    setTokens({ access_token: fakeJwt(10), refresh_token: 'r1' })
    const newer = fakeJwt(900)
    const renewal = refresh(() => {
      setTokens({ access_token: newer, refresh_token: 'r2' })
      return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })
    })
    server.use(renewal.handler, me(newer).handler)

    await expect(unwrap(testApi().GET('/users/me'))).resolves.toEqual(user)
    expect(getRefreshToken()).toBe('r2')
  })

  test.each([
    ['a server error', () => HttpResponse.json({ detail: 'Internal Server Error' }, { status: 503 })],
    ['being offline', () => HttpResponse.error()],
  ])('%s during a renewal keeps the tokens for the next try', async (_, answer) => {
    const expiring = fakeJwt(10)
    setTokens({ access_token: expiring, refresh_token: 'r1' })
    const backend = me(expiring)
    server.use(refresh(answer).handler, backend.handler)

    await expect(unwrap(testApi().GET('/users/me'))).resolves.toEqual(user)
    expect(backend.seen).toEqual([`Bearer ${expiring}`])
    expect(getToken()).toBe(expiring)
    expect(getRefreshToken()).toBe('r1')
  })
})

describe('unwrap', () => {
  test('a string detail becomes the message', async () => {
    server.use(
      http.get('/deals/{deal_id}', ({ response }) =>
        response.untyped(HttpResponse.json({ detail: 'Deal not found' }, { status: 404 })),
      ),
    )
    const error = await unwrap(testApi().GET('/deals/{deal_id}', { params: { path: { deal_id: 'gone' } } })).catch(
      (e: unknown) => e,
    )
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, detail: 'Deal not found', message: 'Deal not found' })
  })

  test('a validation error keeps its detail and names the path', async () => {
    const detail = [{ loc: ['body', 'stage'], msg: 'Input should be a valid stage', type: 'enum' }]
    server.use(http.post('/deals/{deal_id}/stage', ({ response }) => response(422).json({ detail })))
    const error = await unwrap(
      testApi().POST('/deals/{deal_id}/stage', { params: { path: { deal_id: 'deal-1' } }, body: { stage: 'won' } }),
    ).catch((e: unknown) => e)
    expect(error).toMatchObject({ status: 422, detail, message: '/deals/deal-1/stage → 422' })
  })

  test('a 204 resolves to undefined', async () => {
    server.use(http.delete('/deals/{deal_id}', ({ response }) => response(204).empty()))
    await expect(
      unwrap(testApi().DELETE('/deals/{deal_id}', { params: { path: { deal_id: 'deal-1' } } })),
    ).resolves.toBeUndefined()
  })
})
