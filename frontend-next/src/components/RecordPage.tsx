import type { UseQueryResult } from '@tanstack/react-query'
import { Children, type ReactNode } from 'react'

// The pieces every record page is built from (FRONTEND.md, "Record pages"):
// a facts column on the left, linked records in tabs on the right.

// Label above value: the column is narrow, so the eye reads straight down
// instead of jumping across a wide row from label to value. Children are the
// <Fact>s that have a value; with none, the panel says so.
export function Facts({ children, before }: { children: ReactNode; before?: ReactNode }) {
  const facts = Children.toArray(children).filter(Boolean)
  return (
    <aside className="panel facts" aria-label="Details">
      {before}
      {facts.length === 0 ? <p className="muted small">No details yet.</p> : <dl>{facts}</dl>}
    </aside>
  )
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// The first page of one linked record type, and a line saying how many are
// not shown.
export function Rows<T>({
  query,
  empty,
  children,
}: {
  // The generated Page_*_ schemas all share this shape.
  query: UseQueryResult<{ items: T[]; total: number }>
  empty: string
  children: (item: T) => ReactNode
}) {
  const { data, error, isPending } = query
  if (isPending) return <p className="muted">Loading…</p>
  if (error) return <p className="form-error">{error.message}</p>
  if (data.items.length === 0) return <p className="muted">{empty}</p>
  return (
    <>
      <ul className="rows">{data.items.map(children)}</ul>
      {data.total > data.items.length && (
        <p className="muted small">{data.total - data.items.length} more not shown.</p>
      )}
    </>
  )
}
