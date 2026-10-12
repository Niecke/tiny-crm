import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { ContactRead, InteractionRead, TaskRead, TimelineItemType } from '../../../../api/types'
import { ArchiveButton, ArchivedNotice } from '../../../../components/Archive'
import { useArchive } from '../../../../useArchive'
import { Fact, Facts } from '../../../../components/RecordPage'
import { useSelectedTabInView } from '../../../../useSelectedTabInView'
import {
  archiveContact,
  contactQuery,
  contactTimelineQuery,
  deleteContact,
  exportContactVcard,
  freelancerAnswer,
  labelOf,
  lifecycleOptions,
  relationOptions,
  restoreContact,
  sourceOptions,
} from '../../../../contacts'
import { formatDay, localDay } from '../../../../format'
import { linkedDealsQuery, stageLabel, stageTone, valueSummary } from '../../../../deals'
import { linkedTasksQuery, useToggleDone } from '../../../../tasks'
import { TaskList } from '../../../../components/TaskList'
import { TimelineFeed } from '../../../../components/TimelineFeed'
import { Button } from '../../../../components/ui/Button'
import { Checkbox } from '../../../../components/ui/Checkbox'
import { Segmented } from '../../../../components/ui/Segmented'
import { DocumentRows } from '../../../../components/DocumentRows'
import { linkedDocumentsQuery } from '../../../../documents'
import { InteractionList } from '../../../../components/InteractionList'
import { linkedInteractionsQuery, useToggleHappened } from '../../../../interactions'

const tabs = ['timeline', 'tasks', 'interactions', 'deals', 'documents'] as const
type TabId = (typeof tabs)[number]

// The open tab is part of the URL; Timeline is the default and is left out.
const searchSchema = z.object({
  tab: z.enum(tabs).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/contacts/$contactId/')({
  validateSearch: searchSchema,
  component: ContactDetail,
})

function ContactDetail() {
  const { api } = Route.useRouteContext()
  const { contactId } = Route.useParams()
  const { tab = 'timeline', ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const contact = useQuery(contactQuery(api, contactId))
  const [timelineType, setTimelineType] = useState<string>('all')
  const timelineFilter =
    timelineType === 'all' ? undefined : { types: [timelineType as TimelineItemType] }
  const timeline = useQuery(contactTimelineQuery(api, contactId, timelineFilter))
  const [showDone, setShowDone] = useState(false)
  const tasks = useQuery(linkedTasksQuery(api, { contact_id: contactId }, showDone))
  const { toggle, pendingId, error: toggleError, repeated } = useToggleDone(api)
  const interactions = useQuery(linkedInteractionsQuery(api, { contact_id: contactId }))
  const { toggle: toggleInteraction, pendingId: pendingInteraction, error: toggleInteractionError } = useToggleHappened(api)
  const deals = useQuery(linkedDealsQuery(api, { contact_id: contactId }))
  const documents = useQuery(linkedDocumentsQuery(api, { contact_id: contactId }))
  const [now] = useState(() => Date.now())
  const tabsRef = useSelectedTabInView(tab, contact.isSuccess)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleExport = async (name: string) => {
    setExportError(null)
    try {
      await exportContactVcard(api, contactId, `${name}.vcf`)
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  const archiving = useArchive({
    queryKey: contactQuery(api, contactId).queryKey,
    archive: () => archiveContact(api, contactId),
    restore: () => restoreContact(api, contactId),
    remove: () => deleteContact(api, contactId),
    leave: () => navigate({ to: '/contacts', search: filters, replace: true }),
  })

  const back = (
    <Link to="/contacts" search={filters} className="back-link">
      ← Contacts
    </Link>
  )

  if (contact.isPending || contact.error) {
    return (
      <div className="page">
        {back}
        {contact.isPending ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="form-error">
            {contact.error instanceof ApiError && contact.error.status === 404
              ? 'This contact does not exist, or was deleted.'
              : contact.error.message}
          </p>
        )}
      </div>
    )
  }

  const c = contact.data
  const counts: Record<TabId, number | undefined> = {
    timeline: timeline.data?.total,
    tasks: tasks.data?.total,
    interactions: interactions.data?.total,
    deals: deals.data?.total,
    documents: documents.data?.total,
  }

  return (
    <div className="page">
      {back}

      <ArchivedNotice record={c} noun="contact" name={c.name} archiving={archiving}>
        Their tasks, deals, interactions and documents are kept, with no contact on them.
      </ArchivedNotice>

      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>{c.name}</h1>
          {(c.job_title || c.organization_id) && (
            <p>
              {c.job_title}
              {c.job_title && c.organization_id && ' · '}
              {c.organization_id && (
                <Link to="/organizations/$organizationId" params={{ organizationId: c.organization_id }}>
                  {c.organization_name}
                </Link>
              )}
            </p>
          )}
        </div>
        {!c.archived_at && (
          <div className="header-actions">
            <Button
              variant="quiet"
              onPress={() => void handleExport(c.name)}
            >
              Export vCard
            </Button>
            <ArchiveButton archiving={archiving} />
            <Link
              to="/contacts/$contactId/edit"
              params={{ contactId }}
              search={filters}
              className="button button-quiet"
            >
              Edit
            </Link>
          </div>
        )}
      </header>

      {exportError && <p className="form-error">{exportError}</p>}

      <div className="profile">
        <ContactFacts contact={c} />

        <Tabs
          className="panel"
          selectedKey={tab}
          onSelectionChange={(key) => {
            const next = tabs.find((t) => t === key) ?? 'timeline'
            void navigate({
              to: '.',
              search: { ...filters, tab: next === 'timeline' ? undefined : next },
              replace: true,
            })
          }}
        >
          <TabList className="tabs" aria-label="Linked records" ref={tabsRef}>
            {tabs.map((t) => (
              <Tab key={t} id={t} className="tab">
                {t[0].toUpperCase() + t.slice(1)}
                {counts[t] !== undefined && <span className="tab-count">{counts[t]}</span>}
              </Tab>
            ))}
          </TabList>

          <TabPanel id="timeline" className="panel-body">
            <div className="tab-toolbar">
              <Segmented
                label="Filter timeline"
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'interaction', label: 'Interactions' },
                  { value: 'task', label: 'Tasks' },
                  { value: 'deal', label: 'Deals' },
                  { value: 'document', label: 'Documents' },
                  { value: 'change', label: 'Changes' },
                ]}
                value={timelineType}
                onChange={setTimelineType}
              />
              <Link to="/interactions/new" search={{ contactId }} className="button button-quiet">
                Log interaction
              </Link>
              <Link
                to="/tasks/new"
                search={{ contactId, contactName: c.name }}
                className="button button-quiet"
              >
                Add task
              </Link>
            </div>
            {toggleError && (
              <p className="form-error" role="alert">
                Could not update the task: {toggleError.message}
              </p>
            )}
            {toggleInteractionError && (
              <p className="form-error" role="alert">
                Could not update the interaction: {toggleInteractionError.message}
              </p>
            )}
            {timeline.isPending ? (
              <p className="muted">Loading…</p>
            ) : timeline.error ? (
              <p className="form-error">{timeline.error.message}</p>
            ) : (
              <>
                <TimelineFeed
                  items={timeline.data.items}
                  onToggleTask={(taskId, currentDone) => {
                    toggle({ id: taskId, done: currentDone } as TaskRead)
                  }}
                  onToggleInteraction={(interactionId, currentDone) => {
                    toggleInteraction({ id: interactionId, done: currentDone } as InteractionRead)
                  }}
                  pendingId={pendingId || pendingInteraction}
                />
                {timeline.data.total > timeline.data.items.length && (
                  <p className="muted small">
                    {timeline.data.total - timeline.data.items.length} older not shown.
                  </p>
                )}
              </>
            )}
          </TabPanel>

          <TabPanel id="tasks" className="panel-body">
            <div className="tab-toolbar">
              <Checkbox isSelected={showDone} onChange={setShowDone}>
                Show done
              </Checkbox>
              <Link
                to="/tasks/new"
                search={{ contactId, contactName: c.name }}
                className="button button-quiet"
              >
                Add task
              </Link>
            </div>
            {repeated && (
              <p className="notice" role="status">
                Repeated: “{repeated.title}” is due again {formatDay(localDay(repeated.due))}.
              </p>
            )}
            {toggleError && (
              <p className="form-error" role="alert">
                Could not update the task: {toggleError.message}
              </p>
            )}
            {tasks.isPending ? (
              <p className="muted">Loading…</p>
            ) : tasks.error ? (
              <p className="form-error">{tasks.error.message}</p>
            ) : tasks.data.items.length === 0 ? (
              <p className="muted">{showDone ? 'No tasks about this contact.' : 'Nothing outstanding.'}</p>
            ) : (
              <TaskList tasks={tasks.data.items} onToggle={toggle} pendingId={pendingId} hideAbout="contact" now={now} />
            )}
          </TabPanel>

          <TabPanel id="interactions" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/interactions/new" search={{ contactId }} className="button button-quiet">
                Log interaction
              </Link>
            </div>
            {toggleInteractionError && (
              <p className="form-error" role="alert">
                Could not update the interaction: {toggleInteractionError.message}
              </p>
            )}
            {interactions.isPending ? (
              <p className="muted">Loading…</p>
            ) : interactions.error ? (
              <p className="form-error">{interactions.error.message}</p>
            ) : interactions.data.items.length === 0 ? (
              <p className="muted">Nothing logged yet.</p>
            ) : (
              <>
                <InteractionList
                  items={interactions.data.items}
                  onToggle={toggleInteraction}
                  pendingId={pendingInteraction}
                  now={now}
                  compact
                  hideContacts
                />
                {interactions.data.total > interactions.data.items.length && (
                  <p className="muted small">
                    {interactions.data.total - interactions.data.items.length} older not shown.
                  </p>
                )}
              </>
            )}
          </TabPanel>

          <TabPanel id="deals" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/deals/new" className="button button-quiet">
                New deal
              </Link>
            </div>
            {deals.isPending ? (
              <p className="muted">Loading…</p>
            ) : deals.error ? (
              <p className="form-error">{deals.error.message}</p>
            ) : deals.data.items.length === 0 ? (
              <p className="muted">No deals with this contact.</p>
            ) : (
              <ul className="rows">
                {deals.data.items.map((d) => (
                  <li
                    key={d.id}
                    className="deal-row"
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <span className="row-main">
                      <Link to="/deals/$dealId" params={{ dealId: d.id }} className="row-link">
                        {d.title}
                      </Link>
                      <span className="row-meta">
                        {valueSummary(d) ?? '—'}
                        {d.expected_close_date ? ` · Expected close ${formatDay(d.expected_close_date)}` : ''}
                      </span>
                    </span>
                    <span className="badge" data-tone={stageTone(d.stage)}>
                      {stageLabel(d.stage)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </TabPanel>

          <TabPanel id="documents" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/documents/new" search={{ contactId }} className="button button-quiet">
                Upload document
              </Link>
            </div>
            {documents.isPending ? (
              <p className="muted">Loading…</p>
            ) : documents.error ? (
              <p className="form-error">{documents.error.message}</p>
            ) : documents.data.items.length === 0 ? (
              <p className="muted">Nothing filed here yet.</p>
            ) : (
              <>
                <DocumentRows items={documents.data.items} />
                {documents.data.total > documents.data.items.length && (
                  <p className="muted small">{documents.data.total - documents.data.items.length} more not shown.</p>
                )}
              </>
            )}
          </TabPanel>
        </Tabs>
      </div>
    </div>
  )
}

// Only http(s) is passed through, so the field cannot become a javascript: link.
const safeUrl = (url: string) => (/^https?:\/\//i.test(url) ? url : `https://${url}`)

function ContactFacts({ contact: c }: { contact: ContactRead }) {
  const freelancers = freelancerAnswer(c.works_with_freelancers)
  const address = [c.street, [c.postal_code, c.city].filter(Boolean).join(' '), c.country]
    .filter(Boolean)
    .join('\n')

  return (
    <Facts
      before={
        // Status, type and the freelancer answer come first: they are read
        // before anything else.
        <div className="chips">
          {c.lifecycle_status && (
            <span className="badge" data-tone="accent">
              {labelOf(lifecycleOptions, c.lifecycle_status)}
            </span>
          )}
          {c.relation_type && <span className="badge">{labelOf(relationOptions, c.relation_type)}</span>}
          <span className="badge" data-tone={freelancers.tone}>
            {freelancers.label}
          </span>
        </div>
      }
    >
      {c.email && (
        <Fact label="Email">
          <a href={`mailto:${c.email}`}>{c.email}</a>
        </Fact>
      )}
      {c.email_secondary && (
        <Fact label="Second email">
          <a href={`mailto:${c.email_secondary}`}>{c.email_secondary}</a>
        </Fact>
      )}
      {c.phone && (
        <Fact label="Phone">
          <a href={`tel:${c.phone}`}>{c.phone}</a>
        </Fact>
      )}
      {c.phone_secondary && (
        <Fact label="Second phone">
          <a href={`tel:${c.phone_secondary}`}>{c.phone_secondary}</a>
        </Fact>
      )}
      {c.website && (
        <Fact label="Website">
          <a href={safeUrl(c.website)} target="_blank" rel="noreferrer">
            {c.website}
          </a>
        </Fact>
      )}
      {address && <Fact label="Address">{address}</Fact>}
      {c.known_day_rate && (
        <Fact label="Known day rate">
          {c.known_day_rate} {c.rate_currency}
        </Fact>
      )}
      {c.source && <Fact label="Source">{labelOf(sourceOptions, c.source)}</Fact>}
      {c.preferred_language && <Fact label="Preferred language">{c.preferred_language}</Fact>}
      {c.birthday && <Fact label="Birthday">{formatDay(c.birthday)}</Fact>}
      {c.tags.length > 0 && (
        <Fact label="Tags">
          <span className="chips">
            {c.tags.map((t) => (
              <span key={t} className="badge">
                {t}
              </span>
            ))}
          </span>
        </Fact>
      )}
      {c.notes && <Fact label="Notes">{c.notes}</Fact>}
    </Facts>
  )
}
