import type { UseQueryResult } from '@tanstack/react-query'
import { Children, type ReactNode } from 'react'

// The pieces every record page is built from (FRONTEND.md, "Record pages"):
// a main column (facts, then notes) and a side column with the linked records
// in tabs. Below 1440px the facts stay a narrow column beside the tabs; from
// 1440px both columns are wide.

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

// The main column of a record page: facts, then the notes panel, as one grid cell.
export function ProfileMain({ children }: { children: ReactNode }) {
  return <div className="profile-main">{children}</div>
}

// Notes (or a description) as a panel of their own, at the full width of the
// main column, instead of one squeezed fact.
export function Notes({ label = 'Notes', children }: { label?: string; children: ReactNode }) {
  return (
    <section className="panel record-notes" aria-label={label}>
      <h2 className="record-notes-title">{label}</h2>
      <div className="record-notes-body">{children}</div>
    </section>
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
