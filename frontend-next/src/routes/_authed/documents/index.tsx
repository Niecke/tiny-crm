import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import type { DocumentRead } from '../../../api/types'
import { DocumentThumb } from '../../../components/DocumentThumb'
import { DocumentViewer } from '../../../components/DocumentViewer'
import { Button } from '../../../components/ui/Button'
import { Pagination } from '../../../components/ui/Pagination'
import { SearchField } from '../../../components/ui/SearchField'
import { PAGE_SIZE } from '../../../contacts'
import { contentQuery, documentsQuery, filenameFor, saveBlob } from '../../../documents'
import { formatBytes, formatDate } from '../../../format'
import { useDebounced } from '../../../useDebounced'

export const Route = createFileRoute('/_authed/documents/')({
  component: DocumentsList,
})

function DocumentsList() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const { q = '', page = 1 } = filters
  const navigate = Route.useNavigate()
  const queryClient = useQueryClient()

  const [input, setInput] = useState(q)
  const search = useDebounced(input.trim())
  useEffect(() => {
    if (search !== q)
      void navigate({ search: (prev) => ({ ...prev, q: search || undefined, page: undefined }), replace: true })
  }, [search, q, navigate])

  const { data, error, isPending, isPlaceholderData } = useQuery(documentsQuery(api, { q: search, page }))
  const [viewing, setViewing] = useState<DocumentRead | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function download(doc: DocumentRead) {
    setDownloadError(null)
    try {
      saveBlob(await queryClient.fetchQuery(contentQuery(api, doc)), filenameFor(doc))
    } catch (e) {
      setDownloadError(`Could not download “${doc.title}”: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return (
    <div className="page">
      <header className="page-header page-header-row">
        <h1>Documents</h1>
        <Link to="/documents/new" search={filters} className="button">
          Upload
        </Link>
      </header>

      <div className="toolbar filters">
        <SearchField label="Search documents" placeholder="Search titles and descriptions" value={input} onChange={setInput} />
      </div>

      {downloadError && (
        <p className="form-error" role="alert">
          {downloadError}
        </p>
      )}

      {isPending ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="form-error">{error.message}</p>
      ) : data.items.length === 0 && page === 1 ? (
        <p className="muted">{search ? `No document matches “${search}”.` : 'No documents yet.'}</p>
      ) : (
        <>
          <ul className="doc-grid" data-stale={isPlaceholderData || undefined}>
            {data.items.map((d) => (
              <li key={d.id} className="panel doc-card">
                <button type="button" className="doc-open" onClick={() => setViewing(d)} aria-label={`View ${d.title}`}>
                  <DocumentThumb doc={d} />
                </button>
                <div className="doc-body">
                  <Link to="/documents/$documentId" params={{ documentId: d.id }} search={filters} className="row-link doc-title">
                    {d.title}
                  </Link>
                  <span className="row-meta">
                    {d.format === 'markdown' ? 'Markdown' : d.format.toUpperCase()} · {formatBytes(d.size)} ·{' '}
                    {formatDate(d.created_at)}
                  </span>
                  {d.description && <p className="doc-description">{d.description}</p>}
                  {d.tags.length > 0 && (
                    <span className="chips">
                      {d.tags.map((t) => (
                        <span key={t} className="badge">
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                  <span className="doc-actions">
                    <Button variant="quiet" onPress={() => setViewing(d)}>
                      View
                    </Button>
                    <Button variant="quiet" onPress={() => void download(d)}>
                      Download
                    </Button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            isStale={isPlaceholderData}
            onChange={(next) => void navigate({ search: (prev) => ({ ...prev, page: next > 1 ? next : undefined }) })}
          />
        </>
      )}

      <DocumentViewer doc={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}
