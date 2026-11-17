import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useRouteContext } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'
import type { ContactRead, DealRead, InteractionRead, OrganizationRead, ProposalRead, TaskRead } from '../api/types'
import { formatDateTime } from '../format'
import { type Approval, actionTitle, diffRows, targetRecord } from '../proposals'
import { ContactForm } from './ContactForm'
import { DealForm } from './DealForm'
import { InteractionForm } from './InteractionForm'
import { OrganizationForm } from './OrganizationForm'
import { TaskForm } from './TaskForm'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { TextField } from './ui/TextField'

type Labels = Record<string, string>

// One proposal, as a card: what the agent wants, why, and how to decide.
// A create shows the record it would make; an update shows Current beside
// Proposed, with the rows that really change picked out; an archive says which
// record it would put away.
export function ProposalCard({
  proposal,
  labels,
  error,
  onApprove,
  onReject,
}: {
  proposal: ProposalRead
  labels: Labels
  error?: string
  onApprove: (proposal: ProposalRead, approval?: Approval) => void
  onReject: (proposal: ProposalRead, reason: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const pending = proposal.status === 'pending'
  const version = proposal.current?.version
  const approvedAs = typeof version === 'number' ? { version } : undefined

  return (
    <li className="proposal-card panel" data-status={proposal.status}>
      <div className="panel-body">
        <header className="proposal-head">
          <h2 className="proposal-title">
            {actionTitle(proposal)}
            {proposal.target_label && (
              <>
                {' · '}
                <em>{proposal.target_label}</em>
              </>
            )}
          </h2>
          <span className="muted small">{formatDateTime(proposal.created_at)}</span>
        </header>

        <blockquote className="proposal-reason">{proposal.reason}</blockquote>
        <p className="muted small">
          via <strong>{proposal.token_name ?? 'a deleted token'}</strong>
        </p>

        <ProposalBody proposal={proposal} labels={labels} />

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        {pending ? (
          <div className="form-actions proposal-actions">
            <Button onPress={() => onApprove(proposal, approvedAs)}>Approve</Button>
            {proposal.action !== 'archive' && (
              <Button variant="quiet" onPress={() => setEditing(true)}>
                Edit
              </Button>
            )}
            <Button variant="quiet" onPress={() => setRejecting(true)}>
              Reject
            </Button>
          </div>
        ) : (
          <Outcome proposal={proposal} />
        )}
      </div>

      {editing && (
        <EditDialog
          proposal={proposal}
          labels={labels}
          onClose={() => setEditing(false)}
          onSave={(approval) => {
            setEditing(false)
            onApprove(proposal, approval)
          }}
        />
      )}
      <RejectDialog
        isOpen={rejecting}
        onClose={() => setRejecting(false)}
        onReject={(reason) => {
          setRejecting(false)
          onReject(proposal, reason)
        }}
      />
    </li>
  )
}

function ProposalBody({ proposal, labels }: { proposal: ProposalRead; labels: Labels }) {
  if (proposal.action === 'archive') {
    return (
      <p>
        Put <strong>{proposal.target_label ?? `this ${proposal.entity_type}`}</strong> away. It leaves every list, and
        can be restored.
      </p>
    )
  }
  const rows = diffRows(proposal, labels)
  if (proposal.action === 'create') {
    return (
      <dl className="proposal-fields">
        {rows.map((row) => (
          <div key={row.field}>
            <dt>{row.field}</dt>
            <dd>{row.proposed}</dd>
          </div>
        ))}
      </dl>
    )
  }
  return (
    <table className="proposal-diff">
      <thead>
        <tr>
          <th scope="col">Field</th>
          <th scope="col">Current</th>
          <th scope="col">Proposed</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.field} data-changed={row.changed || undefined}>
            <th scope="row">{row.field}</th>
            <td>{row.current}</td>
            <td>{row.proposed}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const recordLinks = {
  contact: (id: string) => <Link to="/contacts/$contactId" params={{ contactId: id }}>Open the contact</Link>,
  organization: (id: string) => (
    <Link to="/organizations/$organizationId" params={{ organizationId: id }}>
      Open the organization
    </Link>
  ),
  deal: (id: string) => <Link to="/deals/$dealId" params={{ dealId: id }}>Open the deal</Link>,
  task: (id: string) => <Link to="/tasks/$taskId" params={{ taskId: id }}>Open the task</Link>,
  interaction: (id: string) => (
    <Link to="/interactions/$interactionId" params={{ interactionId: id }}>
      Open the interaction
    </Link>
  ),
}

// What became of a decided proposal.
function Outcome({ proposal }: { proposal: ProposalRead }) {
  if (proposal.status === 'approved') {
    return (
      <p className="proposal-outcome">
        <span className="badge" data-tone="success">
          Approved
        </span>{' '}
        {proposal.applied_payload && <span className="muted">after your edit · </span>}
        {proposal.target_id && recordLinks[proposal.entity_type](proposal.target_id)}
      </p>
    )
  }
  return (
    <p className="proposal-outcome">
      <span className="badge" data-tone="danger">
        Rejected
      </span>{' '}
      {proposal.rejection_reason && <span className="muted">“{proposal.rejection_reason}”</span>}
    </p>
  )
}

function RejectDialog({
  isOpen,
  onClose,
  onReject,
}: {
  isOpen: boolean
  onClose: () => void
  onReject: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  return (
    <Modal title="Reject proposal" isOpen={isOpen} onOpenChange={(open) => !open && onClose()}>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault()
          onReject(reason.trim())
          setReason('')
        }}
      >
        <TextField
          label="Note for the agent (optional)"
          value={reason}
          onChange={setReason}
          rows={3}
          maxLength={2000}
          autoFocus
        />
        <div className="form-actions">
          <Button variant="quiet" onPress={onClose}>
            Cancel
          </Button>
          <Button type="submit">Reject</Button>
        </div>
      </form>
    </Modal>
  )
}

// The entity's own form, prefilled with the record (for an update) and the
// proposal on top of it. Saving it approves with what the form holds.
function EditDialog({
  proposal,
  labels,
  onClose,
  onSave,
}: {
  proposal: ProposalRead
  labels: Labels
  onClose: () => void
  onSave: (approval: Approval) => void
}) {
  const { api } = useRouteContext({ from: '/_authed' })
  const queryClient = useQueryClient()
  const isUpdate = proposal.action === 'update' && proposal.target_id
  const target = useQuery({
    queryKey: ['proposals', 'target', proposal.entity_type, proposal.target_id],
    queryFn: () => targetRecord(queryClient, api, proposal.entity_type, proposal.target_id as string),
    enabled: Boolean(isUpdate),
    gcTime: 0,
  })

  let content: ReactNode
  if (isUpdate && target.isPending) content = <p className="muted">Loading…</p>
  else if (isUpdate && target.error) content = <p className="form-error">{target.error.message}</p>
  else {
    const base = (isUpdate ? target.data : undefined) as { version?: number } | undefined
    const save = (body: unknown) =>
      onSave({ payload: withUneditable(proposal, body as Record<string, unknown>), version: base?.version })
    content = (
      <EditForm
        proposal={proposal}
        initial={initialFor(proposal, base, labels)}
        onSubmit={save}
        cancel={
          <Button variant="quiet" onPress={onClose}>
            Cancel
          </Button>
        }
      />
    )
  }

  return (
    <Modal title={`Edit before approving: ${actionTitle(proposal).toLowerCase()}`} isOpen onOpenChange={(open) => !open && onClose()}>
      {content}
    </Modal>
  )
}

// The task form has no `done`, and saving replaces the proposal's payload with
// the form body, so a proposed completion would be dropped (and the task never
// completed or rescheduled). Carry it over.
function withUneditable(proposal: ProposalRead, body: Record<string, unknown>): Record<string, unknown> {
  const proposed = proposal.proposed_payload
  if (proposal.entity_type === 'task' && 'done' in proposed && !('done' in body)) return { ...body, done: proposed.done }
  return body
}

// What the forms show beside the ids: the names are read-only mirrors on the
// Read schemas, and the proposal only holds ids.
const mirrors: Record<string, string> = {
  organization_id: 'organization_name',
  contact_id: 'contact_name',
  deal_id: 'deal_title',
  interaction_id: 'interaction_subject',
}

function initialFor(proposal: ProposalRead, base: object | undefined, labels: Labels): Record<string, unknown> {
  const payload = proposal.applied_payload ?? proposal.proposed_payload
  const initial: Record<string, unknown> = {
    // What a form reads without checking, which a create has no record to take from.
    tags: [],
    contact_ids: [],
    organization_ids: [],
    deal_ids: [],
    project_ids: [],
    ...base,
    ...payload,
  }
  for (const [idField, mirror] of Object.entries(mirrors)) {
    const id = initial[idField]
    if (typeof id === 'string' && labels[id]) initial[mirror] = labels[id]
  }
  return initial
}

function EditForm({
  proposal,
  initial,
  onSubmit,
  cancel,
}: {
  proposal: ProposalRead
  initial: Record<string, unknown>
  onSubmit: (body: unknown) => void
  cancel: ReactNode
}) {
  const common = { onSubmit, submitLabel: 'Save and approve', pending: false, error: null, cancel }
  switch (proposal.entity_type) {
    case 'contact':
      return <ContactForm {...common} initial={initial as unknown as ContactRead} />
    case 'organization':
      return <OrganizationForm {...common} initial={initial as unknown as OrganizationRead} />
    case 'deal':
      return <DealForm {...common} initial={initial as unknown as DealRead} />
    case 'task':
      return <TaskForm {...common} initial={initial as unknown as TaskRead} />
    case 'interaction':
      return <InteractionForm {...common} initial={initial as unknown as InteractionRead} />
  }
}
