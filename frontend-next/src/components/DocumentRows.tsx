import { Link } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'
import type { DocumentRead } from '../api/types'
import { formatBytes, formatDate } from '../format'
import { DocumentViewer } from './DocumentViewer'
import { Button } from './ui/Button'

// A record page's Documents tab: each file with a View button, its page one
// click away, and where else it is filed — a contract under the deal is often
// also under the organization.
export function DocumentRows({
  items,
  actions,
}: {
  items: DocumentRead[]
  // Extra buttons per row: Unlink, on a project.
  actions?: (doc: DocumentRead) => ReactNode
}) {
  const [viewing, setViewing] = useState<DocumentRead | null>(null)
  return (
    <>
      <ul className="rows">
        {items.map((d) => {
          const links = d.contact_ids.length + d.organization_ids.length + d.deal_ids.length + d.project_ids.length
          const elsewhere = links - 1
          return (
            <li key={d.id}>
              <span className="row-main">
                <Link to="/documents/$documentId" params={{ documentId: d.id }} className="row-link">
                  {d.title}
                </Link>
                <span className="row-meta">
                  {d.format === 'markdown' ? 'Markdown' : d.format.toUpperCase()} · {formatBytes(d.size)} ·{' '}
                  {formatDate(d.created_at)}
                  {elsewhere === 1 && ' · also filed elsewhere'}
                  {elsewhere > 1 && ` · also filed under ${elsewhere} others`}
                </span>
              </span>
              <span className="row-actions">
                <Button variant="quiet" onPress={() => setViewing(d)}>
                  View
                </Button>
                {actions?.(d)}
              </span>
            </li>
          )
        })}
      </ul>
      <DocumentViewer doc={viewing} onClose={() => setViewing(null)} />
    </>
  )
}
