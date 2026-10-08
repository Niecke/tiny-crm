import type { UseQueryResult } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from './api/client'

// Two tabs on the same record used to mean the last save silently won (#142).
// Every record now carries a `version`, and a save that sends the one its form
// was opened from is refused with 409 once someone else has saved since.
//
// The version has to be the one the form was *opened* from, not whatever the
// query holds by the time Save is pressed: the query refetches in the
// background (on window focus, after other writes), and sending the fresh
// version would wave through exactly the overwrite the check exists to catch.
//
// For the edit pages whose form keeps its own state while the record moves on
// underneath. Pages that remount their form whenever the record changes (a
// task, an interaction, a document) can send the record's version as it is.
export function useEditVersion<T extends { version: number }>(record: UseQueryResult<T>) {
  const [opened, setOpened] = useState<number>()
  // Bumped to remount the form, so it starts again from the reloaded record.
  const [formKey, setFormKey] = useState(0)
  if (opened === undefined && record.data) setOpened(record.data.version)

  return {
    version: opened ?? record.data?.version,
    formKey,
    // Drop the edits and start over from what is saved now.
    reload: async () => {
      const { data } = await record.refetch()
      if (data) setOpened(data.version)
      setFormKey((key) => key + 1)
    },
  }
}

// The API's answer to a save made from an outdated copy. Matched on the
// wording as well as the status: an archived record answers 409 too, and
// reloading would not help with that one.
export function isStaleSave(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.message.includes('changed elsewhere')
}

// What a form shows as its own error: everything but a stale save, which
// <StaleSaveNotice> explains instead.
export const formError = (error: Error | null) => (isStaleSave(error) ? null : error)
