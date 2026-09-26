import { Button } from './Button'

// Prev / next under a paged list, with where in the list this page is. The
// page number lives in the URL (?page=), so the caller owns it. Silent when
// everything fits on one page.
export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  isStale,
}: {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
  isStale?: boolean
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1 && page <= 1) return null
  const first = Math.min(total, (page - 1) * pageSize + 1)
  const last = Math.min(total, page * pageSize)
  return (
    <nav className="pagination" aria-label="Pages">
      <span className="muted small" aria-live="polite">
        {total === 0 ? 'Nothing on this page' : `${first}–${last} of ${total}`}
      </span>
      <span className="pagination-buttons">
        <Button variant="quiet" isDisabled={page <= 1 || isStale} onPress={() => onChange(page - 1)}>
          ‹ Previous
        </Button>
        <span className="muted small">
          {page} / {pages}
        </span>
        <Button variant="quiet" isDisabled={page >= pages || isStale} onPress={() => onChange(page + 1)}>
          Next ›
        </Button>
      </span>
    </nav>
  )
}
