import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { z } from 'zod'
import { ApiError } from '../../../../api/client'
import type { ProjectRead, ProjectUpdate, TaskRead } from '../../../../api/types'
import { AddLinkPicker } from '../../../../components/AddLinkPicker'
import { DocumentRows } from '../../../../components/DocumentRows'
import { InteractionList } from '../../../../components/InteractionList'
import { Markdown } from '../../../../components/Markdown'
import { Fact, Facts } from '../../../../components/RecordPage'
import { TaskList } from '../../../../components/TaskList'
import { Button } from '../../../../components/ui/Button'
import { Checkbox } from '../../../../components/ui/Checkbox'
import { ConfirmDialog } from '../../../../components/ui/ConfirmDialog'
import { DatePicker } from '../../../../components/ui/DatePicker'
import { Modal } from '../../../../components/ui/Modal'
import { TextField } from '../../../../components/ui/TextField'
import { contactQuery } from '../../../../contacts'
import { linkedDocumentsQuery } from '../../../../documents'
import { endOfLocalDay, formatDay, localDay } from '../../../../format'
import { linkedInteractionsQuery, useToggleHappened } from '../../../../interactions'
import { deleteProject, invalidateProjects, projectQuery, statusLabels, statusOf, updateProject } from '../../../../projects'
import { createTask, invalidateTasks, taskQuery, useToggleDone } from '../../../../tasks'
import { useSelectedTabInView } from '../../../../useSelectedTabInView'

const tabs = ['tasks', 'contacts', 'documents', 'interactions'] as const
type TabId = (typeof tabs)[number]

const searchSchema = z.object({
  tab: z.enum(tabs).optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/projects/$projectId/')({
  validateSearch: searchSchema,
  component: ProjectDetail,
})

// A project's page (#49): what it is, and what belongs to it as lists — tasks
// ticked off in place with done ones hidden until asked for, contacts and
// documents opened, linked or unlinked from here.
function ProjectDetail() {
  const { api } = Route.useRouteContext()
  const { projectId } = Route.useParams()
  const { tab = 'tasks', ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const project = useQuery(projectQuery(api, projectId))
  const p = project.data
  const tabsRef = useSelectedTabInView(tab, project.isSuccess)
  const [now] = useState(() => Date.now())

  // Linked tasks and contacts come back from the project as ids only; each is
  // loaded by id (and shared with the rest of the app through the cache).
  const taskResults = useQueries({ queries: (p?.task_ids ?? []).map((id) => taskQuery(api, id)) })
  const contactResults = useQueries({ queries: (p?.contact_ids ?? []).map((id) => contactQuery(api, id)) })
  const documents = useQuery(linkedDocumentsQuery(api, { project_id: projectId }))
  const interactions = useQuery(linkedInteractionsQuery(api, { project_id: projectId }))
  const [showDone, setShowDone] = useState(false)
  const taskToggle = useToggleDone(api)
  const happened = useToggleHappened(api)

  // Linking and unlinking send the whole list, as the API wants.
  const link = useMutation({
    mutationFn: (body: ProjectUpdate) => updateProject(api, projectId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(projectQuery(api, projectId).queryKey, saved)
      await invalidateProjects(queryClient)
    },
  })

  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useMutation({
    mutationFn: () => deleteProject(api, projectId),
    onSuccess: async () => {
      await navigate({ to: '/projects', search: filters, replace: true })
      queryClient.removeQueries({ queryKey: projectQuery(api, projectId).queryKey })
      await invalidateProjects(queryClient)
    },
  })

  const back = (
    <Link to="/projects" search={filters} className="back-link">
      ← Projects
    </Link>
  )

  if (project.isPending || project.error || !p) {
    return (
      <div className="page">
        {back}
        {project.isPending ? (
          <p className="muted">Loading…</p>
        ) : (
          <p className="form-error">
            {project.error instanceof ApiError && project.error.status === 404
              ? 'This project does not exist, or was deleted.'
              : project.error?.message}
          </p>
        )}
      </div>
    )
  }

  const tasks = taskResults.flatMap((r) => (r.data ? [r.data] : []))
  const tasksLoading = taskResults.some((r) => r.isPending)
  const openTasks = tasks.filter((t) => !t.done)
  const shownTasks = (showDone ? tasks : openTasks).sort(byDue)
  const contacts = contactResults.flatMap((r) => (r.data ? [r.data] : []))
  const counts: Record<TabId, number | undefined> = {
    tasks: openTasks.length,
    contacts: p.contact_ids.length,
    documents: documents.data?.total,
    interactions: interactions.data?.total,
  }
  const without = (ids: string[], id: string) => ids.filter((x) => x !== id)

  return (
    <div className="page">
      {back}

      <header className="page-header page-header-row">
        <div className="page-header">
          <h1>{p.name}</h1>
          <p>
            <span className="badge" data-tone={statusOf(p) === 'active' ? 'success' : undefined}>
              {statusLabels[statusOf(p)]}
            </span>{' '}
            {p.end_date ? `${formatDay(p.start_date)} – ${formatDay(p.end_date)}` : `From ${formatDay(p.start_date)}`}
          </p>
        </div>
        <div className="header-actions">
          <Button variant="quiet" onPress={() => setConfirmDelete(true)}>
            Delete
          </Button>
          <Link to="/projects/$projectId/edit" params={{ projectId }} search={filters} className="button button-quiet">
            Edit
          </Link>
        </div>
      </header>

      {link.error && (
        <p className="form-error" role="alert">
          Could not change the links: {link.error.message}
        </p>
      )}

      <div className="profile">
        <Facts>
          {p.description && (
            <Fact label="Description">
              <Markdown>{p.description}</Markdown>
            </Fact>
          )}
        </Facts>

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
            <div className="tab-toolbar link-toolbar">
              <AddLinkPicker
                kind="task"
                exclude={p.task_ids}
                isDisabled={link.isPending}
                onAdd={(id) => link.mutate({ task_ids: [...p.task_ids, id] })}
              />
              <Checkbox isSelected={showDone} onChange={setShowDone}>
                Show done ({tasks.length - openTasks.length})
              </Checkbox>
              <NewProjectTask project={p} />
            </div>
            {taskToggle.repeated && (
              <p className="notice" role="status">
                Repeated: “{taskToggle.repeated.title}” is due again {formatDay(localDay(taskToggle.repeated.due))}.
              </p>
            )}
            {tasksLoading ? (
              <p className="muted">Loading…</p>
            ) : shownTasks.length === 0 ? (
              <p className="muted">{tasks.length ? 'Every task is done.' : 'No tasks in this project yet.'}</p>
            ) : (
              <TaskList
                tasks={shownTasks}
                onToggle={taskToggle.toggle}
                pendingId={taskToggle.pendingId}
                now={now}
                actions={(t) => (
                  <Button
                    variant="quiet"
                    isDisabled={link.isPending}
                    onPress={() => link.mutate({ task_ids: without(p.task_ids, t.id) })}
                  >
                    Unlink
                  </Button>
                )}
              />
            )}
          </TabPanel>

          <TabPanel id="contacts" className="panel-body">
            <div className="tab-toolbar link-toolbar">
              <AddLinkPicker
                kind="contact"
                exclude={p.contact_ids}
                isDisabled={link.isPending}
                onAdd={(id) => link.mutate({ contact_ids: [...p.contact_ids, id] })}
              />
            </div>
            {contactResults.some((r) => r.isPending) ? (
              <p className="muted">Loading…</p>
            ) : contacts.length === 0 ? (
              <p className="muted">No contacts on this project yet.</p>
            ) : (
              <ul className="rows">
                {contacts.map((c) => (
                  <li key={c.id}>
                    <span className="row-main">
                      <Link to="/contacts/$contactId" params={{ contactId: c.id }} className="row-link">
                        {c.name}
                      </Link>
                      {(c.job_title || c.organization_name) && (
                        <span className="row-meta">{[c.job_title, c.organization_name].filter(Boolean).join(' · ')}</span>
                      )}
                    </span>
                    <span className="row-actions">
                      <Link to="/contacts/$contactId/edit" params={{ contactId: c.id }} className="button button-quiet">
                        Edit
                      </Link>
                      <Button
                        variant="quiet"
                        isDisabled={link.isPending}
                        onPress={() => link.mutate({ contact_ids: without(p.contact_ids, c.id) })}
                      >
                        Unlink
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </TabPanel>

          <TabPanel id="documents" className="panel-body">
            <div className="tab-toolbar link-toolbar">
              <AddLinkPicker
                kind="document"
                exclude={p.document_ids}
                isDisabled={link.isPending}
                onAdd={(id) => link.mutate({ document_ids: [...p.document_ids, id] })}
              />
              <Link to="/documents/new" search={{ projectId }} className="button button-quiet">
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
              <DocumentRows
                items={documents.data.items}
                actions={(d) => (
                  <Button
                    variant="quiet"
                    isDisabled={link.isPending}
                    onPress={() => link.mutate({ document_ids: without(p.document_ids, d.id) })}
                  >
                    Unlink
                  </Button>
                )}
              />
            )}
          </TabPanel>

          <TabPanel id="interactions" className="panel-body">
            <div className="tab-toolbar">
              <Link to="/interactions/new" search={{ projectId }} className="button button-quiet">
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
        </Tabs>
      </div>

      <ConfirmDialog
        title="Delete this project?"
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        onConfirm={() => remove.mutate()}
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        pending={remove.isPending}
        error={remove.error}
      >
        <p>
          <strong>{p.name}</strong> will be permanently deleted. Its tasks, contacts and documents are kept.
        </p>
      </ConfirmDialog>
    </div>
  )
}

// Soonest due first, undated last — the task list's own order.
const byDue = (a: TaskRead, b: TaskRead) =>
  (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999') || a.title.localeCompare(b.title)

// A task made for this project, in place: title and an optional due date. The
// task page has the rest.
function NewProjectTask({ project }: { project: ProjectRead }) {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const mutation = useMutation({
    mutationFn: async () => {
      const task = await createTask(api, {
        title: title.trim(),
        due_date: due ? endOfLocalDay(due) : null,
        priority: 0,
        tags: [],
        recurrence_interval: 1,
      })
      return updateProject(api, project.id, { task_ids: [...project.task_ids, task.id] })
    },
    onSuccess: async (saved) => {
      queryClient.setQueryData(projectQuery(api, project.id).queryKey, saved)
      await Promise.all([invalidateProjects(queryClient), invalidateTasks(queryClient)])
      setOpen(false)
      setTitle('')
      setDue('')
    },
  })

  return (
    <>
      <Button variant="quiet" onPress={() => setOpen(true)}>
        New task
      </Button>
      <Modal title={`New task in ${project.name}`} isOpen={open} onOpenChange={setOpen}>
        <form
          className="quick-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (title.trim()) mutation.mutate()
          }}
        >
          <TextField label="Title" value={title} onChange={setTitle} autoFocus />
          <DatePicker label="Due" value={due} onChange={setDue} description="Optional." />
          {mutation.error && (
            <p className="form-error" role="alert">
              {mutation.error.message}
            </p>
          )}
          <div className="form-actions">
            <Button variant="quiet" onPress={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isDisabled={!title.trim() || mutation.isPending}>
              {mutation.isPending ? 'Creating…' : 'Create task'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
