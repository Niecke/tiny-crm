import { type QueryKey, useMutation, useQueryClient } from '@tanstack/react-query'

// Archiving, restoring and deleting one record, wherever its page is — the
// mutations behind the controls in components/Archive.tsx (#140).

export type Archivable = { archived_at?: string | null }

export function useArchive<T extends Archivable>({
  queryKey,
  archive,
  restore,
  remove,
  leave,
  alsoRemove = [],
}: {
  // The record's own query: updated after archive and restore, dropped after
  // a delete.
  queryKey: QueryKey
  archive: () => Promise<T>
  restore: () => Promise<T>
  remove: () => Promise<unknown>
  // Where to go once the record is deleted.
  leave: () => Promise<unknown>
  // Other queries that only exist for this record — a document's file.
  alsoRemove?: QueryKey[]
}) {
  const queryClient = useQueryClient()
  // Everything is refetched, not just this record type's lists: an archived
  // record also leaves the search, the briefing, the dashboard's numbers and
  // the tabs of every record it is linked to. It is a rare action, and only
  // the queries on screen are fetched again.
  const onChanged = async (saved: T) => {
    queryClient.setQueryData(queryKey, saved)
    await queryClient.invalidateQueries()
  }
  return {
    archive: useMutation({ mutationFn: archive, onSuccess: onChanged }),
    restore: useMutation({ mutationFn: restore, onSuccess: onChanged }),
    remove: useMutation({
      mutationFn: remove,
      // Leave first, then drop the record's cache — the other way round the
      // page would refetch it and show a 404.
      onSuccess: async () => {
        await leave()
        for (const key of [queryKey, ...alsoRemove]) queryClient.removeQueries({ queryKey: key })
        await queryClient.invalidateQueries()
      },
    }),
  }
}

export type Archiving = ReturnType<typeof useArchive>
