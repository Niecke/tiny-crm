import { type ReactNode, useState } from 'react'
import { formatDate } from '../format'
import type { Archivable, Archiving } from '../useArchive'
import { Button } from './ui/Button'
import { Checkbox } from './ui/Checkbox'
import { ConfirmDialog } from './ui/ConfirmDialog'

// Archive instead of delete (#140), the same on every record page.
//
// Archiving puts a record away: it leaves every list and the search, stays
// reachable from whatever links to it, and comes back with Restore. Deleting
// is only offered on a record that is already archived — two steps on purpose,
// because it is the one that cannot be undone and it takes the links with it.
//
// An archived record is read-only (the API answers 409), so a page shows
// <ArchivedNotice> in place of its edit controls rather than next to them.

// Where Delete used to be, on a record that is still in use. No confirmation:
// Restore is one click away on the notice that replaces this button.
export function ArchiveButton({ archiving }: { archiving: Archiving }) {
  return (
    <Button variant="quiet" onPress={() => archiving.archive.mutate()} isDisabled={archiving.archive.isPending}>
      {archiving.archive.isPending ? 'Archiving…' : 'Archive'}
    </Button>
  )
}

// At the top of a record page. Says nothing for a record in use, unless
// archiving it just failed.
export function ArchivedNotice({
  record,
  noun,
  name,
  archiving,
  children,
}: {
  record: Archivable
  // "contact", "deal" — lower case, as it reads mid-sentence.
  noun: string
  name: string
  archiving: Archiving
  // What else goes when this is deleted for good, said in the confirmation.
  children?: ReactNode
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const error = archiving.archive.error ?? archiving.restore.error

  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}
      {record.archived_at && (
        <div className="notice archived-notice" role="status">
          <p>
            <strong>Archived {formatDate(record.archived_at)}.</strong> This {noun} is hidden from lists and search,
            and cannot be changed until it is restored.
          </p>
          <span className="archived-actions">
            <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
              Delete permanently
            </Button>
            <Button onPress={() => archiving.restore.mutate()} isDisabled={archiving.restore.isPending}>
              {archiving.restore.isPending ? 'Restoring…' : 'Restore'}
            </Button>
          </span>
        </div>
      )}
      <ConfirmDialog
        title={`Delete this ${noun} permanently?`}
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => archiving.remove.mutate()}
        confirmLabel="Delete permanently"
        pendingLabel="Deleting…"
        pending={archiving.remove.isPending}
        error={archiving.remove.error}
      >
        <p>
          <strong>{name}</strong> will be deleted for good. This cannot be undone. {children}
        </p>
      </ConfirmDialog>
    </>
  )
}

// The archive is its own list, never mixed into the other one — so this is a
// switch between the two, not a filter that adds rows.
export function ArchivedToggle({ isSelected, onChange }: { isSelected: boolean; onChange: (archived: boolean) => void }) {
  return (
    <Checkbox isSelected={isSelected} onChange={onChange}>
      Archived
    </Checkbox>
  )
}

// Around a form on a page that is its record's form (a task, an interaction,
// a document): a disabled fieldset turns every control in it off at once, and
// still lets the values be read.
export function ReadOnlyWhenArchived({ record, children }: { record: Archivable; children: ReactNode }) {
  return (
    <fieldset className="form-lock" disabled={Boolean(record.archived_at)}>
      {children}
    </fieldset>
  )
}
