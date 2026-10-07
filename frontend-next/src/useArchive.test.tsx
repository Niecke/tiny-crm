import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse } from 'msw'
import { describe, expect, test, vi } from 'vitest'
import { ArchiveButton, ArchivedNotice } from './components/Archive'
import { archiveDeal, dealQuery, deleteDeal, restoreDeal } from './deals'
import { deal } from './test/fixtures'
import { withQueryClient } from './test/query'
import { http, server, testApi } from './test/server'
import { useArchive } from './useArchive'

const ARCHIVED_AT = '2026-10-07T09:00:00Z'

// The three endpoints behind the controls. `calls` is the order they were hit
// in, so a test can say that nothing was deleted.
function endpoints({ refuseDelete = false } = {}) {
  const calls: string[] = []
  server.use(
    http.post('/deals/{deal_id}/archive', ({ params, response }) => {
      calls.push('archive')
      return response(200).json(deal({ id: params.deal_id, archived_at: ARCHIVED_AT }))
    }),
    http.post('/deals/{deal_id}/restore', ({ params, response }) => {
      calls.push('restore')
      return response(200).json(deal({ id: params.deal_id, archived_at: null }))
    }),
    http.delete('/deals/{deal_id}', ({ response }) => {
      calls.push('delete')
      if (refuseDelete)
        return response.untyped(HttpResponse.json({ detail: 'Deal is not archived' }, { status: 409 }))
      return response(204).empty()
    }),
  )
  return calls
}

function setup(archived_at: string | null = null) {
  const { queryClient, wrapper } = withQueryClient()
  const api = testApi()
  const queryKey = dealQuery(api, 'deal-1').queryKey
  queryClient.setQueryData(queryKey, deal({ archived_at }))
  const leave = vi.fn(async () => {})
  const { result } = renderHook(
    () =>
      useArchive({
        queryKey,
        archive: () => archiveDeal(api, 'deal-1'),
        restore: () => restoreDeal(api, 'deal-1'),
        remove: () => deleteDeal(api, 'deal-1'),
        leave,
        alsoRemove: [['deals', 'extra', 'deal-1']],
      }),
    { wrapper },
  )
  const cached = () => queryClient.getQueryData(queryKey)
  return { queryClient, wrapper, result, leave, cached }
}

describe('useArchive', () => {
  test('archiving puts the saved record in the cache and refetches everything', async () => {
    const calls = endpoints()
    const { queryClient, result, leave, cached } = setup()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    act(() => result.current.archive.mutate())

    await waitFor(() => expect(result.current.archive.isSuccess).toBe(true))
    expect(calls).toEqual(['archive'])
    expect(cached()).toMatchObject({ id: 'deal-1', archived_at: ARCHIVED_AT })
    // No key: an archived record also leaves the search, the briefing, the
    // dashboard and the tabs of everything it is linked to.
    expect(invalidate).toHaveBeenCalledWith()
    // The page stays where it is, so Restore is one click away.
    expect(leave).not.toHaveBeenCalled()
  })

  test('restoring brings the record back in the cache', async () => {
    const calls = endpoints()
    const { result, cached } = setup(ARCHIVED_AT)

    act(() => result.current.restore.mutate())

    await waitFor(() => expect(result.current.restore.isSuccess).toBe(true))
    expect(calls).toEqual(['restore'])
    expect(cached()).toMatchObject({ archived_at: null })
  })

  test('deleting leaves the page before it drops the record', async () => {
    const calls = endpoints()
    const { queryClient, result, leave, cached } = setup(ARCHIVED_AT)
    queryClient.setQueryData(['deals', 'extra', 'deal-1'], 'kept until the delete')
    // Still cached while leaving: dropping it first would make the page it is
    // on refetch a record that no longer exists.
    leave.mockImplementation(async () => expect(cached()).toBeDefined())

    act(() => result.current.remove.mutate())

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true))
    expect(calls).toEqual(['delete'])
    expect(leave).toHaveBeenCalledOnce()
    expect(cached()).toBeUndefined()
    expect(queryClient.getQueryData(['deals', 'extra', 'deal-1'])).toBeUndefined()
  })

  test('a refused delete stays on the page and keeps the record', async () => {
    endpoints({ refuseDelete: true })
    const { result, leave, cached } = setup()

    act(() => result.current.remove.mutate())

    await waitFor(() => expect(result.current.remove.error).toMatchObject({ status: 409 }))
    expect(leave).not.toHaveBeenCalled()
    expect(cached()).toBeDefined()
  })
})

describe('the archive controls', () => {
  function Page({ archived_at }: { archived_at: string | null }) {
    const api = testApi()
    const record = deal({ archived_at })
    const archiving = useArchive({
      queryKey: dealQuery(api, record.id).queryKey,
      archive: () => archiveDeal(api, record.id),
      restore: () => restoreDeal(api, record.id),
      remove: () => deleteDeal(api, record.id),
      leave: async () => {},
    })
    return (
      <>
        <ArchivedNotice record={record} noun="deal" name={record.title} archiving={archiving}>
          Its tasks are kept.
        </ArchivedNotice>
        {!record.archived_at && <ArchiveButton archiving={archiving} />}
      </>
    )
  }

  test('a record in use offers Archive, and nothing that deletes', async () => {
    const calls = endpoints()
    const { wrapper } = withQueryClient()
    render(<Page archived_at={null} />, { wrapper })

    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Archive' }))

    // One click, no confirmation: it can be undone.
    await waitFor(() => expect(calls).toEqual(['archive']))
  })

  test('an archived record says so, and deleting it asks first', async () => {
    const calls = endpoints()
    const { wrapper } = withQueryClient()
    render(<Page archived_at={ARCHIVED_AT} />, { wrapper })

    expect(screen.getByRole('status')).toHaveTextContent(/Archived .*2026.*cannot be changed until it is restored/)
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))

    // Nothing is deleted by the first click; the dialog names what goes.
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Platform migration will be deleted for good.')
    expect(dialog).toHaveTextContent('Its tasks are kept.')
    expect(calls).toEqual([])

    await userEvent.click(screen.getAllByRole('button', { name: 'Delete permanently' }).at(-1)!)

    await waitFor(() => expect(calls).toEqual(['delete']))
  })
})
