import { useQuery } from '@tanstack/react-query'
import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse } from 'msw'
import { describe, expect, test, vi } from 'vitest'
import { ApiError } from './api/client'
import { StaleSaveNotice } from './components/StaleSaveNotice'
import { dealQuery, updateDeal } from './deals'
import { deal } from './test/fixtures'
import { withQueryClient } from './test/query'
import { http, server, testApi } from './test/server'
import { formError, isStaleSave, useEditVersion } from './useEditVersion'

const STALE = new ApiError(409, undefined, 'Deal was changed elsewhere since you opened it — reload to see the latest version')
const ARCHIVED = new ApiError(409, undefined, 'Deal is archived')

// The server's copy, which moves on whenever "someone else" saves.
function serverHolds(version: number) {
  server.use(http.get('/deals/{deal_id}', ({ response }) => response(200).json(deal({ version }))))
}

function setup() {
  const { queryClient, wrapper } = withQueryClient()
  const api = testApi()
  const queryKey = dealQuery(api, 'deal-1').queryKey
  queryClient.setQueryData(queryKey, deal({ version: 1 }))
  const { result } = renderHook(
    () => {
      const record = useQuery(dealQuery(api, 'deal-1'))
      return { record, editing: useEditVersion(record) }
    },
    { wrapper },
  )
  return { queryClient, queryKey, result }
}

describe('useEditVersion', () => {
  test('keeps the version the form was opened from when the record refetches', async () => {
    const { queryClient, queryKey, result } = setup()
    expect(result.current.editing.version).toBe(1)

    // Someone saves in another tab; this one refetches on focus.
    serverHolds(2)
    await act(() => queryClient.invalidateQueries({ queryKey }))

    await waitFor(() => expect(result.current.record.data?.version).toBe(2))
    // Sending 2 would overwrite their save with this form's older contents.
    expect(result.current.editing.version).toBe(1)
  })

  test('reloading takes the latest version and remounts the form', async () => {
    const { result } = setup()
    const before = result.current.editing.formKey
    serverHolds(3)

    await act(() => result.current.editing.reload())

    expect(result.current.editing.version).toBe(3)
    expect(result.current.editing.formKey).not.toBe(before)
  })
})

describe('updateDeal', () => {
  test('sends the version alongside the fields', async () => {
    const sent = vi.fn()
    server.use(
      http.patch('/deals/{deal_id}', async ({ request, response }) => {
        sent(await request.json())
        return response(200).json(deal({ version: 5 }))
      }),
    )

    await updateDeal(testApi(), 'deal-1', { title: 'Platform migration, phase 2' }, 4)

    expect(sent).toHaveBeenCalledWith({ title: 'Platform migration, phase 2', version: 4 })
  })

  test('a refused save comes back as a stale save', async () => {
    server.use(
      http.patch('/deals/{deal_id}', ({ response }) =>
        response.untyped(HttpResponse.json({ detail: STALE.message }, { status: 409 })),
      ),
    )

    const error = await updateDeal(testApi(), 'deal-1', { title: 'x' }, 1).catch((e: unknown) => e)

    expect(isStaleSave(error)).toBe(true)
  })
})

describe('isStaleSave', () => {
  test('only the outdated-copy 409, not every 409', () => {
    expect(isStaleSave(STALE)).toBe(true)
    // Reloading does not help with an archived record.
    expect(isStaleSave(ARCHIVED)).toBe(false)
    expect(isStaleSave(null)).toBe(false)
  })

  test('the form shows every other error itself', () => {
    expect(formError(STALE)).toBeNull()
    expect(formError(ARCHIVED)).toBe(ARCHIVED)
  })
})

describe('StaleSaveNotice', () => {
  test('says nothing unless the save was stale', () => {
    const { container } = render(<StaleSaveNotice error={ARCHIVED} onReload={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  test('offers to load the latest version', async () => {
    const onReload = vi.fn()
    render(<StaleSaveNotice error={STALE} onReload={onReload} />)

    expect(screen.getByRole('alert')).toHaveTextContent('changed elsewhere since you opened it')
    await userEvent.click(screen.getByRole('button', { name: 'Load latest version' }))

    expect(onReload).toHaveBeenCalledOnce()
  })
})
