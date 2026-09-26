import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import type { DocumentRead } from '../api/types'
import { previewQuery } from '../documents'

// The first page of a PDF, when the server made a preview; otherwise the
// format, large, on an A4-shaped card.
export function DocumentThumb({ doc }: { doc: DocumentRead }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const preview = useQuery({ ...previewQuery(api, doc), enabled: doc.has_preview })
  return (
    <span className="doc-thumb" aria-hidden="true">
      {preview.data ? (
        <BlobImage blob={preview.data} />
      ) : (
        <span className="doc-format">{doc.format === 'markdown' ? 'MD' : doc.format.toUpperCase()}</span>
      )}
    </span>
  )
}

// An image from a blob. The object URL is revoked when the blob changes or the
// image goes away; without that, every preview shown stays in memory for the
// life of the tab.
function BlobImage({ blob }: { blob: Blob }) {
  const img = useRef<HTMLImageElement>(null)
  useEffect(() => {
    const url = URL.createObjectURL(blob)
    if (img.current) img.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [blob])
  return <img ref={img} alt="" />
}
