import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useRouterState } from '@tanstack/react-router'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { ApiError } from '../../../api/client'
import type { CaptureConvert, CaptureRead } from '../../../api/types'
import {
  captureQuery,
  capturesQuery,
  convertCapture,
  dismissCapture,
  invalidateAfterCapture,
} from '../../../captures'
import { ContactPicker, OrganizationPicker } from '../../../components/RecordPickers'
import { Button } from '../../../components/ui/Button'
import { Checkbox } from '../../../components/ui/Checkbox'
import { FormTextField } from '../../../components/ui/FormTextField'
import { Modal } from '../../../components/ui/Modal'
import { Segmented } from '../../../components/ui/Segmented'
import { daysSince, formatDate } from '../../../format'

export const Route = createFileRoute('/_authed/inbox/$captureId')({
  component: Triage,
})

// One capture, worked: who they are (a new contact or one you already have),
// optionally the lead it opens and the message you sent — one request, then
// on to the next. The same flow as the Flutter inbox.
function Triage() {
  const { api } = Route.useRouteContext()
  const { captureId } = Route.useParams()
  const search = Route.useSearch()
  const capture = useQuery(captureQuery(api, captureId))
  // The waiting list, oldest first, for "n of m" and for where to go next.
  const waiting = useQuery(capturesQuery(api, 'new', ''))
  const flash = useRouterState({ select: (s) => s.location.state.flash })

  const queue = waiting.data?.items ?? []
  const position = queue.findIndex((c) => c.id === captureId)
  // The one after this, or the first other one when this was the last.
  const next = queue[position + 1] ?? queue.find((c) => c.id !== captureId)

  return (
    <div className="page page-narrow">
      <Link to="/inbox" search={search} className="back-link">
        ← Inbox
      </Link>

      {flash && (
        <p className="notice" role="status">
          {flash}
        </p>
      )}

      {capture.isPending ? (
        <p className="muted">Loading…</p>
      ) : capture.error ? (
        <p className="form-error">
          {capture.error instanceof ApiError && capture.error.status === 404
            ? 'This capture does not exist, or was deleted.'
            : capture.error.message}
        </p>
      ) : (
        <>
          <header className="page-header page-header-row">
            <div className="page-header">
              {position >= 0 && (
                <p className="small">
                  {position + 1} of {queue.length} waiting
                </p>
              )}
              <h1>{capture.data.name ?? capture.data.raw}</h1>
            </div>
            {capture.data.status === 'new' && next && (
              <Link
                to="/inbox/$captureId"
                params={{ captureId: next.id }}
                search={search}
                className="button button-quiet"
              >
                Skip
              </Link>
            )}
          </header>

          <Captured capture={capture.data} />

          {capture.data.status === 'new' ? (
            // Keyed by id: moving to the next capture starts a fresh form with
            // that capture's defaults.
            <TriageForm key={capture.data.id} capture={capture.data} nextId={next?.id} />
          ) : (
            <Worked capture={capture.data} />
          )}
        </>
      )}
    </div>
  )
}

// What was captured: the original text, the link to look at while deciding,
// and how long it has waited.
function Captured({ capture }: { capture: CaptureRead }) {
  const days = daysSince(capture.created_at)
  return (
    <section className="panel facts captured">
      <dl>
        {capture.name && capture.raw !== capture.name && (
          <div className="fact">
            <dt>Captured as</dt>
            <dd>{capture.raw}</dd>
          </div>
        )}
        {capture.url && (
          <div className="fact">
            <dt>Link</dt>
            <dd>
              {/* Only http(s) reaches here: the server extracts links with an
                  http(s) pattern, and a shared url is taken as given — so the
                  scheme is checked before it becomes an href. */}
              {/^https?:\/\//i.test(capture.url) ? (
                <a href={capture.url} target="_blank" rel="noreferrer">
                  {capture.url}
                </a>
              ) : (
                capture.url
              )}
            </dd>
          </div>
        )}
        {capture.note && (
          <div className="fact">
            <dt>Note</dt>
            <dd>{capture.note}</dd>
          </div>
        )}
        <div className="fact">
          <dt>Captured</dt>
          <dd>
            {formatDate(capture.created_at)}
            {days > 0 && <span className="muted"> · waiting {days === 1 ? '1 day' : `${days} days`}</span>}
          </dd>
        </div>
      </dl>
    </section>
  )
}

function Worked({ capture }: { capture: CaptureRead }) {
  return (
    <section className="panel facts">
      {capture.status === 'converted' ? (
        <p>
          Converted{capture.triaged_at && ` on ${formatDate(capture.triaged_at)}`} into{' '}
          <strong>{capture.contact_name ?? 'a contact'}</strong>
          {capture.deal_title && (
            <>
              , with the lead <strong>{capture.deal_title}</strong>
            </>
          )}
          .
        </p>
      ) : (
        <p>
          Dismissed{capture.triaged_at && ` on ${formatDate(capture.triaged_at)}`}. The inbox will not offer it
          again.
        </p>
      )}
    </section>
  )
}

const formSchema = z
  .object({
    mode: z.enum(['new', 'existing']),
    contactId: z.string().nullable(),
    name: z.string().trim(),
    jobTitle: z.string().trim(),
    email: z.string().trim(),
    website: z.string().trim(),
    organizationId: z.string().nullable(),
    openDeal: z.boolean(),
    dealTitle: z.string().trim(),
    logMessage: z.boolean(),
    subject: z.string().trim(),
    messageNotes: z.string().trim(),
  })
  // Which fields are required depends on the choices above, so the rules live
  // here rather than on the fields.
  .superRefine((v, ctx) => {
    if (v.mode === 'new' && !v.name) ctx.addIssue({ code: 'custom', path: ['name'], message: 'Name is required.' })
    if (v.mode === 'new' && v.email && !z.email().safeParse(v.email).success) {
      ctx.addIssue({ code: 'custom', path: ['email'], message: 'Enter a valid email address.' })
    }
    if (v.mode === 'existing' && !v.contactId) {
      ctx.addIssue({ code: 'custom', path: ['contactId'], message: 'Pick the contact this is.' })
    }
    if (v.openDeal && !v.dealTitle) {
      ctx.addIssue({ code: 'custom', path: ['dealTitle'], message: 'The lead needs a title.' })
    }
    if (v.logMessage && !v.subject) {
      ctx.addIssue({ code: 'custom', path: ['subject'], message: 'The message needs a subject.' })
    }
  })

type FormValues = z.infer<typeof formSchema>

// Filled from what the capture already knows, so the common case — a new
// person, a lead, "I wrote to them" — is one click.
const defaultsFor = (capture: CaptureRead): FormValues => {
  const name = capture.name ?? ''
  return {
    mode: 'new',
    contactId: null,
    name,
    jobTitle: '',
    email: '',
    // The captured link is almost always the person's profile.
    website: capture.url ?? '',
    organizationId: null,
    openDeal: true,
    dealTitle: name ? `Outreach – ${name}` : 'Outreach',
    logMessage: true,
    subject: name ? `Wrote to ${name}` : 'Wrote to them',
    messageNotes: '',
  }
}

const toBody = (v: FormValues): CaptureConvert => ({
  ...(v.mode === 'existing'
    ? { contact_id: v.contactId }
    : {
        contact: {
          name: v.name,
          job_title: v.jobTitle || null,
          email: v.email || null,
          website: v.website || null,
          organization_id: v.organizationId,
          lifecycle_status: 'lead',
          tags: [],
        },
      }),
  deal: v.openDeal ? { title: v.dealTitle } : null,
  interaction: v.logMessage ? { kind: 'email', subject: v.subject, notes: v.messageNotes || null } : null,
})

function TriageForm({ capture, nextId }: { capture: CaptureRead; nextId: string | undefined }) {
  const { api } = Route.useRouteContext()
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const queryClient = useQueryClient()
  const [confirmDismiss, setConfirmDismiss] = useState(false)

  const { control, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: defaultsFor(capture),
  })
  const [mode, openDeal, logMessage] = useWatch({ control, name: ['mode', 'openDeal', 'logMessage'] })

  // Where a worked capture leads: the next one waiting, or back to the inbox.
  async function advance(flash: string) {
    if (nextId) {
      await navigate({ to: '/inbox/$captureId', params: { captureId: nextId }, search, state: { flash } })
    } else {
      await navigate({ to: '/inbox', search, state: { flash: `${flash} That was the last one.` } })
    }
  }

  const convert = useMutation({
    mutationFn: (values: FormValues) => convertCapture(api, capture.id, toBody(values)),
    onSuccess: async (result) => {
      await invalidateAfterCapture(queryClient, true)
      await advance(result.deal ? `${result.contact.name} is a lead.` : `${result.contact.name} is filed.`)
    },
  })

  const dismiss = useMutation({
    mutationFn: () => dismissCapture(api, capture.id),
    onSuccess: async () => {
      setConfirmDismiss(false)
      await invalidateAfterCapture(queryClient)
      await advance(`Dismissed ${capture.name ?? capture.raw}.`)
    },
  })

  const busy = convert.isPending || dismiss.isPending

  return (
    <form className="panel form" onSubmit={handleSubmit((v) => convert.mutate(v))} noValidate>
      <Controller
        control={control}
        name="mode"
        render={({ field }) => (
          <Segmented
            label="Who is this"
            value={field.value}
            onChange={field.onChange}
            options={[
              { value: 'new', label: 'New person' },
              { value: 'existing', label: 'Already a contact' },
            ]}
          />
        )}
      />

      {mode === 'existing' ? (
        <Controller
          control={control}
          name="contactId"
          render={({ field, fieldState }) => (
            <ContactPicker value={field.value} onChange={field.onChange} errorMessage={fieldState.error?.message} />
          )}
        />
      ) : (
        <>
          <FormTextField control={control} name="name" label="Name" autoFocus />
          <div className="form-row">
            <FormTextField control={control} name="jobTitle" label="Job title" />
            <Controller
              control={control}
              name="organizationId"
              render={({ field }) => <OrganizationPicker value={field.value} onChange={field.onChange} />}
            />
          </div>
          <div className="form-row">
            <FormTextField control={control} name="email" label="Email" type="email" />
            <FormTextField control={control} name="website" label="Website" />
          </div>
        </>
      )}

      <Controller
        control={control}
        name="openDeal"
        render={({ field }) => (
          <Checkbox isSelected={field.value} onChange={field.onChange} description="Puts them on the pipeline board.">
            Open a deal at stage Lead
          </Checkbox>
        )}
      />
      {openDeal && <FormTextField control={control} name="dealTitle" label="Deal title" />}

      <Controller
        control={control}
        name="logMessage"
        render={({ field }) => (
          <Checkbox
            isSelected={field.value}
            onChange={field.onChange}
            description="Recorded as an email sent now, in the activity log."
          >
            Log the message you sent
          </Checkbox>
        )}
      />
      {logMessage && (
        <>
          <FormTextField control={control} name="subject" label="Subject" />
          <FormTextField control={control} name="messageNotes" label="What you wrote" rows={3} />
        </>
      )}

      {(convert.error || dismiss.error) && (
        <p className="form-error" role="alert">
          {(convert.error ?? dismiss.error)?.message}
        </p>
      )}

      <div className="form-actions">
        <Button variant="quiet" onPress={() => setConfirmDismiss(true)} isDisabled={busy}>
          Dismiss
        </Button>
        <Button type="submit" isDisabled={busy}>
          {convert.isPending ? 'Working…' : nextId ? 'Convert and go to next' : 'Convert'}
        </Button>
      </div>

      <Modal title="Dismiss this capture?" isOpen={confirmDismiss} onOpenChange={setConfirmDismiss}>
        <p>
          <strong>{capture.name ?? capture.raw}</strong> stays on record as decided against, so the inbox will not
          offer it again.
        </p>
        <div className="form-actions">
          <Button variant="quiet" onPress={() => setConfirmDismiss(false)}>
            Keep it
          </Button>
          <Button onPress={() => dismiss.mutate()} isDisabled={dismiss.isPending}>
            {dismiss.isPending ? 'Dismissing…' : 'Dismiss'}
          </Button>
        </div>
      </Modal>
    </form>
  )
}
