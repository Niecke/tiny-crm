import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { useState } from 'react'
import { ApiError } from '../../../api/client'
import { DocumentForm, type DocumentFields, FilePicker } from '../../../components/DocumentForm'
import { DocumentThumb } from '../../../components/DocumentThumb'
import { DocumentViewer } from '../../../components/DocumentViewer'
import { Button } from '../../../components/ui/Button'
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog'
import { Modal } from '../../../components/ui/Modal'
import {
  contentQuery,
  deleteDocument,
  documentQuery,
  filenameFor,
  invalidateDocuments,
  replaceContent,
  saveBlob,
  updateDocument,
} from '../../../documents'
import { formatBytes, formatDateTime } from '../../../format'

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
  const [confirmDelete, setConfirmDelete] = useState(false)
  const leave = useLeave({ to: '/documents', search: filters })

  const save = useMutation({
    mutationFn: (fields: DocumentFields) => updateDocument(api, documentId, fields),
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

  const remove = useMutation({
    mutationFn: () => deleteDocument(api, documentId),
    onSuccess: async () => {
      await leave()
      queryClient.removeQueries({ queryKey: documentQuery(api, documentId).queryKey })
      queryClient.removeQueries({ queryKey: ['documents', 'content', documentId] })
      queryClient.removeQueries({ queryKey: ['documents', 'preview', documentId] })
      await invalidateDocuments(queryClient)
    },
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
                <Button variant="quiet" onPress={() => setReplacing(true)}>
                  Replace file
                </Button>
              </span>
              {download.error && <p className="form-error">{download.error.message}</p>}
            </div>
          </section>

          <DocumentForm
            key={d.updated_at}
            initial={d}
            onSubmit={(fields) => save.mutate(fields)}
            submitLabel="Save changes"
            pending={save.isPending}
            error={save.error}
            cancel={
              <Button variant="quiet" onPress={() => void leave()}>
                Cancel
              </Button>
            }
            extraActions={
              <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
                Delete
              </Button>
            }
          />
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

      <ConfirmDialog
        title="Delete this document?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{d?.title}</strong> will be permanently deleted, from every record it is filed under.
        </p>
      </ConfirmDialog>
    </div>
  )
}
