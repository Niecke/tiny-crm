import { isStaleSave } from '../useEditVersion'
import { Button } from './ui/Button'

// Above an edit form whose save was refused because someone else saved first
// (#142). Saving again cannot work, so the one way forward is offered: load
// what is saved now. The edits made here are lost, and the notice says so.
export function StaleSaveNotice({ error, onReload }: { error: Error | null; onReload: () => void }) {
  if (!isStaleSave(error)) return null
  return (
    <div className="notice" role="alert">
      <p>
        <strong>This was changed elsewhere since you opened it.</strong> Saving now would overwrite that change. Load
        the latest version to see it — your edits here will be discarded.
      </p>
      <Button variant="quiet" onPress={onReload}>
        Load latest version
      </Button>
    </div>
  )
}
