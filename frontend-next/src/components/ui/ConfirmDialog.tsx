import type { ReactNode } from 'react'
import { Button } from './Button'
import { Modal } from './Modal'

// "Are you sure?" before something that cannot be undone. The safe choice is
// the quiet one on the left; the error, if the action fails, stays in the
// dialog so it is read where it happened.
export function ConfirmDialog({
  title,
  isOpen,
  onOpenChange,
  onConfirm,
  confirmLabel,
  pendingLabel,
  pending,
  error,
  children,
}: {
  title: string
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onConfirm: () => void
  confirmLabel: string
  pendingLabel: string
  pending: boolean
  error?: Error | null
  children: ReactNode
}) {
  return (
    <Modal title={title} isOpen={isOpen} onOpenChange={onOpenChange}>
      {children}
      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}
      <div className="form-actions">
        <Button variant="quiet" onPress={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button className="button-danger" onPress={onConfirm} isDisabled={pending}>
          {pending ? pendingLabel : confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}
