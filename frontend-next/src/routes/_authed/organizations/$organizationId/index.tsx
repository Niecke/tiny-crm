import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { OrganizationRead } from '../../../../api/types'
import { AddNotReady, Fact, Facts, Rows } from '../../../../components/RecordPage'
import { useSelectedTabInView } from '../../../../useSelectedTabInView'
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

  const tabsRef = useSelectedTabInView(tab, org.isSuccess)

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
        <OrgFacts org={o} />

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
            <div className="tab-toolbar">
              <Link
                to="/contacts/new"
                search={{ organizationId, organizationName: o.name }}
                className="button button-quiet"
              >
                Add contact
              </Link>
            </div>
            <Rows query={contacts} empty="No contacts at this organization.">
              {(c) => (
                <li key={c.id}>
                  <span className="row-main">
                    <Link to="/contacts/$contactId" params={{ contactId: c.id }} className="row-link">
                      {c.name}
                    </Link>
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

// Only http(s) is passed through, so the field cannot become a javascript: link.
function OrgFacts({ org }: { org: OrganizationRead }) {
  const { domain, email, phone, address, notes } = org
  // Stored as a bare domain, but an older record may hold a full URL.
  const website = domain && (/^https?:\/\//i.test(domain) ? domain : `https://${domain}`)

  return (
    <Facts>
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
    </Facts>
  )
}
