import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useState } from 'react'
import type { CaptureRead } from '../api/types'
import { createCapture, deleteCapture, invalidateAfterCapture } from '../captures'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { TextField } from './ui/TextField'

// The always-there way to put someone in the inbox: one line, Enter, done.
// The server parses the line into a name and a link (a LinkedIn URL becomes
// "Jane Doe"), and every guess is fixable in triage.
// `className` picks the look: quick-note-sidebar or quick-note-fab. The shell
// renders both and styles.css shows one per screen size.
export function QuickCaptureButton({ className }: { className?: string }) {
  const [isOpen, setOpen] = useState(false)
  return (
    <>
      <Button className={`quick-note ${className ?? ''}`} onPress={() => setOpen(true)} aria-label="Quick note">
        <span aria-hidden="true">+</span>
        <span className="quick-note-label">Quick note</span>
      </Button>
      <QuickCaptureDialog isOpen={isOpen} onOpenChange={setOpen} />
    </>
  )
}

// Stays open after a save, with the field cleared and focused: the real motion
// is looking at a list of people and putting four of them in, not one.
export function QuickCaptureDialog({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
}) {
  const { api } = useRouteContext({ from: '/_authed' })
  const queryClient = useQueryClient()
  const [raw, setRaw] = useState('')
  const [note, setNote] = useState('')
  const [noteOpen, setNoteOpen] = useState(false)
  // Saved in this sitting, newest first: what Undo points at, and the count.
  const [saved, setSaved] = useState<CaptureRead[]>([])
  // Bumped after each save to remount the field, which puts the focus back.
  const [round, setRound] = useState(0)

  const save = useMutation({
    mutationFn: () => createCapture(api, { raw: raw.trim(), note: note.trim() || undefined }),
    onSuccess: async (capture) => {
      setSaved((prev) => [capture, ...prev])
      setRaw('')
      setNote('')
      setNoteOpen(false)
      setRound((n) => n + 1)
      await invalidateAfterCapture(queryClient)
    },
  })

  const undo = useMutation({
    mutationFn: (id: string) => deleteCapture(api, id),
    onSuccess: async (_, id) => {
      setSaved((prev) => prev.filter((c) => c.id !== id))
      await invalidateAfterCapture(queryClient)
    },
  })

  function close(open: boolean) {
    onOpenChange(open)
    if (!open) {
      setSaved([])
      save.reset()
    }
  }

  return (
    <Modal title="Quick note" isOpen={isOpen} onOpenChange={close}>
      <form
        className="quick-form"
        onSubmit={(e) => {
          e.preventDefault()
          // Enter on an empty field does nothing: it is a double tap, not an error.
          if (raw.trim() && !save.isPending) save.mutate()
        }}
      >
        <TextField
          key={round}
          label="Who or what"
          placeholder="A name, or paste a LinkedIn link"
          value={raw}
          onChange={setRaw}
          autoFocus
        />
        {noteOpen ? (
          <TextField label="Note" rows={2} value={note} onChange={setNote} />
        ) : (
          <Button variant="quiet" className="link-button" onPress={() => setNoteOpen(true)}>
            + Add a note
          </Button>
        )}

        {save.isError && (
          <p className="form-error" role="alert">
            {save.error.message}
          </p>
        )}

        {saved.length > 0 && (
          <div className="quick-saved" aria-live="polite">
            <p className="muted small">
              {saved.length} saved to the inbox — last:{' '}
              <strong>{saved[0].name ?? saved[0].raw}</strong>
            </p>
            <Button variant="quiet" className="link-button" onPress={() => undo.mutate(saved[0].id)}>
              Undo
            </Button>
          </div>
        )}

        <div className="form-actions">
          <Button variant="quiet" onPress={() => close(false)}>
            Done
          </Button>
          <Button type="submit" isDisabled={!raw.trim() || save.isPending}>
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
