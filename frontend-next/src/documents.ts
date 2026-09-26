import { keepPreviousData, type QueryClient, queryOptions } from '@tanstack/react-query'
import { type Api, unwrap } from './api/client'
import type { DocumentRead, DocumentUpdate } from './api/types'
import { PAGE_SIZE } from './contacts'

// Files are pdf, Markdown or plain text, up to 25 MB (routers/documents.py).
export const ACCEPTED_TYPES = ['.pdf', '.md', '.markdown', '.txt', 'application/pdf', 'text/markdown', 'text/plain']
export const MAX_BYTES = 25 * 1024 * 1024

export const extensionFor = (format: string) => ({ pdf: 'pdf', markdown: 'md', txt: 'txt' })[format] ?? 'bin'

export type DocumentLinks = Pick<DocumentUpdate, 'contact_ids' | 'organization_ids' | 'deal_ids' | 'project_ids'>

export const documentsQuery = (api: Api, { q, page = 1 }: { q?: string; page?: number }) =>
  queryOptions({
    queryKey: ['documents', 'list', { q, page }],
    queryFn: () =>
      unwrap(
        api.GET('/documents/', {
          params: { query: { search: q || undefined, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  })

export const documentQuery = (api: Api, id: string) =>
  queryOptions({
    queryKey: ['documents', 'detail', id],
    queryFn: () => unwrap(api.GET('/documents/{document_id}', { params: { path: { document_id: id } } })),
  })

export type DocumentLink = { contact_id?: string; organization_id?: string; deal_id?: string; project_id?: string }

export const linkedDocumentsQuery = (api: Api, link: DocumentLink) =>
  queryOptions({
    queryKey: ['documents', 'linked', link],
    queryFn: () => unwrap(api.GET('/documents/', { params: { query: { ...link, limit: 50 } } })),
  })

// The file itself and its first-page thumbnail are behind the login, so they
// are fetched with the token as blobs rather than linked to. `updated_at` is
// in the key: replacing the file must not show the old one from the cache.
export const contentQuery = (api: Api, doc: Pick<DocumentRead, 'id' | 'updated_at'>) =>
  queryOptions({
    queryKey: ['documents', 'content', doc.id, doc.updated_at],
    queryFn: () =>
      unwrap(
        api.GET('/documents/{document_id}/content', {
          params: { path: { document_id: doc.id } },
          parseAs: 'blob',
        }),
      ) as Promise<Blob>,
    staleTime: Infinity,
    gcTime: 60_000,
  })

export const previewQuery = (api: Api, doc: Pick<DocumentRead, 'id' | 'updated_at'>) =>
  queryOptions({
    queryKey: ['documents', 'preview', doc.id, doc.updated_at],
    queryFn: () =>
      unwrap(
        api.GET('/documents/{document_id}/preview', {
          params: { path: { document_id: doc.id } },
          parseAs: 'blob',
        }),
      ) as Promise<Blob>,
    staleTime: Infinity,
    retry: false,
  })

// Multipart has no list type, so the backend takes tags and link lists as
// JSON strings in form fields.
export function uploadDocument(
  api: Api,
  file: File,
  meta: { title: string; description: string | null; tags: string[] } & Required<DocumentLinks>,
) {
  const form = new FormData()
  form.append('file', file)
  form.append('title', meta.title)
  if (meta.description) form.append('description', meta.description)
  form.append('tags', JSON.stringify(meta.tags))
  form.append('contact_ids', JSON.stringify(meta.contact_ids))
  form.append('organization_ids', JSON.stringify(meta.organization_ids))
  form.append('deal_ids', JSON.stringify(meta.deal_ids))
  form.append('project_ids', JSON.stringify(meta.project_ids))
  return unwrap(
    api.POST('/documents/', {
      // The schema types the file as a string; the real body is the FormData.
      body: {} as never,
      bodySerializer: () => form,
    }),
  )
}

export function replaceContent(api: Api, id: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return unwrap(
    api.PUT('/documents/{document_id}/content', {
      params: { path: { document_id: id } },
      body: {} as never,
      bodySerializer: () => form,
    }),
  )
}

// Link lists are sent whole: they replace what is stored.
export const updateDocument = (api: Api, id: string, body: DocumentUpdate) =>
  unwrap(api.PATCH('/documents/{document_id}', { params: { path: { document_id: id } }, body }))

export const deleteDocument = (api: Api, id: string) =>
  unwrap(api.DELETE('/documents/{document_id}', { params: { path: { document_id: id } } }))

// Lists and details only. A file and its preview are keyed by `updated_at`,
// so they never go stale; refetching one that was just replaced asks for a
// preview that may no longer exist (404).
export const invalidateDocuments = (queryClient: QueryClient) =>
  queryClient.invalidateQueries({
    queryKey: ['documents'],
    predicate: (q) => q.queryKey[1] !== 'content' && q.queryKey[1] !== 'preview',
  })

// Saves a blob under a name, through a temporary link. The Flutter app's
// version needed a typed array (#51); a Blob from fetch is already one.
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// A filename that is safe on every OS, from the document's title.
export const filenameFor = (doc: Pick<DocumentRead, 'title' | 'format'>) =>
  `${doc.title.replace(/[\\/:*?"<>|]+/g, '-').trim() || 'document'}.${extensionFor(doc.format)}`
