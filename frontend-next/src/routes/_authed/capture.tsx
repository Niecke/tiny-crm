import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'
import { captureQuery, createCapture, invalidateAfterCapture } from '../../captures'
import { QuickCaptureDialog } from '../../components/QuickCapture'
import { Button } from '../../components/ui/Button'

// Where Android's share sheet lands: /next/capture?title=…&text=…&url=…,
// declared as the share_target in public/manifest.json. "Share → tinyCRM"
// from LinkedIn or Chrome files a person without opening the app first.
//
// Behind the login like every other page: a share while signed out goes
// through /login and comes back here with the parameters intact.
const searchSchema = z.object({
  title: z.string().optional().catch(undefined),
  text: z.string().optional().catch(undefined),
  url: z.string().optional().catch(undefined),
  // Set once the share is saved, replacing the three above — so a reload or
  // the back button shows the result instead of filing it a second time.
  saved: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/capture')({
  validateSearch: searchSchema,
  component: SharedCapture,
})

// The three parameters as the one line the capture box takes. Android fills
// them inconsistently — Chrome sends title + url, some apps put the url
// inside `text` and nothing else — so the distinct non-empty parts are joined.
export function composeRaw(parts: (string | undefined)[]): string {
  const seen: string[] = []
  for (const part of parts) {
    const trimmed = part?.trim() ?? ''
    // `text` frequently repeats the title or the url verbatim.
    if (trimmed && !seen.includes(trimmed)) seen.push(trimmed)
  }
  return seen.join(' ')
}

function SharedCapture() {
  const { api } = Route.useRouteContext()
  const { title, text, url, saved } = Route.useSearch()
  const navigate = Route.useNavigate()
  const queryClient = useQueryClient()
  const [quickOpen, setQuickOpen] = useState(false)
  const raw = composeRaw([title, text, url])

  const save = useMutation({
    // Android already handed over the url, so the parser does not have to
    // find it again in a string built here.
    mutationFn: () => createCapture(api, { raw, url: url?.trim() || undefined }),
    onSuccess: async (capture) => {
      await invalidateAfterCapture(queryClient)
      await navigate({ search: { saved: capture.id }, replace: true })
    },
  })

  // Once per arrival. The ref survives React's development double-mount,
  // which would otherwise save every share twice.
  const started = useRef(false)
  useEffect(() => {
    if (started.current || saved || !raw) return
    started.current = true
    save.mutate()
  }, [saved, raw, save])

  const result = useQuery({ ...captureQuery(api, saved ?? ''), enabled: Boolean(saved) })

  return (
    <div className="page page-narrow">
      <section className="panel share-result" aria-live="polite">
        {saved ? (
          result.data ? (
            <>
              <p className="share-mark" aria-hidden="true">
                ✓
              </p>
              <h1>{result.data.name ?? result.data.raw}</h1>
              <p className="muted">is in the inbox.</p>
            </>
          ) : (
            <p className="muted">Saved.</p>
          )
        ) : !raw ? (
          <>
            <h1>Nothing was shared</h1>
            <p className="muted">The share arrived empty. Type it in instead.</p>
          </>
        ) : save.isError ? (
          <>
            <h1>Could not save it</h1>
            <p className="form-error">{save.error.message}</p>
            <p className="muted small">{raw}</p>
          </>
        ) : (
          <p className="muted">Saving…</p>
        )}

        <div className="form-actions share-actions">
          {save.isError && (
            <Button variant="quiet" onPress={() => save.mutate()}>
              Try again
            </Button>
          )}
          <Button variant="quiet" onPress={() => setQuickOpen(true)}>
            {saved ? 'Add another' : 'Type it in instead'}
          </Button>
          <Link to="/inbox" className="button">
            Open the inbox
          </Link>
        </div>
      </section>
      <QuickCaptureDialog isOpen={quickOpen} onOpenChange={setQuickOpen} />
    </div>
  )
}
