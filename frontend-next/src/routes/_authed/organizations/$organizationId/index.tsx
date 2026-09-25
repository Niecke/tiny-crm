import { type UseQueryResult, useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { OrganizationRead } from '../../../../api/types'
import { Button } from '../../../../components/ui/Button'
import { formatBytes, formatDate, formatDateTime } from '../../../../format'
import { orgContactsQuery, orgDocumentsQuery, organizationQuery, orgInteractionsQuery } from '../../../../organizations'

const tabs = ['contacts', 'interactions', 'documents'] as const
type TabId = (typeof tabs)[number]

// The open tab is part of the URL, so a reload or a shared link lands on it.
// Contacts is the default and is left out of the URL.
const searchSchema = z.object({
  tab: z.enum(tabs).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/organizations/$organizationId/')({
  validateSearch: searchSchema,
  component: OrganizationDetail,
})

function OrganizationDetail() {
  const { api } = Route.useRouteContext()
  const { organizationId } = Route.useParams()
  const { q, tab = 'contacts' } = Route.useSearch()
  const navigate = Route.useNavigate()
  const org = useQuery(organizationQuery(api, organizationId))
  // All three load up front: each tab label shows its count, and switching
  // tabs should not wait on a request.
  const contacts = useQuery(orgContactsQuery(api, organizationId))
  const interactions = useQuery(orgInteractionsQuery(api, organizationId))
  const documents = useQuery(orgDocumentsQuery(api, organizationId))

  // Fixed when the page opens: whether an entry is still planned should not
  // flip on an unrelated re-render.
  const [now] = useState(() => Date.now())

  // On a phone the tab strip can be wider than the screen; a tab opened from a
  // link or a reload must not sit off to the side.
  const tabsRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    tabsRef.current
      ?.querySelector('[aria-selected="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [tab, org.isSuccess])

  if (org.isPending || org.error) {
    return (
      <div className="page">
        <Link to="/organizations" search={{ q }} className="back-link">
          ← Organizations
        </Link>
        {org.isPending ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="form-error">
            {org.error instanceof ApiError && org.error.status === 404
              ? 'This organization does not exist, or was deleted.'
              : org.error.message}
          </p>
        )}
      </div>
    )
  }

  const o = org.data
  const counts: Record<TabId, number | undefined> = {
    contacts: contacts.data?.total,
    interactions: interactions.data?.total,
    documents: documents.data?.total,
  }

  return (
    <div className="page">
      <Link to="/organizations" search={{ q }} className="back-link">
        ← Organizations
      </Link>

      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>{o.name}</h1>
          {(o.industry || o.domain) && <p>{[o.industry, o.domain].filter(Boolean).join(' · ')}</p>}
        </div>
        <Link
          to="/organizations/$organizationId/edit"
          params={{ organizationId }}
          search={{ q }}
          className="button button-quiet"
        >
          Edit
        </Link>
      </header>

      <div className="profile">
        <Facts org={o} />

        {/* React Aria's Tabs: arrow keys move between tabs, and the tablist /
            tabpanel roles and their links are set up for screen readers. The
            selection is the ?tab= search param, so it survives a reload. */}
        <Tabs
          className="panel"
          selectedKey={tab}
          onSelectionChange={(key) => {
            const next = tabs.find((t) => t === key) ?? 'contacts'
            void navigate({ search: { q, tab: next === 'contacts' ? undefined : next }, replace: true })
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

          <TabPanel id="contacts" className="panel-body">
            <AddNotReady label="Add contact" />
            <Rows query={contacts} empty="No contacts at this organization.">
              {(c) => (
                <li key={c.id}>
                  <span className="row-main">
                    <span>{c.name}</span>
                    {c.job_title && <span className="row-meta">{c.job_title}</span>}
                  </span>
                  {c.email && (
                    <a className="row-side" href={`mailto:${c.email}`}>
                      {c.email}
                    </a>
                  )}
                </li>
              )}
            </Rows>
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
            <Rows query={documents} empty="No documents filed here.">
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
    </div>
  )
}

// The action each tab will get. Shown disabled until the forms exist, so the
// screen already has the shape it will keep and nobody goes looking elsewhere.
// Only the selected TabPanel is rendered, so the id is unique on the page.
function AddNotReady({ label }: { label: string }) {
  return (
    <div className="tab-toolbar">
      <span className="muted small" id="add-not-ready">
        Not available in the React preview yet — use the current app for now.
      </span>
      <Button variant="quiet" isDisabled aria-describedby="add-not-ready">
        {label}
      </Button>
    </div>
  )
}

// Label above value: the column is narrow, so the eye reads straight down
// instead of jumping across a wide row from label to value.
function Facts({ org }: { org: OrganizationRead }) {
  const { domain, email, phone, address, notes } = org
  // Stored as a bare domain, but an older record may hold a full URL. Only
  // http(s) is passed through, so the field cannot become a javascript: link.
  const website = domain && (/^https?:\/\//i.test(domain) ? domain : `https://${domain}`)

  return (
    <aside className="panel facts" aria-label="Details">
      {!website && !email && !phone && !address && !notes ? (
        <p className="muted small">No details yet.</p>
      ) : (
        <dl>
          {website && (
            <Fact label="Website">
              <a href={website} target="_blank" rel="noreferrer">
                {domain}
              </a>
            </Fact>
          )}
          {email && (
            <Fact label="Email">
              <a href={`mailto:${email}`}>{email}</a>
            </Fact>
          )}
          {phone && (
            <Fact label="Phone">
              <a href={`tel:${phone}`}>{phone}</a>
            </Fact>
          )}
          {address && <Fact label="Address">{address}</Fact>}
          {notes && <Fact label="Notes">{notes}</Fact>}
        </dl>
      )}
    </aside>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// The first page of one linked record type, and a line saying how many are
// not shown.
function Rows<T>({
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
