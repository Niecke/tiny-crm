import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import type { WatchCreate, WatchRead } from '../api/types'
import { MAX_RECURRENCE_INTERVAL, recurrenceOptions } from '../tasks'
import { kindOptions } from '../watches'
import { OrganizationPicker } from './RecordPickers'
import { Button } from './ui/Button'
import { Checkbox } from './ui/Checkbox'
import { FormTextField } from './ui/FormTextField'
import { Select } from './ui/Select'

const optional = z.string().trim()

const formSchema = z.object({
  name: z.string().trim().min(1, 'Name is required.'),
  // A source you cannot open is not a source.
  url: z
    .string()
    .trim()
    .min(1, 'Where is it?')
    .refine((v) => /^(https?:\/\/)?[^\s/$.?#].[^\s]*$/i.test(v), 'A web address, like https://jobs.example.com.'),
  kind: z.enum(kindOptions.map((o) => o.value) as [string, ...string[]]),
  query_note: optional,
  organization_id: z.string().nullable(),
  recurrence_rule: z.enum(recurrenceOptions.map((o) => o.value) as [string, ...string[]]),
  recurrence_interval: optional.refine(
    (v) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= MAX_RECURRENCE_INTERVAL,
    `A whole number from 1 to ${MAX_RECURRENCE_INTERVAL}.`,
  ),
  active: z.boolean(),
  notes: optional,
})

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

const toBody = (v: FormOutput): WatchCreate => ({
  name: v.name,
  // Stored as typed, with a scheme added when there is none, so it opens.
  url: /^https?:\/\//i.test(v.url) ? v.url : `https://${v.url}`,
  kind: v.kind as WatchCreate['kind'],
  query_note: v.query_note || null,
  organization_id: v.organization_id,
  recurrence_rule: v.recurrence_rule as WatchCreate['recurrence_rule'],
  recurrence_interval: Number(v.recurrence_interval),
  active: v.active,
  notes: v.notes || null,
})

export function WatchForm({
  initial,
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
}: {
  initial?: WatchRead
  onSubmit: (body: WatchCreate) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
}) {
  const { control, handleSubmit } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: initial?.name ?? '',
      url: initial?.url ?? '',
      kind: initial?.kind ?? 'job_board',
      query_note: initial?.query_note ?? '',
      organization_id: initial?.organization_id ?? null,
      recurrence_rule: initial?.recurrence_rule ?? 'weekly',
      recurrence_interval: String(initial?.recurrence_interval ?? 1),
      active: initial?.active ?? true,
      notes: initial?.notes ?? '',
    },
  })
  const rule = useWatch({ control, name: 'recurrence_rule' })
  const units = recurrenceOptions.find((o) => o.value === rule)?.units ?? 'periods'

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <div className="form-row">
        <FormTextField control={control} name="name" label="Name" autoFocus />
        <Controller
          control={control}
          name="kind"
          render={({ field }) => (
            <Select label="Kind" options={kindOptions} value={field.value as never} onChange={field.onChange} />
          )}
        />
      </div>
      <FormTextField control={control} name="url" label="Web address" type="url" placeholder="https://" />
      <FormTextField
        control={control}
        name="query_note"
        label="What to look for"
        rows={2}
        description="The search, the filter or the kind of posting — so a sweep is quick."
      />
      <Controller
        control={control}
        name="organization_id"
        render={({ field }) => (
          <OrganizationPicker
            label="Company"
            value={field.value}
            onChange={field.onChange}
            initialLabel={initial?.organization_name}
          />
        )}
      />

      <fieldset className="form-section">
        <legend>Sweep</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="recurrence_rule"
            render={({ field }) => (
              <Select
                label="Check"
                options={recurrenceOptions.map((o) => ({ value: o.value, label: o.label }))}
                value={field.value as never}
                onChange={field.onChange}
              />
            )}
          />
          <FormTextField control={control} name="recurrence_interval" label={`Every how many ${units}`} inputMode="numeric" />
        </div>
        <Controller
          control={control}
          name="active"
          render={({ field }) => (
            <Checkbox
              isSelected={field.value}
              onChange={field.onChange}
              description="Pause a source without losing its history."
            >
              Active
            </Checkbox>
          )}
        />
      </fieldset>

      <FormTextField control={control} name="notes" label="Notes" rows={3} />

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
