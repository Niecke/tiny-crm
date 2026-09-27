import { Link } from '@tanstack/react-router'
import { Checkbox } from 'react-aria-components'
import type { TaskRead } from '../api/types'
import { formatDay, localDay } from '../format'
import { isOverdue, recurrenceLabel } from '../tasks'
import { PriorityBadge } from './PriorityBadge'

// Tasks as rows: a tick box, the title (to the task's page), when it is due
// and what it is about, and its priority. Used by the task list and by every
// record page's Tasks tab, so the surfaces cannot drift apart (#137).
export function TaskList({
  tasks,
  onToggle,
  pendingId,
  hideAbout,
  now,
}: {
  tasks: TaskRead[]
  onToggle: (task: TaskRead) => void
  pendingId?: string
  // On a contact's page, "about Jane" on every row says nothing.
  hideAbout?: 'contact' | 'deal'
  // Fixed by the caller when its page opens, so a row does not turn late on
  // an unrelated re-render.
  now: number
}) {
  return (
    <ul className="rows task-list">
      {tasks.map((t) => {
        const late = isOverdue(t, now)
        const about = [hideAbout !== 'contact' && t.contact_name, hideAbout !== 'deal' && t.deal_title]
          .filter(Boolean)
          .join(' · ')
        const repeats = recurrenceLabel(t, (iso) => formatDay(localDay(iso)))
        return (
          <li key={t.id} className="task-row" data-priority={priorityName(t.priority)} data-done={t.done || undefined}>
            <Checkbox
              className="checkbox task-check"
              isSelected={t.done}
              isDisabled={pendingId === t.id}
              onChange={() => onToggle(t)}
              aria-label={t.done ? `Mark “${t.title}” as not done` : `Mark “${t.title}” as done`}
            >
              <span className="checkbox-box" aria-hidden="true">
                ✓
              </span>
            </Checkbox>
            <span className="row-main">
              <Link to="/tasks/$taskId" params={{ taskId: t.id }} className="row-link task-title">
                {t.title}
              </Link>
              {(t.due_date || repeats || about) && (
                <span className="row-meta">
                  {t.due_date && (
                    <span className={late ? 'late' : undefined}>
                      {late ? 'Was due' : 'Due'} {formatDay(localDay(t.due_date))}
                    </span>
                  )}
                  {[repeats, about]
                    .filter(Boolean)
                    .map((part) => (
                      <span key={part as string}> · {part}</span>
                    ))}
                </span>
              )}
            </span>
            <PriorityBadge priority={t.priority} />
          </li>
        )
      })}
    </ul>
  )
}

const priorityName = (p: number) => (p >= 2 ? 'high' : p === 1 ? 'medium' : undefined)
