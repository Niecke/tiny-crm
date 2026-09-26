import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { ContactRead } from '../../../../api/types'
import { AddNotReady, Fact, Facts, Rows } from '../../../../components/RecordPage'
import { useSelectedTabInView } from '../../../../useSelectedTabInView'
import { Button } from '../../../../components/ui/Button'
import { ConfirmDialog } from '../../../../components/ui/ConfirmDialog'
import {
  contactDocumentsQuery,
  contactInteractionsQuery,
  contactQuery,
  deleteContact,
  freelancerAnswer,
  invalidateContacts,
  labelOf,
  lifecycleOptions,
  relationOptions,
  sourceOptions,
} from '../../../../contacts'
import { formatBytes, formatDate, formatDateTime, formatDay, localDay } from '../../../../format'
import { linkedTasksQuery, useToggleDone } from '../../../../tasks'
import { TaskList } from '../../../../components/TaskList'
import { Checkbox } from '../../../../components/ui/Checkbox'

const tabs = ['tasks', 'interactions', 'documents'] as const
type TabId = (typeof tabs)[number]

// The open tab is part of the URL; Tasks is the default and is left out.
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
  const { tab = 'tasks', ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const contact = useQuery(contactQuery(api, contactId))
  // All three load up front: each tab label shows its count.
  const [showDone, setShowDone] = useState(false)
  const tasks = useQuery(linkedTasksQuery(api, { contact_id: contactId }, showDone))
  const { toggle, pendingId, error: toggleError, repeated } = useToggleDone(api)
  const interactions = useQuery(contactInteractionsQuery(api, contactId))
  const documents = useQuery(contactDocumentsQuery(api, contactId))
  const [now] = useState(() => Date.now())
  const tabsRef = useSelectedTabInView(tab, contact.isSuccess)

  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useMutation({
    mutationFn: () => deleteContact(api, contactId),
    onSuccess: async () => {
      await navigate({ to: '/contacts', search: filters, replace: true })
      queryClient.removeQueries({ queryKey: contactQuery(api, contactId).queryKey })
      await invalidateContacts(queryClient)
    },
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
    tasks: tasks.data?.total,
    interactions: interactions.data?.total,
    documents: documents.data?.total,
  }

  return (
    <div className="page">
      {back}

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
        <div className="header-actions">
          <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
            Delete
          </Button>
          <Link
            to="/contacts/$contactId/edit"
            params={{ contactId }}
            search={filters}
            className="button button-quiet"
          >
            Edit
          </Link>
        </div>
      </header>

      <div className="profile">
        <ContactFacts contact={c} />

        <Tabs
          className="panel"
          selectedKey={tab}
          onSelectionChange={(key) => {
            const next = tabs.find((t) => t === key) ?? 'tasks'
            void navigate({
              to: '.',
              search: { ...filters, tab: next === 'tasks' ? undefined : next },
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
            <AddNotReady label="Log interaction" />
            <Rows query={interactions} empty="Nothing logged yet.">
              {(i) => (
                <li key={i.id}>
                  <span className="row-main">
                    <span>{i.subject}</span>
                    <span className="row-meta">
                      {i.kind} · {formatDateTime(i.occurred_at)}
                    </span>
                  </span>
                  {Date.parse(i.occurred_at) > now && <span className="badge">planned</span>}
                </li>
              )}
            </Rows>
          </TabPanel>

          <TabPanel id="documents" className="panel-body">
            <AddNotReady label="Upload document" />
            <Rows query={documents} empty="Nothing filed here yet.">
              {(d) => (
                <li key={d.id}>
                  <span className="row-main">
                    <span>{d.title}</span>
                    <span className="row-meta">
                      {d.format.toUpperCase()} · {formatBytes(d.size)}
                    </span>
                  </span>
                  <span className="row-side muted">{formatDate(d.created_at)}</span>
                </li>
              )}
            </Rows>
          </TabPanel>
        </Tabs>
      </div>

      <ConfirmDialog
        title="Delete this contact?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{c.name}</strong> will be permanently deleted.
        </p>
      </ConfirmDialog>
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
