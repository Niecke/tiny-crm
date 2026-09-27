// A task's priority at a glance (#137). Red is taken — it means overdue — so
// High is amber and Medium the accent; Low is the default and gets nothing.
// The word is always there: colour alone fails in grey print and for
// colour-blind readers.
export function PriorityBadge({ priority }: { priority: number }) {
  if (priority >= 2)
    return (
      <span className="badge priority" data-priority="high">
        High
      </span>
    )
  if (priority === 1)
    return (
      <span className="badge priority" data-priority="medium">
        Medium
      </span>
    )
  return null
}
