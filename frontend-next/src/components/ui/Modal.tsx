import type { ReactNode } from 'react'
import { Dialog, Heading, Modal as AriaModal, ModalOverlay } from 'react-aria-components'

// React Aria's modal dialog: focus moves in and is trapped there, Escape and a
// click outside close it, focus returns to whatever opened it, and the page
// behind is hidden from screen readers. Controlled by the caller.
export function Modal({
  title,
  isOpen,
  onOpenChange,
  children,
}: {
  title: string
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  children: ReactNode
}) {
  return (
    <ModalOverlay className="modal-overlay" isOpen={isOpen} onOpenChange={onOpenChange} isDismissable>
      <AriaModal className="modal">
        <Dialog className="dialog">
          <Heading slot="title" className="dialog-title">
            {title}
          </Heading>
          {children}
        </Dialog>
      </AriaModal>
    </ModalOverlay>
  )
}
