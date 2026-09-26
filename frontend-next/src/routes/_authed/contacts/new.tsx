import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { z } from 'zod'
import type { ContactCreate } from '../../../api/types'
import { ContactForm } from '../../../components/ContactForm'
import { contactQuery, createContact, invalidateContacts } from '../../../contacts'

// Opened from an organization's page, the new contact starts at that
// organization, and Cancel goes back there.
const searchSchema = z.object({
  organizationId: z.string().optional().catch(undefined),
  organizationName: z.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_authed/contacts/new')({
  validateSearch: searchSchema,
  component: NewContact,
})

function NewContact() {
  const { api } = Route.useRouteContext()
  const { organizationId, organizationName, ...filters } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (body: ContactCreate) => createContact(api, body),
    onSuccess: async (contact) => {
      queryClient.setQueryData(contactQuery(api, contact.id).queryKey, contact)
      await invalidateContacts(queryClient)
      await navigate({ to: '/contacts/$contactId', params: { contactId: contact.id }, search: filters, replace: true })
    },
  })

  const back = organizationId ? (
    <Link to="/organizations/$organizationId" params={{ organizationId }} className="button button-quiet">
      Cancel
    </Link>
  ) : (
    <Link to="/contacts" search={filters} className="button button-quiet">
      Cancel
    </Link>
  )

  return (
    <div className="page page-narrow">
      {organizationId ? (
        <Link to="/organizations/$organizationId" params={{ organizationId }} className="back-link">
          ← {organizationName ?? 'Organization'}
        </Link>
      ) : (
        <Link to="/contacts" search={filters} className="back-link">
          ← Contacts
        </Link>
      )}
      <header className="page-header">
        <h1>New contact</h1>
      </header>
      <ContactForm
        organization={organizationId ? { id: organizationId, name: organizationName ?? '' } : undefined}
        onSubmit={(body) => mutation.mutate(body)}
        submitLabel="Create contact"
        pending={mutation.isPending}
        error={mutation.error}
        cancel={back}
      />
    </div>
  )
}
