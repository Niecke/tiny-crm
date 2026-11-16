import { type QueryClient, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { type Api, ApiError } from './api/client'
import type { ProposalRead } from './api/types'
import { type Approval, approveProposal, entityKeys, rejectProposal } from './proposals'

type Decision = { proposal: ProposalRead; approval?: Approval; reject?: { reason: string } }

type Page = { items: ProposalRead[]; total: number }

// Approve and reject, from the Approvals inbox. The card leaves the list at
// once, so a click feels instant; if the request fails it comes back, with the
// reason, instead of the decision silently not having happened. The mutation
// lives here, in the page, and not in the card: the card is gone by the time
// the answer arrives, and a callback tied to it would never run.
export function useProposalDecision(api: Api) {
  const queryClient = useQueryClient()
  const [errors, setErrors] = useState<Record<string, string>>({})

  const mutation = useMutation({
    mutationFn: ({ proposal, approval, reject }: Decision) =>
      reject ? rejectProposal(api, proposal.id, reject.reason) : approveProposal(api, proposal.id, approval),
    onMutate: async ({ proposal }) => {
      await queryClient.cancelQueries({ queryKey: ['proposals'] })
      setErrors((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== proposal.id)))
      const lists = queryClient.getQueriesData<Page>({ queryKey: ['proposals', 'list'] })
      const count = queryClient.getQueryData<{ pending: number }>(['proposals', 'count'])
      queryClient.setQueriesData<Page>({ queryKey: ['proposals', 'list', 'pending'] }, (page) =>
        page && { ...page, items: page.items.filter((p) => p.id !== proposal.id), total: page.total - 1 },
      )
      queryClient.setQueryData(['proposals', 'count'], count && { pending: Math.max(0, count.pending - 1) })
      return { lists, count }
    },
    onError: (error, { proposal }, context) => {
      for (const [key, data] of context?.lists ?? []) queryClient.setQueryData(key, data)
      queryClient.setQueryData(['proposals', 'count'], context?.count)
      const message = error instanceof ApiError ? error.message : 'The request failed.'
      setErrors((current) => ({ ...current, [proposal.id]: message }))
    },
    onSettled: (_data, _error, { proposal }) => invalidateAfterDecision(queryClient, proposal),
  })

  return {
    approve: (proposal: ProposalRead, approval?: Approval) => mutation.mutate({ proposal, approval }),
    reject: (proposal: ProposalRead, reason: string) => mutation.mutate({ proposal, reject: { reason } }),
    errors,
  }
}

// The inbox and the badge, and whatever the change touched.
async function invalidateAfterDecision(queryClient: QueryClient, proposal: ProposalRead) {
  const keys = [['proposals'], [entityKeys[proposal.entity_type]], ['briefing'], ['count']]
  await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
}
