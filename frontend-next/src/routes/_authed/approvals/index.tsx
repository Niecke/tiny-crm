import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useState } from 'react'
import { z } from 'zod'
import type { ProposalStatus } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { ProposalCard } from '../../../components/ProposalCard'
import { PROPOSALS_LIMIT, proposalsQuery } from '../../../proposals'
import { useProposalDecision } from '../../../useProposalDecision'

const searchSchema = z.object({
  status: z.enum(['pending', 'approved', 'rejected']).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/approvals/')({
  validateSearch: searchSchema,
  component: Approvals,
})

const statuses: { value: ProposalStatus; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

// What agents propose (backend/app/routers/proposals.py): nothing reaches the
// CRM until it is approved here.
function Approvals() {
  const { api } = Route.useRouteContext()
  const { status = 'pending' } = Route.useSearch()
  // How many to fetch per tab; "Show more" raises it, so decisions beyond the
  // first page stay reachable.
  const [limits, setLimits] = useState<Partial<Record<ProposalStatus, number>>>({})
  const limit = limits[status] ?? PROPOSALS_LIMIT
  const { data, error, isPending } = useQuery(proposalsQuery(api, status, limit))
  const { approve, reject, errors } = useProposalDecision(api)

  return (
    <div className="page">
      <header className="page-header">
        <h1>Approvals</h1>
        <p>Changes proposed by agents. Nothing is saved until you approve it.</p>
      </header>

      <nav className="tabs tabs-plain" aria-label="Status">
        {statuses.map((s) => (
          <Link
            key={s.value}
            to="/approvals"
            search={{ status: s.value === 'pending' ? undefined : s.value }}
            replace
            activeOptions={{ explicitUndefined: true }}
            className="tab"
          >
            {s.label}
          </Link>
        ))}
      </nav>

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 ? (
        <p className="today-clear">{status === 'pending' ? 'Nothing waiting for approval.' : `Nothing ${status} yet.`}</p>
      ) : (
        <>
          <ul className="proposal-list">
            {data.items.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                labels={data.labels}
                error={errors[proposal.id]}
                onApprove={approve}
                onReject={reject}
              />
            ))}
          </ul>
          {data.total > data.items.length && (
            <p className="muted small">
              Showing {data.items.length} of {data.total}.{' '}
              <Button variant="quiet" onPress={() => setLimits((l) => ({ ...l, [status]: limit + PROPOSALS_LIMIT }))}>
                Show more
              </Button>
            </p>
          )}
        </>
      )}
    </div>
  )
}
