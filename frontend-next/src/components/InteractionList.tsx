import { Link } from '@tanstack/react-router'
import type { InteractionRead } from '../api/types'
import { formatDateTime } from '../format'
import { isOverdueInteraction, isPlanned, kindLabel } from '../interactions'
import { RecordName } from './LinksPicker'
import { Markdown } from './Markdown'
import { Button } from './ui/Button'

// Interactions as rows: what and when, who with, the notes, and the two things
// done to one from a list — mark it as happened, or turn it into a follow-up
// task. Used by the activity screen and every record page's tab.
export function InteractionList({
  items,
  onToggle,
  pendingId,
  now,
  compact,
  hideContacts,
}: {
  items: InteractionRead[]
  onToggle: (i: InteractionRead) => void
  pendingId?: string
  // Fixed by the caller when its page opens.
  now: number
  // On a record page's tab: no notes or tags, the row is a pointer.
  compact?: boolean
  // On a contact's page, "with Jane" on every row says nothing.
  hideContacts?: boolean
}) {
  return (
    <ul className="rows interaction-list">
      {items.map((i) => {
        const planned = isPlanned(i, now)
        const overdue = isOverdueInteraction(i, now)
        const firstContact = i.contact_ids[0]
        return (
          <li key={i.id} className="interaction-row" data-done={i.done || undefined}>
            <span className="row-main">
              <span>
                <span className="badge kind-badge" data-kind={i.kind}>
                  {kindLabel(i.kind)}
                </span>{' '}
                <Link
                  to="/interactions/$interactionId"
                  params={{ interactionId: i.id }}
                  className="row-link"
                >
                  {i.subject}
                </Link>
              </span>
              <span className="row-meta">
                <span className={overdue ? 'late' : undefined}>{formatDateTime(i.occurred_at)}</span>
                {i.duration_minutes ? ` · ${i.duration_minutes} min` : ''}
                {planned && !i.done && ' · planned'}
                {overdue && ' · not marked as happened'}
                {!hideContacts && i.contact_ids.length > 0 && (
                  <>
                    {' · with '}
                    {i.contact_ids.map((id, n) => (
                      <span key={id}>
                        {n > 0 && ', '}
                        <Link to="/contacts/$contactId" params={{ contactId: id }} className="row-link">
                          <RecordName kind="contact" id={id} />
                        </Link>
                      </span>
                    ))}
                  </>
                )}
              </span>
              {!compact && i.notes && (
                <div className="interaction-notes">
                  <Markdown>{i.notes}</Markdown>
                </div>
              )}
              {!compact && i.tags.length > 0 && (
                <span className="chips">
                  {i.tags.map((t) => (
                    <span key={t} className="badge">
                      {t}
                    </span>
                  ))}
                </span>
              )}
            </span>
            <span className="row-actions">
              <Link
                to="/tasks/new"
                search={{
                  interactionId: i.id,
                  interactionSubject: i.subject,
                  contactId: firstContact,
                }}
                className="button button-quiet"
              >
                Follow up
              </Link>
              {/* Only offered while it is still open; undoing it is rare
                  enough to live in the form's Happened box. */}
              {!i.done && (
                <Button variant="quiet" onPress={() => onToggle(i)} isDisabled={pendingId === i.id}>
                  Mark happened
                </Button>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
