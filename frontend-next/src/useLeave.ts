import { type NavigateOptions, useCanGoBack, useNavigate, useRouter } from '@tanstack/react-router'

// Back to where a form was opened from — a record page, a list — or, when the
// page was opened directly, to `fallback`. The promise settles once the
// destination has rendered, so a delete can drop the record's cached query
// after its page is gone rather than while it would still refetch it (404).
export function useLeave(fallback: NavigateOptions): () => Promise<void> {
  const router = useRouter()
  const navigate = useNavigate()
  const canGoBack = useCanGoBack()
  return () => {
    if (!canGoBack) return navigate(fallback)
    return new Promise<void>((resolve) => {
      const unsubscribe = router.subscribe('onResolved', () => {
        unsubscribe()
        resolve()
      })
      router.history.back()
    })
  }
}
