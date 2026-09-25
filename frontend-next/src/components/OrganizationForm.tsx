import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import type { OrganizationCreate, OrganizationRead } from '../api/types'
import { Button } from './ui/Button'
import { FormTextField } from './ui/FormTextField'

// Every field is text in the form; the empty string is how an input says
// "nothing", and it goes to the API as null — the same as the Flutter form.
// On an edit that is also how a field gets cleared.
const optional = z.string().trim()

const formSchema = z.object({
  name: z.string().trim().min(1, 'Name is required.'),
  // Stored as a bare domain. A pasted URL is the common case, so the scheme and
  // anything after the host are dropped rather than rejected.
  domain: optional.transform((v) => v.replace(/^https?:\/\//i, '').replace(/\/.*$/, '')),
  industry: optional,
  email: optional.refine((v) => v === '' || z.email().safeParse(v).success, 'Enter a valid email address.'),
  phone: optional,
  address: optional,
  notes: optional,
})

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

const toBody = (values: FormOutput): OrganizationCreate => ({
  name: values.name,
  domain: values.domain || null,
  industry: values.industry || null,
  email: values.email || null,
  phone: values.phone || null,
  address: values.address || null,
  notes: values.notes || null,
})

const toDefaults = (org?: OrganizationRead): FormInput => ({
  name: org?.name ?? '',
  domain: org?.domain ?? '',
  industry: org?.industry ?? '',
  email: org?.email ?? '',
  phone: org?.phone ?? '',
  address: org?.address ?? '',
  notes: org?.notes ?? '',
})

export function OrganizationForm({
  initial,
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
}: {
  // Absent for a new organization.
  initial?: OrganizationRead
  onSubmit: (body: OrganizationCreate) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  // A link rendered with the button's look; where Cancel goes is the caller's.
  cancel: ReactNode
}) {
  const { control, handleSubmit } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial),
  })

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <FormTextField control={control} name="name" label="Name" autoFocus />

      <div className="form-row">
        <FormTextField control={control} name="domain" label="Domain" placeholder="acme.example" />
        <FormTextField control={control} name="industry" label="Industry" />
      </div>

      <div className="form-row">
        <FormTextField
          control={control}
          name="email"
          label="Email"
          type="email"
          placeholder="office@acme.example"
        />
        <FormTextField control={control} name="phone" label="Phone" type="tel" />
      </div>

      <FormTextField control={control} name="address" label="Address" rows={2} />
      <FormTextField control={control} name="notes" label="Notes" rows={4} />

      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}

      <div className="form-actions">
        {cancel}
        <Button type="submit" isDisabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  )
}
