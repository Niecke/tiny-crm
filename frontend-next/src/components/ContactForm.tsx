import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import type { ContactCreate, ContactRead } from '../api/types'
import { splitTags } from '../format'
import { lifecycleOptions, relationOptions, sourceOptions } from '../contacts'
import { createOrganization } from '../organizations'
import { OrganizationPicker } from './RecordPickers'
import { Button } from './ui/Button'
import { DatePicker } from './ui/DatePicker'
import { FormTextField } from './ui/FormTextField'
import { Modal } from './ui/Modal'
import { Select } from './ui/Select'
import { TextField } from './ui/TextField'

// Every text field is a string in the form; the empty string is how an input
// says "nothing", and it goes to the API as null. On an edit that is also how a
// field gets cleared.
const optional = z.string().trim()

const pattern = (re: RegExp, message: string) => optional.refine((v) => v === '' || re.test(v), message)
const email = optional.refine((v) => v === '' || z.email().safeParse(v).success, 'Enter a valid email address.')

// The backend's rules (schemas/contact.py, schemas/common.py), checked here so
// a typo is caught on the field instead of coming back as a 422.
const formSchema = z
  .object({
    name: z.string().trim().min(1, 'Name is required.'),
    job_title: optional,
    organization_id: z.string().nullable(),
    email,
    email_secondary: email,
    phone: optional,
    phone_secondary: optional,
    website: optional,
    street: optional,
    postal_code: optional,
    city: optional,
    country: pattern(/^[A-Za-z]{2}$/, 'Two letters, like AT or DE.'),
    lifecycle_status: z.enum(['', ...lifecycleOptions.map((o) => o.value)]),
    relation_type: z.enum(['', ...relationOptions.map((o) => o.value)]),
    source: z.enum(['', ...sourceOptions.map((o) => o.value)]),
    works_with_freelancers: z.enum(['', 'yes', 'no']),
    known_day_rate: pattern(/^\d{1,12}([.,]\d{1,2})?$/, 'An amount like 850 or 850.50.'),
    rate_currency: optional,
    preferred_language: pattern(/^[A-Za-z]{2}$/, 'Two letters, like de or en.'),
    birthday: z.string(),
    tags: optional,
    notes: optional,
  })
  // The router refuses a rate without its currency, as it refuses a deal's
  // volume without a unit. The currency is only checked when there is a rate.
  .refine((v) => v.known_day_rate === '' || /^[A-Za-z]{3}$/.test(v.rate_currency), {
    path: ['rate_currency'],
    message: 'Three letters, like EUR.',
  })

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

const orNull = (v: string) => v || null

const toBody = (v: FormOutput): ContactCreate => ({
  name: v.name,
  job_title: orNull(v.job_title),
  organization_id: v.organization_id,
  email: orNull(v.email),
  email_secondary: orNull(v.email_secondary),
  phone: orNull(v.phone),
  phone_secondary: orNull(v.phone_secondary),
  website: orNull(v.website),
  street: orNull(v.street),
  postal_code: orNull(v.postal_code),
  city: orNull(v.city),
  country: v.country ? v.country.toUpperCase() : null,
  lifecycle_status: v.lifecycle_status || null,
  relation_type: v.relation_type || null,
  source: v.source || null,
  works_with_freelancers: v.works_with_freelancers === '' ? null : v.works_with_freelancers === 'yes',
  // Sent as a string, like every amount in the API: a double cannot hold 0.10.
  // A comma is what a German keyboard types for the decimal point.
  known_day_rate: v.known_day_rate ? v.known_day_rate.replace(',', '.') : null,
  rate_currency: v.known_day_rate ? v.rate_currency.toUpperCase() : null,
  preferred_language: v.preferred_language ? v.preferred_language.toLowerCase() : null,
  birthday: v.birthday || null,
  tags: splitTags(v.tags),
  notes: orNull(v.notes),
})

const toDefaults = (c?: ContactRead, organizationId?: string): FormInput => ({
  name: c?.name ?? '',
  job_title: c?.job_title ?? '',
  organization_id: c ? (c.organization_id ?? null) : (organizationId ?? null),
  email: c?.email ?? '',
  email_secondary: c?.email_secondary ?? '',
  phone: c?.phone ?? '',
  phone_secondary: c?.phone_secondary ?? '',
  website: c?.website ?? '',
  street: c?.street ?? '',
  postal_code: c?.postal_code ?? '',
  city: c?.city ?? '',
  country: c?.country ?? '',
  lifecycle_status: c?.lifecycle_status ?? '',
  relation_type: c?.relation_type ?? '',
  source: c?.source ?? '',
  works_with_freelancers: c?.works_with_freelancers == null ? '' : c.works_with_freelancers ? 'yes' : 'no',
  known_day_rate: c?.known_day_rate ?? '',
  rate_currency: c?.rate_currency ?? 'EUR',
  preferred_language: c?.preferred_language ?? '',
  birthday: c?.birthday ?? '',
  tags: c?.tags.join(', ') ?? '',
  notes: c?.notes ?? '',
})

const freelancerOptions: { value: 'yes' | 'no'; label: string }[] = [
  { value: 'yes', label: 'Works with freelancers' },
  { value: 'no', label: 'Does not use freelancers' },
]

export function ContactForm({
  initial,
  organization,
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
}: {
  // Absent for a new contact.
  initial?: ContactRead
  // Preselected on a new contact opened from an organization's page.
  organization?: { id: string; name: string }
  onSubmit: (body: ContactCreate) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
}) {
  const { control, handleSubmit, setValue } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial, organization?.id),
  })
  // A new organization made from here is chosen at once; the picker is keyed
  // on it so it restarts showing the new name.
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null)
  const orgLabel = created?.name ?? initial?.organization_name ?? organization?.name ?? null

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <FormTextField control={control} name="name" label="Name" autoFocus />
      <div className="form-row">
        <FormTextField control={control} name="job_title" label="Job title" />
        <div className="field-with-action">
          <Controller
            control={control}
            name="organization_id"
            render={({ field }) => (
              <OrganizationPicker
                key={created?.id}
                value={field.value}
                onChange={field.onChange}
                initialLabel={orgLabel}
              />
            )}
          />
          <NewOrganization
            onCreated={(org) => {
              setCreated(org)
              setValue('organization_id', org.id, { shouldDirty: true })
            }}
          />
        </div>
      </div>

      <fieldset className="form-section">
        <legend>Reach</legend>
        <div className="form-row">
          <FormTextField control={control} name="email" label="Email" type="email" />
          <FormTextField control={control} name="email_secondary" label="Second email" type="email" />
        </div>
        <div className="form-row">
          <FormTextField control={control} name="phone" label="Phone" type="tel" />
          <FormTextField control={control} name="phone_secondary" label="Second phone" type="tel" />
        </div>
        <FormTextField control={control} name="website" label="Website" placeholder="https://" />
      </fieldset>

      <fieldset className="form-section">
        <legend>Address</legend>
        <FormTextField control={control} name="street" label="Street" />
        <div className="form-row form-row-3">
          <FormTextField control={control} name="postal_code" label="Postcode" />
          <FormTextField control={control} name="city" label="City" />
          <FormTextField control={control} name="country" label="Country" placeholder="AT" maxLength={2} />
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Relationship</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="lifecycle_status"
            render={({ field }) => (
              <Select
                label="Status"
                emptyLabel="Not set"
                options={lifecycleOptions}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="relation_type"
            render={({ field }) => (
              <Select
                label="Type"
                emptyLabel="Not set"
                options={relationOptions}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </div>
        <div className="form-row">
          <Controller
            control={control}
            name="source"
            render={({ field }) => (
              <Select
                label="Source"
                emptyLabel="Not set"
                options={sourceOptions}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="works_with_freelancers"
            render={({ field }) => (
              <Select
                label="Works with freelancers?"
                emptyLabel="Never asked"
                options={freelancerOptions}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </div>
        <div className="form-row">
          <FormTextField control={control} name="known_day_rate" label="Known day rate" inputMode="decimal" />
          <FormTextField control={control} name="rate_currency" label="Currency" maxLength={3} />
        </div>
        <div className="form-row">
          <FormTextField
            control={control}
            name="preferred_language"
            label="Preferred language"
            placeholder="de"
            maxLength={2}
          />
          <Controller
            control={control}
            name="birthday"
            render={({ field }) => (
              <DatePicker
                label="Birthday"
                value={field.value}
                onChange={field.onChange}
                minValue="1900-01-01"
                maxValue={today()}
              />
            )}
          />
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Filing</legend>
        <FormTextField control={control} name="tags" label="Tags" description="Separated by commas." />
        <FormTextField control={control} name="notes" label="Notes" rows={4} />
      </fieldset>

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

const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// A company that is not on file yet, made without leaving the contact form:
// its name is enough, the rest can be filled in on its own page later.
function NewOrganization({ onCreated }: { onCreated: (org: { id: string; name: string }) => void }) {
  const { api } = useRouteContext({ from: '/_authed' })
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const mutation = useMutation({
    mutationFn: () => createOrganization(api, { name: name.trim() }),
    onSuccess: async (org) => {
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      onCreated({ id: org.id, name: org.name })
      setOpen(false)
      setName('')
    },
  })

  return (
    <>
      <Button variant="quiet" className="link-button" onPress={() => setOpen(true)}>
        New organization
      </Button>
      <Modal title="New organization" isOpen={open} onOpenChange={setOpen}>
        {/* Its own form, not nested in the contact form: Enter here saves the
            organization, not the contact. */}
        <form
          className="quick-form"
          onSubmit={(e) => {
            e.preventDefault()
            e.stopPropagation()
            if (name.trim()) mutation.mutate()
          }}
        >
          <TextField label="Name" value={name} onChange={setName} autoFocus />
          {mutation.error && (
            <p className="form-error" role="alert">
              {mutation.error.message}
            </p>
          )}
          <div className="form-actions">
            <Button variant="quiet" onPress={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isDisabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? 'Creating…' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
