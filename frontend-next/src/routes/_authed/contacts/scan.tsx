import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { FileTrigger } from 'react-aria-components'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import type { BusinessCardImport, BusinessCardScan } from '../../../api/types'
import { importCard, scanCard } from '../../../businessCards'
import { contactQuery, invalidateContacts } from '../../../contacts'
import { OrganizationPicker } from '../../../components/RecordPickers'
import { Button } from '../../../components/ui/Button'
import { FormTextField } from '../../../components/ui/FormTextField'
import { Segmented } from '../../../components/ui/Segmented'

// Business card scanning (#262): photograph the card, check what was read,
// file it as a contact and — if it is new — the company.
export const Route = createFileRoute('/_authed/contacts/scan')({
  component: ScanCard,
})

function ScanCard() {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const [scan, setScan] = useState<BusinessCardScan | null>(null)

  const reading = useMutation({
    mutationFn: ({ front, back }: { front: File; back: File | null }) => scanCard(api, front, back),
    onSuccess: setScan,
  })

  return (
    <div className="page page-narrow">
      <Link to="/contacts" search={filters} className="back-link">
        ← Contacts
      </Link>
      <header className="page-header">
        <h1>Scan business card</h1>
      </header>
      {scan ? (
        <CardReview scan={scan} onRescan={() => setScan(null)} />
      ) : (
        <CardPhotos
          onRead={(front, back) => reading.mutate({ front, back })}
          pending={reading.isPending}
          error={reading.error}
        />
      )}
    </div>
  )
}

// --- Step 1: the photos ------------------------------------------------------

function CardPhotos({
  onRead,
  pending,
  error,
}: {
  onRead: (front: File, back: File | null) => void
  pending: boolean
  error: Error | null
}) {
  const [front, setFront] = useState<Photo | null>(null)
  const [back, setBack] = useState<Photo | null>(null)

  return (
    <form
      className="panel form"
      onSubmit={(e) => {
        e.preventDefault()
        if (front) onRead(front.file, back?.file ?? null)
      }}
    >
      <p className="muted">
        Take a photo of each side, or upload photos you already have. What is read comes back as a draft to check —
        nothing is saved until you do.
      </p>
      <div className="card-sides">
        <CardSide label="Front" photo={front} onChange={setFront} />
        <CardSide label="Back (optional)" photo={back} onChange={setBack} />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}
      <div className="form-actions">
        <Button type="submit" isDisabled={!front || pending}>
          {pending ? 'Reading card…' : 'Read card'}
        </Button>
      </div>
    </form>
  )
}

// A chosen photo and the object URL its preview shows. The URL is made when
// the photo is picked and released when it is replaced or removed.
type Photo = { file: File; url: string }

function CardSide({
  label,
  photo,
  onChange,
}: {
  label: string
  photo: Photo | null
  onChange: (photo: Photo | null) => void
}) {
  const replace = (file: File | null) => {
    if (photo) URL.revokeObjectURL(photo.url)
    onChange(file ? { file, url: URL.createObjectURL(file) } : null)
  }
  const pick = (list: FileList | null) => {
    const f = list?.[0]
    if (f) replace(f)
  }
  return (
    <div className="field card-side">
      <span className="field-label">{label}</span>
      <div className="card-side-preview">
        {photo ? <img src={photo.url} alt={`${label} of the card`} /> : <span className="muted">No photo yet</span>}
      </div>
      <div className="card-side-actions">
        {/* On a phone this opens the camera; on a desktop it is a file picker. */}
        <FileTrigger acceptedFileTypes={['image/*']} defaultCamera="environment" onSelect={pick}>
          <Button variant="quiet">Take photo</Button>
        </FileTrigger>
        <FileTrigger acceptedFileTypes={['image/*']} onSelect={pick}>
          <Button variant="quiet">Upload</Button>
        </FileTrigger>
        {photo && (
          <Button variant="quiet" onPress={() => replace(null)}>
            Remove
          </Button>
        )}
      </div>
    </div>
  )
}

// --- Step 2: check what was read --------------------------------------------

type CompanyChoice = 'existing' | 'new' | 'none'

const optional = z.string().trim()
const email = optional.refine((v) => v === '' || z.email().safeParse(v).success, 'Enter a valid email address.')

const formSchema = z
  .object({
    name: z.string().trim().min(1, 'Name is required.'),
    job_title: optional,
    email,
    email_secondary: email,
    phone: optional,
    phone_secondary: optional,
    website: optional,
    street: optional,
    postal_code: optional,
    city: optional,
    country: optional.refine((v) => v === '' || /^[A-Za-z]{2}$/.test(v), 'Two letters, like AT or DE.'),
    notes: optional,
    company: z.enum(['existing', 'new', 'none']),
    organization_id: z.string().nullable(),
    org_name: optional,
    org_domain: optional,
    org_email: email,
    org_phone: optional,
    org_address: optional,
  })
  .refine((v) => v.company !== 'existing' || v.organization_id, {
    path: ['organization_id'],
    message: 'Choose the company.',
  })
  .refine((v) => v.company !== 'new' || v.org_name, { path: ['org_name'], message: 'Name is required.' })

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

const orNull = (v: string) => v || null

const toDefaults = (scan: BusinessCardScan): FormInput => {
  const c = scan.contact
  const o = scan.organization
  return {
    name: c.name ?? '',
    job_title: c.job_title ?? '',
    email: c.email ?? '',
    email_secondary: c.email_secondary ?? '',
    phone: c.phone ?? '',
    phone_secondary: c.phone_secondary ?? '',
    website: c.website ?? '',
    street: c.street ?? '',
    postal_code: c.postal_code ?? '',
    city: c.city ?? '',
    country: c.country ?? '',
    notes: c.notes ?? '',
    // A company already on file wins over making a second one.
    company: scan.match ? 'existing' : o ? 'new' : 'none',
    organization_id: scan.match?.id ?? null,
    org_name: o?.name ?? '',
    org_domain: o?.domain ?? '',
    org_email: o?.email ?? '',
    org_phone: o?.phone ?? '',
    org_address: o?.address ?? '',
  }
}

const toBody = (v: FormOutput): BusinessCardImport => ({
  contact: {
    name: v.name,
    job_title: orNull(v.job_title),
    organization_id: v.company === 'existing' ? v.organization_id : null,
    email: orNull(v.email),
    email_secondary: orNull(v.email_secondary),
    phone: orNull(v.phone),
    phone_secondary: orNull(v.phone_secondary),
    website: orNull(v.website),
    street: orNull(v.street),
    postal_code: orNull(v.postal_code),
    city: orNull(v.city),
    country: v.country ? v.country.toUpperCase() : null,
    notes: orNull(v.notes),
    tags: [],
  },
  organization:
    v.company === 'new'
      ? {
          name: v.org_name,
          domain: orNull(v.org_domain),
          email: orNull(v.org_email),
          phone: orNull(v.org_phone),
          address: orNull(v.org_address),
        }
      : null,
})

function CardReview({ scan, onRescan }: { scan: BusinessCardScan; onRescan: () => void }) {
  const { api } = Route.useRouteContext()
  const filters = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { control, handleSubmit } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(scan),
  })
  const company = useWatch({ control, name: 'company' })

  const mutation = useMutation({
    mutationFn: (body: BusinessCardImport) => importCard(api, body),
    onSuccess: async (contact) => {
      queryClient.setQueryData(contactQuery(api, contact.id).queryKey, contact)
      await invalidateContacts(queryClient)
      await navigate({ to: '/contacts/$contactId', params: { contactId: contact.id }, search: filters, replace: true })
    },
  })

  const companyOptions: { value: CompanyChoice; label: string }[] = [
    { value: 'existing', label: 'On file' },
    ...(scan.organization ? [{ value: 'new' as const, label: 'New company' }] : []),
    { value: 'none', label: 'No company' },
  ]

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => mutation.mutate(toBody(values)))} noValidate>
      <p className="muted">Check what was read against the card and correct anything that is off.</p>

      <fieldset className="form-section">
        <legend>Person</legend>
        <div className="form-row">
          <FormTextField control={control} name="name" label="Name" autoFocus />
          <FormTextField control={control} name="job_title" label="Job title" />
        </div>
        <div className="form-row">
          <FormTextField control={control} name="email" label="Email" type="email" />
          <FormTextField control={control} name="email_secondary" label="Second email" type="email" />
        </div>
        <div className="form-row">
          <FormTextField control={control} name="phone" label="Phone" type="tel" />
          <FormTextField control={control} name="phone_secondary" label="Second phone" type="tel" />
        </div>
        <FormTextField control={control} name="website" label="Website" />
        <FormTextField control={control} name="street" label="Street" />
        <div className="form-row form-row-3">
          <FormTextField control={control} name="postal_code" label="Postcode" />
          <FormTextField control={control} name="city" label="City" />
          <FormTextField control={control} name="country" label="Country" placeholder="AT" maxLength={2} />
        </div>
        <FormTextField control={control} name="notes" label="Notes" rows={3} />
      </fieldset>

      <fieldset className="form-section">
        <legend>Company</legend>
        {scan.match && (
          <p className="muted">
            {scan.match.matched_on === 'domain'
              ? `${scan.match.name} is already on file with the same domain.`
              : `${scan.match.name} is already on file with the same name.`}
          </p>
        )}
        <Controller
          control={control}
          name="company"
          render={({ field }) => (
            <Segmented label="Company" options={companyOptions} value={field.value} onChange={field.onChange} />
          )}
        />
        {company === 'existing' && (
          <Controller
            control={control}
            name="organization_id"
            render={({ field, fieldState }) => (
              <OrganizationPicker
                value={field.value}
                onChange={field.onChange}
                initialLabel={scan.match?.name ?? null}
                placeholder="Search companies"
                errorMessage={fieldState.error?.message}
              />
            )}
          />
        )}
        {company === 'new' && (
          <>
            <div className="form-row">
              <FormTextField control={control} name="org_name" label="Name" />
              <FormTextField control={control} name="org_domain" label="Domain" placeholder="acme.example" />
            </div>
            <div className="form-row">
              <FormTextField control={control} name="org_email" label="Company email" type="email" />
              <FormTextField control={control} name="org_phone" label="Switchboard" type="tel" />
            </div>
            <FormTextField control={control} name="org_address" label="Address" />
          </>
        )}
      </fieldset>

      {mutation.error && (
        <p className="form-error" role="alert">
          {mutation.error.message}
        </p>
      )}

      <div className="form-actions">
        <Button variant="quiet" onPress={onRescan}>
          Scan again
        </Button>
        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save contact'}
        </Button>
      </div>
    </form>
  )
}
