import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useLeave } from '../../../useLeave'
import { z } from 'zod'
import { DocumentForm, type DocumentFields } from '../../../components/DocumentForm'
import { Button } from '../../../components/ui/Button'
import { documentQuery, invalidateDocuments, uploadDocument } from '../../../documents'

// Uploaded from a record page, the document starts filed under that record.
const searchSchema = z.object({
  contactId: z.string().optional().catch(undefined),
  organizationId: z.string().optional().catch(undefined),
  dealId: z.string().optional().catch(undefined),
  projectId: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/documents/new')({
  validateSearch: searchSchema,
  component: UploadDocument,
})

function UploadDocument() {
  const { api } = Route.useRouteContext()
  const { contactId, organizationId, dealId, projectId, ...filters } = Route.useSearch()
  const queryClient = useQueryClient()
  const leave = useLeave({ to: '/documents', search: filters })

  const mutation = useMutation({
    mutationFn: ({ fields, file }: { fields: DocumentFields; file: File }) => uploadDocument(api, file, fields),
    onSuccess: async (doc) => {
      queryClient.setQueryData(documentQuery(api, doc.id).queryKey, doc)
      await invalidateDocuments(queryClient)
      await leave()
    },
  })

  return (
    <div className="page page-narrow">
      <Link to="/documents" search={filters} className="back-link">
        ← Documents
      </Link>
      <header className="page-header">
        <h1>Upload document</h1>
      </header>
      <DocumentForm
        withFile
        preset={{ contact_id: contactId, organization_id: organizationId, deal_id: dealId, project_id: projectId }}
        onSubmit={(fields, file) => file && mutation.mutate({ fields, file })}
        submitLabel="Upload"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={
          <Button variant="quiet" onPress={() => void leave()}>
            Cancel
          </Button>
        }
      />
    </div>
  )
}
