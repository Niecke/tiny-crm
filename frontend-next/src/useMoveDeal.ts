import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { Api } from './api/client'
import type { DealRead } from './api/types'
import { invalidateDeals, moveDeal, type Stage } from './deals'

// Moving a deal between stages, from the board, the list or its page. A move
// to Lost first asks why (optional — an unexplained loss still beats a deal
// left sitting in negotiation), everything else goes straight through. Board
// caches are updated at once, so a dropped card does not jump back while the
// request is on its way.
export function useMoveDeal(api: Api) {
  const queryClient = useQueryClient()
  const [askingWhy, setAskingWhy] = useState<DealRead | null>(null)

  const mutation = useMutation({
    mutationFn: ({ deal, stage, reason }: { deal: DealRead; stage: Stage; reason?: string }) =>
      moveDeal(api, deal.id, stage, reason),
    onMutate: async ({ deal, stage }) => {
      await queryClient.cancelQueries({ queryKey: ['deals', 'board'] })
      queryClient.setQueriesData<{ items: DealRead[]; total: number }>({ queryKey: ['deals', 'board'] }, (page) =>
        page && { ...page, items: page.items.map((d) => (d.id === deal.id ? { ...d, stage } : d)) },
      )
    },
    onSettled: () => invalidateDeals(queryClient),
  })

  return {
    move: (deal: DealRead, stage: Stage) => {
      if (deal.stage === stage) return
      if (stage === 'lost') setAskingWhy(deal)
      else mutation.mutate({ deal, stage })
    },
    askingWhy,
    confirmLost: (reason: string) => {
      if (askingWhy) mutation.mutate({ deal: askingWhy, stage: 'lost', reason })
      setAskingWhy(null)
    },
    cancelLost: () => setAskingWhy(null),
    error: mutation.error,
    pendingId: mutation.isPending ? mutation.variables?.deal.id : undefined,
  }
}
