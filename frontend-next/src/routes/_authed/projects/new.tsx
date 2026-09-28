import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { ProjectForm, type ProjectFields } from '../../../components/ProjectForm'
import { createProject, invalidateProjects, projectQuery } from '../../../projects'

export const Route = createFileRoute('/_authed/projects/new')({
  component: NewProject,
})

function NewProject() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (fields: ProjectFields) =>
      createProject(api, { ...fields, contact_ids: [], task_ids: [], document_ids: [] }),
    onSuccess: async (project) => {
      queryClient.setQueryData(projectQuery(api, project.id).queryKey, project)
      await invalidateProjects(queryClient)
      await navigate({ to: '/projects/$projectId', params: { projectId: project.id }, search: filters, replace: true })
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/projects" search={filters} className="back-link">
        ← Projects
      </Link>
      <header className="page-header">
        <h1>New project</h1>
      </header>
      <ProjectForm
        onSubmit={(fields) => mutation.mutate(fields)}
        submitLabel="Create project"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Link to="/projects" search={filters} className="button button-quiet">
            Cancel
          </Link>
        }
      />
    </div>
  )
}
