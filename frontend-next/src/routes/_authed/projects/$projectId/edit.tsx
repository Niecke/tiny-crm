import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { ProjectForm, type ProjectFields } from '../../../../components/ProjectForm'
import { invalidateProjects, projectQuery, updateProject } from '../../../../projects'
import { StaleSaveNotice } from '../../../../components/StaleSaveNotice'
import { formError, useEditVersion } from '../../../../useEditVersion'

export const Route = createFileRoute('/_authed/projects/$projectId/edit')({
  component: EditProject,
})

function EditProject() {
  const { api } = Route.useRouteContext()
  const { projectId } = Route.useParams()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const project = useQuery(projectQuery(api, projectId))
  const editing = useEditVersion(project)
  const mutation = useMutation({
    mutationFn: (fields: ProjectFields) => updateProject(api, projectId, fields, editing.version),
    onSuccess: async (saved) => {
      queryClient.setQueryData(projectQuery(api, projectId).queryKey, saved)
      await invalidateProjects(queryClient)
      await navigate({ to: '/projects/$projectId', params: { projectId }, search: filters, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/projects/$projectId" params={{ projectId }} search={filters} className="back-link">
        ← {project.data?.name ?? 'Project'}
      </Link>
      <header className="page-header">
        <h1>Edit project</h1>
      </header>
      <StaleSaveNotice error={mutation.error} onReload={() => void editing.reload().then(() => mutation.reset())} />
      {project.isPending ? (
        <p className="muted">Loading…</p>
      ) : project.error ? (
        <p className="form-error">{project.error.message}</p>
      ) : (
        <ProjectForm
          key={editing.formKey}
          initial={project.data}
          onSubmit={(fields) => mutation.mutate(fields)}
          submitLabel="Save changes"
          pending={mutation.isPending}
          error={formError(mutation.error)}
          cancel={
            <Link to="/projects/$projectId" params={{ projectId }} search={filters} className="button button-quiet">
              Cancel
            </Link>
          }
        />
      )}
    </div>
  )
}
