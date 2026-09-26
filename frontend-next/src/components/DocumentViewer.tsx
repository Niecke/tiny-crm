import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Dialog, Heading, Modal, ModalOverlay } from 'react-aria-components'
import type { DocumentRead } from '../api/types'
import { contentQuery, filenameFor, saveBlob } from '../documents'
import { Markdown } from './Markdown'
import { Button } from './ui/Button'

const PdfView = lazy(() => import('./PdfView'))

// A document read in place: a PDF drawn by pdf.js, Markdown rendered, plain
// text as it is. Full screen on a phone, a wide dialog on a desktop.
export function DocumentViewer({ doc, onClose }: { doc: DocumentRead | null; onClose: () => void }) {
  return (
    <ModalOverlay className="modal-overlay" isOpen={doc !== null} onOpenChange={(open) => !open && onClose()} isDismissable>
      <Modal className="modal viewer">
        <Dialog className="dialog viewer-dialog">{doc && <ViewerBody doc={doc} onClose={onClose} />}</Dialog>
      </Modal>
    </ModalOverlay>
  )
}

function ViewerBody({ doc, onClose }: { doc: DocumentRead; onClose: () => void }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const content = useQuery(contentQuery(api, doc))
  return (
    <>
      <div className="viewer-head">
        <Heading slot="title" className="dialog-title">
          {doc.title}
        </Heading>
        <span className="viewer-actions">
          <Button variant="quiet" isDisabled={!content.data} onPress={() => content.data && saveBlob(content.data, filenameFor(doc))}>
            Download
          </Button>
          <Button variant="quiet" onPress={onClose}>
            Close
          </Button>
        </span>
      </div>
      <div className="viewer-body">
        {content.isPending ? (
          <p className="muted">Loading…</p>
        ) : content.error ? (
          <p className="form-error">{content.error.message}</p>
        ) : doc.format === 'pdf' ? (
          <Suspense fallback={<p className="muted">Loading the PDF viewer…</p>}>
            <PdfView blob={content.data} />
          </Suspense>
        ) : (
          <TextContent blob={content.data} markdown={doc.format === 'markdown'} />
        )}
      </div>
    </>
  )
}

// Decoded as UTF-8; a malformed byte becomes a replacement character rather
// than an error, as in the Flutter viewer.
function TextContent({ blob, markdown }: { blob: Blob; markdown: boolean }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void blob.arrayBuffer().then((buf) => !cancelled && setText(new TextDecoder('utf-8').decode(buf)))
    return () => {
      cancelled = true
    }
  }, [blob])
  if (text === null) return <p className="muted">Loading…</p>
  return markdown ? <Markdown>{text}</Markdown> : <pre className="viewer-text">{text}</pre>
}
