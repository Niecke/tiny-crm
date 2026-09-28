import { useState } from 'react'
import type { DealRead } from '../api/types'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { TextField } from './ui/TextField'

// Why a deal was lost, asked on the way to Lost. Optional on purpose.
export function LostReasonDialog({
  deal,
  onConfirm,
  onCancel,
}: {
  deal: DealRead | null
  onConfirm: (reason: string) => void
  onCancel: () => void
}) {
  return (
    <Modal title="Mark as lost" isOpen={deal !== null} onOpenChange={(open) => !open && onCancel()}>
      {/* Keyed so the reason starts empty for every deal. */}
      {deal && <LostForm key={deal.id} deal={deal} onConfirm={onConfirm} onCancel={onCancel} />}
    </Modal>
  )
}

function LostForm({ deal, onConfirm, onCancel }: { deal: DealRead; onConfirm: (r: string) => void; onCancel: () => void }) {
  const [reason, setReason] = useState('')
  return (
    <form
      className="quick-form"
      onSubmit={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onConfirm(reason.trim())
      }}
    >
      <p>
        <strong>{deal.title}</strong> moves to Lost; its probability goes to 0%.
      </p>
      <TextField
        label="Why was it lost?"
        value={reason}
        onChange={setReason}
        rows={2}
        autoFocus
        description="Optional. Price, timing, went with someone else…"
      />
      <div className="form-actions">
        <Button variant="quiet" onPress={onCancel}>
          Cancel
        </Button>
        <Button type="submit">Mark as lost</Button>
      </div>
    </form>
  )
}
