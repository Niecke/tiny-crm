import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type PDFPageProxy } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
import { useEffect, useRef, useState } from 'react'

// pdf.js, loaded only when a PDF is opened (DocumentViewer imports this file
// lazily), so the rest of the app does not carry it. The worker is a file of
// its own, served from our origin. The legacy build: the modern one relies on
// JavaScript too new for current Chrome and Safari (Map#getOrInsertComputed)
// and fails on them outright.
GlobalWorkerOptions.workerSrc = workerUrl

// Enough to read a contract or an offer; a longer PDF is a download.
const MAX_PAGES = 50

export default function PdfView({ blob }: { blob: Blob }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    // Destroying the loading task also destroys the document and its worker.
    let task: ReturnType<typeof getDocument> | null = null
    void blob
      .arrayBuffer()
      .then((data) => {
        if (cancelled) return null
        task = getDocument({ data })
        return task.promise
      })
      .then((doc) => {
        if (doc && !cancelled) setPdf(doc)
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
      void task?.destroy()
    }
  }, [blob])

  if (error) return <p className="form-error">This PDF could not be shown: {error}</p>
  if (!pdf) return <p className="muted">Rendering…</p>
  const pages = Math.min(pdf.numPages, MAX_PAGES)
  return (
    <div className="pdf-pages">
      {Array.from({ length: pages }, (_, n) => (
        <PdfPage key={n} pdf={pdf} number={n + 1} />
      ))}
      {pdf.numPages > pages && (
        <p className="muted small">
          {pdf.numPages - pages} more pages not shown — download the file to read them.
        </p>
      )}
    </div>
  )
}

function PdfPage({ pdf, number }: { pdf: PDFDocumentProxy; number: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    // The page arrives asynchronously, so the effect may already be cleaned
    // up (a re-render, StrictMode's double run) before drawing starts; a
    // canvas takes one render at a time.
    let cancelled = false
    let task: ReturnType<PDFPageProxy['render']> | null = null
    void pdf.getPage(number).then((page) => {
      const target = canvas.current
      if (cancelled || !target) return
      // Sharp on high-density screens: drawn at the device's pixel ratio and
      // shown at the container's width.
      const ratio = window.devicePixelRatio || 1
      const width = target.parentElement?.clientWidth ?? 800
      const base = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: (width / base.width) * ratio })
      target.width = viewport.width
      target.height = viewport.height
      target.style.width = `${viewport.width / ratio}px`
      task = page.render({ canvas: target, viewport })
      // Cancelling rejects the promise; that is expected, not an error.
      task.promise.catch(() => {})
    })
    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [pdf, number])
  return <canvas ref={canvas} className="pdf-page" aria-label={`Page ${number}`} />
}
