import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { useState } from 'react'
import { ApiError } from '../../../api/client'
import { ArchiveButton, ArchivedNotice, ReadOnlyWhenArchived } from '../../../components/Archive'
import { useArchive } from '../../../useArchive'
import { DocumentForm, type DocumentFields, FilePicker } from '../../../components/DocumentForm'
import { DocumentThumb } from '../../../components/DocumentThumb'
import { DocumentViewer } from '../../../components/DocumentViewer'
import { Button } from '../../../components/ui/Button'
import { Modal } from '../../../components/ui/Modal'
import {
  archiveDocument,
  contentQuery,
  deleteDocument,
  documentQuery,
  filenameFor,
  invalidateDocuments,
  replaceContent,
  restoreDocument,
  saveBlob,
  updateDocument,
} from '../../../documents'
import { formatBytes, formatDateTime } from '../../../format'
import { StaleSaveNotice } from '../../../components/StaleSaveNotice'
import { formError } from '../../../useEditVersion'

// A document's page: the file (view, download, replace) and its details form.
export const Route = createFileRoute('/_authed/documents/$documentId')({
  component: DocumentPage,
})

function DocumentPage() {
  const { api } = Route.useRouteContext()
  const { documentId } = Route.useParams()
  const filters = Route.useSearch()
  const queryClient = useQueryClient()
  const doc = useQuery(documentQuery(api, documentId))
  const [viewing, setViewing] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const [newFile, setNewFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const leave = useLeave({ to: '/documents', search: filters })

  // The form below is remounted whenever the document changes, so the version on
  // screen is always the one it was filled from (#142, see useEditVersion).
  const save = useMutation({
    mutationFn: (fields: DocumentFields) => updateDocument(api, documentId, fields, doc.data?.version),
    onSuccess: async (saved) => {
      queryClient.setQueryData(documentQuery(api, documentId).queryKey, saved)
      await invalidateDocuments(queryClient)
      await leave()
    },
  })

  const replace = useMutation({
    mutationFn: (file: File) => replaceContent(api, documentId, file),
    onSuccess: async (saved) => {
      queryClient.setQueryData(documentQuery(api, documentId).queryKey, saved)
      await invalidateDocuments(queryClient)
      setReplacing(false)
      setNewFile(null)
    },
  })

  const archiving = useArchive({
    queryKey: documentQuery(api, documentId).queryKey,
    archive: () => archiveDocument(api, documentId),
    restore: () => restoreDocument(api, documentId),
    remove: () => deleteDocument(api, documentId),
    leave,
    alsoRemove: [
      ['documents', 'content', documentId],
      ['documents', 'preview', documentId],
    ],
  })

  const download = useMutation({
    mutationFn: async () => {
      if (!doc.data) return
      saveBlob(await queryClient.fetchQuery(contentQuery(api, doc.data)), filenameFor(doc.data))
    },
  })

  const d = doc.data

  return (
    <div className="page page-narrow">
      <Link to="/documents" search={filters} className="back-link">
        ← Documents
      </Link>
      <header className="page-header">
        <h1>{d?.title ?? 'Document'}</h1>
      </header>
      <StaleSaveNotice error={save.error} onReload={() => void doc.refetch().then(() => save.reset())} />

      {doc.isPending ? (
        <p className="muted">Loading…</p>
      ) : doc.error || !d ? (
        <p className="form-error">
          {doc.error instanceof ApiError && doc.error.status === 404
            ? 'This document does not exist, or was deleted.'
            : doc.error?.message}
        </p>
      ) : (
        <>
          <ArchivedNotice record={d} noun="document" name={d.title} archiving={archiving}>
            The file goes with it, from every record it is filed under.
          </ArchivedNotice>
          <section className="panel doc-file">
            <button type="button" className="doc-open" onClick={() => setViewing(true)} aria-label={`View ${d.title}`}>
              <DocumentThumb doc={d} />
            </button>
            <div className="doc-body">
              <span>
                {d.format === 'markdown' ? 'Markdown' : d.format.toUpperCase()} · {formatBytes(d.size)}
              </span>
              <span className="row-meta">Updated {formatDateTime(d.updated_at)}</span>
              <span className="doc-actions">
                <Button onPress={() => setViewing(true)}>View</Button>
                <Button variant="quiet" onPress={() => download.mutate()} isDisabled={download.isPending}>
                  {download.isPending ? 'Downloading…' : 'Download'}
                </Button>
                {/* Still viewed and downloaded once archived; not replaced. */}
                {!d.archived_at && (
                  <Button variant="quiet" onPress={() => setReplacing(true)}>
                    Replace file
                  </Button>
                )}
              </span>
              {download.error && <p className="form-error">{download.error.message}</p>}
            </div>
          </section>

          <ReadOnlyWhenArchived record={d}>
            <DocumentForm
              key={d.updated_at}
              initial={d}
              onSubmit={(fields) => save.mutate(fields)}
              submitLabel="Save changes"
              pending={save.isPending}
              error={formError(save.error)}
              cancel={
                <Button variant="quiet" onPress={() => void leave()}>
                  Cancel
                </Button>
              }
              extraActions={!d.archived_at && <ArchiveButton archiving={archiving} />}
            />
          </ReadOnlyWhenArchived>
        </>
      )}

      <DocumentViewer doc={viewing && d ? d : null} onClose={() => setViewing(false)} />

      <Modal title="Replace the file" isOpen={replacing} onOpenChange={setReplacing}>
        <p className="muted small">
          The title, details and links stay; the old file is kept as a version in storage.
        </p>
        <FilePicker
          label="New file"
          file={newFile}
          error={fileError}
          onChange={(f, problem) => {
            setNewFile(f)
            setFileError(problem)
          }}
        />
        {replace.error && (
          <p className="form-error" role="alert">
            {replace.error.message}
          </p>
        )}
        <div className="form-actions">
          <Button variant="quiet" onPress={() => setReplacing(false)}>
            Cancel
          </Button>
          <Button isDisabled={!newFile || replace.isPending} onPress={() => newFile && replace.mutate(newFile)}>
            {replace.isPending ? 'Uploading…' : 'Replace'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}
