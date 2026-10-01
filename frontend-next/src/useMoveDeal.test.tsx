import { act, renderHook, waitFor } from '@testing-library/react'
import { HttpResponse } from 'msw'
import { describe, expect, test, vi } from 'vitest'
import type { DealRead } from './api/types'
import { deal } from './test/fixtures'
import { withQueryClient } from './test/query'
import { http, server, testApi } from './test/server'
import { useMoveDeal } from './useMoveDeal'

type Page = { items: DealRead[]; total: number }

const BOARD_KEY = ['deals', 'board', { q: undefined, scope: 'plate' }]

// The stage endpoint, held until `release()` so a test can look at the cache
// while the request is still on its way. Records each request body.
function stageEndpoint({ fail = false } = {}) {
  const bodies: unknown[] = []
  let release!: () => void
  const gate = new Promise<void>((resolve) => (release = resolve))
  const handler = http.post('/deals/{deal_id}/stage', async ({ request, params, response }) => {
    const body = await request.json()
    bodies.push(body)
    await gate
    if (fail) return response.untyped(HttpResponse.json({ detail: 'Deal is archived' }, { status: 409 }))
    return response(200).json(deal({ id: params.deal_id, stage: body.stage, lost_reason: body.lost_reason ?? null }))
  })
  return { handler, bodies, release }
}

function setup(stage: DealRead['stage'] = 'proposal') {
  const { queryClient, wrapper } = withQueryClient()
  const d = deal({ stage })
  queryClient.setQueryData<Page>(BOARD_KEY, { items: [d, deal({ id: 'deal-2', stage: 'lead' })], total: 2 })
  const { result } = renderHook(() => useMoveDeal(testApi()), { wrapper })
  const board = () => queryClient.getQueryData<Page>(BOARD_KEY)?.items.map((x) => [x.id, x.stage])
  return { d, queryClient, result, board }
}

describe('useMoveDeal', () => {
  test('moves the card at once, then saves and refreshes what shows deals', async () => {
    const endpoint = stageEndpoint()
    server.use(endpoint.handler)
    const { d, queryClient, result, board } = setup()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    act(() => result.current.move(d, 'won'))

    await waitFor(() => expect(result.current.pendingId).toBe(d.id))
    expect(board()).toEqual([
      ['deal-1', 'won'],
      ['deal-2', 'lead'],
    ])
    expect(invalidate).not.toHaveBeenCalled()

    endpoint.release()
    await waitFor(() => expect(result.current.pendingId).toBeUndefined())
    expect(endpoint.bodies).toEqual([{ stage: 'won', lost_reason: null }])
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(
      expect.arrayContaining([['deals'], ['briefing'], ['tasks']]),
    )
  })

  test('a move to the same stage does nothing', () => {
    const { d, queryClient, result, board } = setup('proposal')

    act(() => result.current.move(d, 'proposal'))

    // A mutation lands in the cache the moment it starts.
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0)
    expect(board()?.[0]).toEqual(['deal-1', 'proposal'])
  })

  test('a move to Lost asks why first, and sends the reason', async () => {
    const endpoint = stageEndpoint()
    endpoint.release()
    server.use(endpoint.handler)
    const { d, result } = setup()

    act(() => result.current.move(d, 'lost'))
    expect(result.current.askingWhy).toEqual(d)
    expect(endpoint.bodies).toEqual([])

    act(() => result.current.confirmLost('Went with a bigger agency'))
    expect(result.current.askingWhy).toBeNull()

    await waitFor(() => expect(endpoint.bodies).toEqual([{ stage: 'lost', lost_reason: 'Went with a bigger agency' }]))
  })

  test('an unexplained loss is still a loss', async () => {
    const endpoint = stageEndpoint()
    endpoint.release()
    server.use(endpoint.handler)
    const { d, result } = setup()

    act(() => result.current.move(d, 'lost'))
    act(() => result.current.confirmLost(''))

    await waitFor(() => expect(endpoint.bodies).toEqual([{ stage: 'lost', lost_reason: null }]))
  })

  test('cancelling the question leaves the deal where it was', () => {
    const { d, queryClient, result, board } = setup()

    act(() => result.current.move(d, 'lost'))
    act(() => result.current.cancelLost())

    expect(result.current.askingWhy).toBeNull()
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0)
    expect(board()?.[0]).toEqual(['deal-1', 'proposal'])
  })

  test('a failed move reports the error and refreshes the board', async () => {
    const endpoint = stageEndpoint({ fail: true })
    endpoint.release()
    server.use(endpoint.handler)
    const { d, queryClient, result } = setup()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    act(() => result.current.move(d, 'won'))

    await waitFor(() => expect(result.current.error).toMatchObject({ status: 409, message: 'Deal is archived' }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['deals'] })
  })
})
