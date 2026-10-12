import { Link } from '@tanstack/react-router'
import { Checkbox } from 'react-aria-components'
import type { TimelineItemRead } from '../api/types'
import { formatBytes, formatDateTime, formatDay, localDay } from '../format'
import { kindLabel } from '../interactions'
import { formatMoney, stageLabel, stageTone } from '../deals'
import { Markdown } from './Markdown'
import { PriorityBadge } from './PriorityBadge'
import { Button } from './ui/Button'

export function TimelineFeed({
  items,
  onToggleTask,
  onToggleInteraction,
  pendingId,
}: {
  items: TimelineItemRead[]
  onToggleTask?: (taskId: string, currentDone: boolean) => void
  onToggleInteraction?: (interactionId: string, currentDone: boolean) => void
  pendingId?: string
}) {
  if (items.length === 0) {
    return <p className="muted">No history yet.</p>
  }

  return (
    <ul className="rows timeline-list">
      {items.map((item) => {
        const meta = (item.metadata || {}) as Record<string, unknown>
        const tags = Array.isArray(meta.tags) ? (meta.tags as string[]) : []

        return (
          <li key={`${item.item_type}-${item.id}`} className="timeline-row">
            <span className="row-main">
              <span className="timeline-header">
                {renderTypeBadge(item)}
                {renderTitle(item, meta, onToggleTask, pendingId)}
              </span>

              <span className="row-meta">
                <span>{formatDateTime(item.timestamp)}</span>
                {renderMeta(item, meta)}
              </span>

              {item.description && (
                <div className="timeline-notes interaction-notes">
                  <Markdown>{item.description}</Markdown>
                </div>
              )}

              {item.item_type === 'change' && renderChanges(meta.changes)}

              {tags.length > 0 && (
                <span className="chips">
                  {tags.map((t) => (
                    <span key={t} className="badge">
                      {t}
                    </span>
                  ))}
                </span>
              )}
            </span>

            <span className="row-actions">
              {item.item_type === 'interaction' && !meta.done && onToggleInteraction && (
                <Button
                  variant="quiet"
                  onPress={() => onToggleInteraction(item.id, Boolean(meta.done))}
                  isDisabled={pendingId === item.id}
                >
                  Mark happened
                </Button>
              )}
              {item.item_type === 'document' && (
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: item.id }}
                  className="button button-quiet"
                >
                  View
                </Link>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function renderTypeBadge(item: TimelineItemRead) {
  const meta = item.metadata || {}
  switch (item.item_type) {
    case 'interaction': {
      const kind = typeof meta.kind === 'string' ? meta.kind : 'note'
      return (
        <span className="badge kind-badge" data-kind={kind}>
          {kindLabel(kind)}
        </span>
      )
    }
    case 'task':
      return (
        <span className="badge" data-tone={meta.done ? 'success' : undefined}>
          Task
        </span>
      )
    case 'deal': {
      const stage = typeof meta.stage === 'string' ? meta.stage : 'lead'
      return (
        <span className="badge" data-tone={stageTone(stage)}>
          {stageLabel(stage)}
        </span>
      )
    }
    case 'document': {
      const fmt = typeof meta.format === 'string' ? meta.format.toUpperCase() : 'DOC'
      return <span className="badge">{fmt}</span>
    }
    case 'change':
      return (
        <span className="badge">
          Audit
        </span>
      )
    default:
      return null
  }
}

function renderTitle(
  item: TimelineItemRead,
  meta: Record<string, unknown>,
  onToggleTask?: (taskId: string, currentDone: boolean) => void,
  pendingId?: string,
) {
  switch (item.item_type) {
    case 'interaction':
      return (
        <Link
          to="/interactions/$interactionId"
          params={{ interactionId: item.id }}
          className="row-link"
        >
          {item.title}
        </Link>
      )
    case 'task':
      return (
        <span className="task-title-wrap">
          <Checkbox
            className="checkbox task-check"
            isSelected={Boolean(meta.done)}
            isDisabled={pendingId === item.id}
            onChange={() => onToggleTask?.(item.id, Boolean(meta.done))}
            aria-label={meta.done ? `Mark “${item.title}” as not done` : `Mark “${item.title}” as done`}
          >
            <span className="checkbox-box" aria-hidden="true">
              ✓
            </span>
          </Checkbox>
          <Link to="/tasks/$taskId" params={{ taskId: item.id }} className="row-link task-title">
            {item.title}
          </Link>
        </span>
      )
    case 'deal':
      return (
        <Link to="/deals/$dealId" params={{ dealId: item.id }} className="row-link">
          {item.title}
        </Link>
      )
    case 'document':
      return (
        <Link
          to="/documents/$documentId"
          params={{ documentId: item.id }}
          className="row-link"
        >
          {item.title}
        </Link>
      )
    case 'change':
      return <span className="timeline-audit-title">{item.title}</span>
    default:
      return <span>{item.title}</span>
  }
}

function renderMeta(item: TimelineItemRead, meta: Record<string, unknown>) {
  switch (item.item_type) {
    case 'interaction': {
      const dur = typeof meta.duration_minutes === 'number' ? ` · ${meta.duration_minutes} min` : ''
      const status = meta.done ? ' · happened' : ' · planned'
      return <>{dur}{status}</>
    }
    case 'task': {
      const priority = typeof meta.priority === 'number' ? meta.priority : 0
      const due =
        typeof meta.due_date === 'string' ? ` · Due ${formatDay(localDay(meta.due_date))}` : ''
      return (
        <>
          {due}
          {priority > 0 && (
            <span>
              {' · '}<PriorityBadge priority={priority} />
            </span>
          )}
        </>
      )
    }
    case 'deal': {
      const currency = typeof meta.currency === 'string' ? meta.currency : 'EUR'
      const val =
        meta.expected_value !== null && meta.expected_value !== undefined
          ? ` · ${formatMoney(String(meta.expected_value), currency)}`
          : ''
      const prob =
        typeof meta.probability === 'number' ? ` · ${meta.probability}%` : ''
      return <>{val}{prob}</>
    }
    case 'document': {
      const size = typeof meta.size === 'number' ? ` · ${formatBytes(meta.size)}` : ''
      return <>{size}</>
    }
    default:
      return null
  }
}

function renderChanges(rawChanges: unknown) {
  if (!rawChanges || typeof rawChanges !== 'object') return null
  const changes = rawChanges as Record<string, { old: unknown; new: unknown }>
  const entries = Object.entries(changes)
  if (entries.length === 0) return null

  return (
    <div className="timeline-changes">
      {entries.map(([field, diff]) => (
        <div key={field} className="timeline-change-field small muted">
          <span className="change-field-name">{field.replace(/_/g, ' ')}</span>:{' '}
          {diff.old !== null && diff.old !== undefined ? (
            <>
              <del>{String(diff.old)}</del> → <strong>{String(diff.new)}</strong>
            </>
          ) : (
            <span>
              set to <strong>{String(diff.new)}</strong>
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
