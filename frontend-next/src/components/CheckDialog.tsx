import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useRouteContext } from '@tanstack/react-router'
import { useState } from 'react'
import type { WatchRead } from '../api/types'
import { invalidateWatches, logCheck } from '../watches'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { Segmented } from './ui/Segmented'
import { TextField } from './ui/TextField'

// Logging one sweep: nothing, or a find — and a find can become a deal or a
// task on the spot, before the browser tab with the posting is closed.
export function CheckDialog({ watch, isOpen, onOpenChange }: { watch: WatchRead; isOpen: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Modal title={`Sweep: ${watch.name}`} isOpen={isOpen} onOpenChange={onOpenChange}>
      {isOpen && <CheckForm watch={watch} onDone={() => onOpenChange(false)} />}
    </Modal>
  )
}

function CheckForm({ watch, onDone }: { watch: WatchRead; onDone: () => void }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<'nothing' | 'found'>('nothing')
  const [note, setNote] = useState('')
  // A tender is usually a deal; a job posting usually a task to apply.
  const [as, setAs] = useState<'deal' | 'task'>(watch.kind === 'tender_portal' ? 'deal' : 'task')
  const [title, setTitle] = useState('')
  const [made, setMade] = useState<{ deal?: string; task?: string } | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      logCheck(api, watch.id, {
        outcome,
        note: note.trim() || null,
        // Only with a find, and only with a title: an empty title just records
        // the note.
        create_deal: outcome === 'found' && as === 'deal' && title.trim() ? { title: title.trim() } : null,
        create_task: outcome === 'found' && as === 'task' && title.trim() ? { title: title.trim() } : null,
      }),
    onSuccess: async ({ check }) => {
      await invalidateWatches(queryClient)
      if (check.created_deal_id || check.created_task_id)
        setMade({ deal: check.created_deal_id ?? undefined, task: check.created_task_id ?? undefined })
      else onDone()
    },
  })

  if (made) {
    return (
      <div className="quick-form">
        <p className="notice" role="status">
          Logged, and made a {made.deal ? 'deal' : 'task'} from it.
        </p>
        <div className="form-actions">
          <Button variant="quiet" onPress={onDone}>
            Close
          </Button>
          {made.deal ? (
            <Link to="/deals/$dealId" params={{ dealId: made.deal }} className="button">
              Open the deal
            </Link>
          ) : (
            made.task && (
              <Link to="/tasks/$taskId" params={{ taskId: made.task }} className="button">
                Open the task
              </Link>
            )
          )}
        </div>
      </div>
    )
  }

  return (
    <form
      className="quick-form"
      onSubmit={(e) => {
        e.preventDefault()
        mutation.mutate()
      }}
    >
      {watch.query_note && <p className="muted small">Looking for: {watch.query_note}</p>}
      <Segmented
        label="Outcome"
        value={outcome}
        onChange={setOutcome}
        options={[
          { value: 'nothing', label: 'Nothing new' },
          { value: 'found', label: 'Found something' },
        ]}
      />
      {outcome === 'found' && (
        <>
          <Segmented
            label="Turn it into"
            value={as}
            onChange={setAs}
            options={[
              { value: 'deal', label: 'A deal' },
              { value: 'task', label: 'A task' },
            ]}
          />
          <TextField
            label={as === 'deal' ? 'Deal title' : 'Task title'}
            value={title}
            onChange={setTitle}
            autoFocus
            description="Leave empty to only record the note."
          />
        </>
      )}
      <TextField label="Note" value={note} onChange={setNote} rows={2} />
      {mutation.error && (
        <p className="form-error" role="alert">
          {mutation.error.message}
        </p>
      )}
      <div className="form-actions">
        <Button variant="quiet" onPress={onDone}>
          Cancel
        </Button>
        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Logging…' : 'Log sweep'}
        </Button>
      </div>
    </form>
  )
}
