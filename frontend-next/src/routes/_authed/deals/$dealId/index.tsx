import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { DealRead } from '../../../../api/types'
import { DocumentRows } from '../../../../components/DocumentRows'
import { InteractionList } from '../../../../components/InteractionList'
import { LostReasonDialog } from '../../../../components/LostReasonDialog'
import { Fact, Facts } from '../../../../components/RecordPage'
import { TaskList } from '../../../../components/TaskList'
import { Button } from '../../../../components/ui/Button'
import { Checkbox } from '../../../../components/ui/Checkbox'
import { ConfirmDialog } from '../../../../components/ui/ConfirmDialog'
import { Select } from '../../../../components/ui/Select'
import {
  dealQuery,
  dealValue,
  deleteDeal,
  invalidateDeals,
  isDecided,
  type Stage,
  stageLabel,
  stageOptions,
  stageTone,
} from '../../../../deals'
import { linkedDocumentsQuery } from '../../../../documents'
import { formatDateTime, formatDay, localDay } from '../../../../format'
import { linkedInteractionsQuery, useToggleHappened } from '../../../../interactions'
import { linkedTasksQuery, useToggleDone } from '../../../../tasks'
import { useMoveDeal } from '../../../../useMoveDeal'
import { useSelectedTabInView } from '../../../../useSelectedTabInView'

const tabs = ['tasks', 'interactions', 'documents'] as const
type TabId = (typeof tabs)[number]

const searchSchema = z.object({
  tab: z.enum(tabs).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/deals/$dealId/')({
  validateSearch: searchSchema,
  component: DealDetail,
})

function DealDetail() {
  const { api } = Route.useRouteContext()
  const { dealId } = Route.useParams()
  const { tab = 'tasks', ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const deal = useQuery(dealQuery(api, dealId))
  const [showDone, setShowDone] = useState(false)
  const tasks = useQuery(linkedTasksQuery(api, { deal_id: dealId }, showDone))
  const interactions = useQuery(linkedInteractionsQuery(api, { deal_id: dealId }))
  const documents = useQuery(linkedDocumentsQuery(api, { deal_id: dealId }))
  const taskToggle = useToggleDone(api)
  const happened = useToggleHappened(api)
  const mover = useMoveDeal(api)
  const [now] = useState(() => Date.now())
  const tabsRef = useSelectedTabInView(tab, deal.isSuccess)

  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useMutation({
    mutationFn: () => deleteDeal(api, dealId),
    onSuccess: async () => {
      await navigate({ to: '/deals', search: filters, replace: true })
      queryClient.removeQueries({ queryKey: dealQuery(api, dealId).queryKey })
      await invalidateDeals(queryClient)
    },
  })

  const back = (
    <Link to="/deals" search={filters} className="back-link">
      ← Deals
    </Link>
  )

  if (deal.isPending || deal.error) {
    return (
      <div className="page">
        {back}
        {deal.isPending ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="form-error">
            {deal.error instanceof ApiError && deal.error.status === 404
              ? 'This deal does not exist, or was deleted.'
              : deal.error.message}
          </p>
        )}
      </div>
    )
  }

  const d = deal.data
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
          <h1>{d.title}</h1>
          <p>
            <span className="badge" data-tone={stageTone(d.stage)}>
              {stageLabel(d.stage)}
            </span>
            {d.organization_id && (
              <>
                {' '}
                <Link to="/organizations/$organizationId" params={{ organizationId: d.organization_id }}>
                  {d.organization_name}
                </Link>
              </>
            )}
          </p>
        </div>
        <div className="header-actions">
          <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
            Delete
          </Button>
          <Link to="/deals/$dealId/edit" params={{ dealId }} search={filters} className="button button-quiet">
            Edit
          </Link>
        </div>
      </header>

      {mover.error && (
        <p className="form-error" role="alert">
          Could not move the deal: {mover.error.message}
        </p>
      )}

      <div className="profile">
        <DealFacts deal={d} onMove={(stage) => mover.move(d, stage)} moving={mover.pendingId === d.id} />

        <Tabs
          className="panel"
          selectedKey={tab}
          onSelectionChange={(key) => {
            const next = tabs.find((t) => t === key) ?? 'tasks'
            void navigate({ to: '.', search: { ...filters, tab: next === 'tasks' ? undefined : next }, replace: true })
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
              <Link to="/tasks/new" search={{ dealId, dealTitle: d.title }} className="button button-quiet">
                Add task
              </Link>
            </div>
            {taskToggle.repeated && (
              <p className="notice" role="status">
                Repeated: “{taskToggle.repeated.title}” is due again{' '}
                {formatDay(localDay(taskToggle.repeated.due))}.
              </p>
            )}
            {tasks.isPending ? (
              <p className="muted">Loading…</p>
            ) : tasks.error ? (
              <p className="form-error">{tasks.error.message}</p>
            ) : tasks.data.items.length === 0 ? (
              <p className="muted">{showDone ? 'No tasks about this deal.' : 'Nothing outstanding.'}</p>
            ) : (
              <TaskList
                tasks={tasks.data.items}
                onToggle={taskToggle.toggle}
                pendingId={taskToggle.pendingId}
                hideAbout="deal"
                now={now}
              />
            )}
          </TabPanel>

          <TabPanel id="interactions" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/interactions/new" search={{ dealId }} className="button button-quiet">
                Log interaction
              </Link>
            </div>
            {interactions.isPending ? (
              <p className="muted">Loading…</p>
            ) : interactions.error ? (
              <p className="form-error">{interactions.error.message}</p>
            ) : interactions.data.items.length === 0 ? (
              <p className="muted">Nothing logged here yet.</p>
            ) : (
              <InteractionList
                items={interactions.data.items}
                onToggle={happened.toggle}
                pendingId={happened.pendingId}
                now={now}
                compact
              />
            )}
          </TabPanel>

          <TabPanel id="documents" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/documents/new" search={{ dealId }} className="button button-quiet">
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
              <DocumentRows items={documents.data.items} />
            )}
          </TabPanel>
        </Tabs>
      </div>

      <LostReasonDialog deal={mover.askingWhy} onConfirm={mover.confirmLost} onCancel={mover.cancelLost} />

      <ConfirmDialog
        title="Delete this deal?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{d.title}</strong> will be permanently deleted. Its tasks, interactions and documents are kept.
        </p>
      </ConfirmDialog>
    </div>
  )
}

function DealFacts({ deal: d, onMove, moving }: { deal: DealRead; onMove: (stage: Stage) => void; moving: boolean }) {
  const { headline, detail } = dealValue(d)
  const decided = isDecided(d.stage)
  return (
    <Facts
      before={
        <div className="deal-head">
          <div className="deal-value">
            <span className="deal-headline">{headline ?? <span className="muted">No value yet</span>}</span>
            {detail && <span className="row-meta">{detail}</span>}
          </div>
          {/* The one move the pipeline is made of; Lost asks why first. */}
          <Select
            label={moving ? 'Stage (moving…)' : 'Stage'}
            options={stageOptions}
            value={d.stage}
            onChange={(v) => v && onMove(v)}
          />
        </div>
      }
    >
      {d.contact_id && (
        <Fact label="Contact">
          <Link to="/contacts/$contactId" params={{ contactId: d.contact_id }}>
            {d.contact_name}
          </Link>
        </Fact>
      )}
      {d.expected_close_date && (
        <Fact label={decided ? 'Was expected to close' : 'Expected close'}>{formatDay(d.expected_close_date)}</Fact>
      )}
      {d.closed_at && <Fact label="Decided">{formatDateTime(d.closed_at)}</Fact>}
      {d.probability != null && <Fact label="Probability">{d.probability}%</Fact>}
      {d.lost_reason && <Fact label="Lost because">{d.lost_reason}</Fact>}
      {d.notes && <Fact label="Notes">{d.notes}</Fact>}
    </Facts>
  )
}
