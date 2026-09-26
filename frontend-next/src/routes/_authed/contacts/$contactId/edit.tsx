import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import type { ContactCreate } from '../../../../api/types'
import { ContactForm } from '../../../../components/ContactForm'
import { contactQuery, invalidateContacts, updateContact } from '../../../../contacts'

export const Route = createFileRoute('/_authed/contacts/$contactId/edit')({
  component: EditContact,
})

function EditContact() {
  const { api } = Route.useRouteContext()
  const { contactId } = Route.useParams()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const contact = useQuery(contactQuery(api, contactId))

  const mutation = useMutation({
    mutationFn: (body: ContactCreate) => updateContact(api, contactId, body),
    onSuccess: async (saved) => {
      queryClient.setQueryData(contactQuery(api, contactId).queryKey, saved)
      await invalidateContacts(queryClient)
      await navigate({ to: '/contacts/$contactId', params: { contactId }, search: filters, replace: true })
    },
  })

  const back = (
    <Link to="/contacts/$contactId" params={{ contactId }} search={filters} className="button button-quiet">
      Cancel
    </Link>
  )

  return (
    <div className="page page-narrow">
      <Link to="/contacts/$contactId" params={{ contactId }} search={filters} className="back-link">
        ← {contact.data?.name ?? 'Contact'}
      </Link>
      <header className="page-header">
        <h1>Edit contact</h1>
      </header>
      {contact.isPending ? (
        <p className="muted">Loading…</p>
      ) : contact.error ? (
        <p className="form-error">{contact.error.message}</p>
      ) : (
        <ContactForm
          initial={contact.data}
          onSubmit={(body) => mutation.mutate(body)}
          submitLabel="Save changes"
          pending={mutation.isPending}
          error={mutation.error}
          cancel={back}
        />
      )}
    </div>
  )
}
