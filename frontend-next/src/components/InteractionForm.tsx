import { zodResolver } from '@hookform/resolvers/zod'
import { type ReactNode, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import type { InteractionCreate, InteractionRead } from '../api/types'
import { fromLocalDateTime, splitTags, toLocalDateTime } from '../format'
import { kindOptions } from '../interactions'
import { type LinkKind, LinksPicker } from './LinksPicker'
import { Button } from './ui/Button'
import { Checkbox } from './ui/Checkbox'
import { DatePicker } from './ui/DatePicker'
import { FormTextField } from './ui/FormTextField'
import { MarkdownField } from './ui/MarkdownField'
import { Select } from './ui/Select'

const optional = z.string().trim()

const formSchema = z.object({
  kind: z.enum(kindOptions.map((o) => o.value) as [string, ...string[]]),
  subject: z.string().trim().min(1, 'Subject is required.'),
  notes: optional,
  when: z.string().min(1, 'When did it happen, or when will it?'),
  duration: optional.refine((v) => v === '' || /^\d+$/.test(v), 'Whole minutes, or leave it empty.'),
  done: z.boolean(),
  tags: optional,
  contact_ids: z.array(z.string()),
  organization_ids: z.array(z.string()),
  deal_ids: z.array(z.string()),
  project_ids: z.array(z.string()),
})

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

// Every field is sent, and the link lists whole: they replace what is stored,
// so a record unlinked in the form is unlinked on the server.
const toBody = (v: FormOutput): InteractionCreate => ({
  kind: v.kind as InteractionCreate['kind'],
  subject: v.subject,
  notes: v.notes || null,
  occurred_at: fromLocalDateTime(v.when),
  duration_minutes: v.duration ? Number(v.duration) : null,
  done: v.done,
  tags: splitTags(v.tags),
  contact_ids: v.contact_ids,
  organization_ids: v.organization_ids,
  deal_ids: v.deal_ids,
  project_ids: v.project_ids,
})

export type InteractionPreset = Partial<Record<`${LinkKind}_id`, string>>

const nowLocal = () => toLocalDateTime(new Date().toISOString())

const toDefaults = (i: InteractionRead | undefined, preset: InteractionPreset): FormInput => ({
  kind: i?.kind ?? 'note',
  subject: i?.subject ?? '',
  notes: i?.notes ?? '',
  when: i ? toLocalDateTime(i.occurred_at) : nowLocal(),
  duration: i?.duration_minutes != null ? String(i.duration_minutes) : '',
  // A new entry for now has happened; one moved into the future has not.
  done: i?.done ?? true,
  tags: i?.tags.join(', ') ?? '',
  contact_ids: i?.contact_ids ?? (preset.contact_id ? [preset.contact_id] : []),
  organization_ids: i?.organization_ids ?? (preset.organization_id ? [preset.organization_id] : []),
  deal_ids: i?.deal_ids ?? (preset.deal_id ? [preset.deal_id] : []),
  project_ids: i?.project_ids ?? (preset.project_id ? [preset.project_id] : []),
})

export function InteractionForm({
  initial,
  preset = {},
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
  extraActions,
}: {
  initial?: InteractionRead
  // A new entry opened from a record page starts linked to that record.
  preset?: InteractionPreset
  onSubmit: (body: InteractionCreate) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
  extraActions?: ReactNode
}) {
  const { control, handleSubmit, setValue, getFieldState } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial, preset),
  })
  const when = useWatch({ control, name: 'when' })
  // Fixed when the form opens, so the hint does not flip while typing.
  const [now] = useState(() => Date.now())
  const future = when ? Date.parse(fromLocalDateTime(when)) > now : false

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <div className="form-row">
        <Controller
          control={control}
          name="kind"
          render={({ field }) => (
            <Select label="Kind" options={kindOptions} value={field.value as never} onChange={field.onChange} />
          )}
        />
        <Controller
          control={control}
          name="when"
          render={({ field, fieldState }) => (
            <DatePicker
              label="When"
              withTime
              value={field.value}
              onChange={(v) => {
                field.onChange(v)
                // Planned or logged follows the time, until the checkbox is
                // set by hand.
                if (v && !getFieldState('done').isDirty) {
                  setValue('done', Date.parse(fromLocalDateTime(v)) <= Date.now())
                }
              }}
              description={
                future
                  ? 'In the future — this is a planned interaction.'
                  : 'In the past — this goes into the activity log.'
              }
              errorMessage={fieldState.error?.message}
            />
          )}
        />
      </div>

      <FormTextField control={control} name="subject" label="Subject" autoFocus />

      <Controller
        control={control}
        name="notes"
        render={({ field }) => (
          <MarkdownField
            label="Notes"
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            inputRef={field.ref}
            rows={5}
          />
        )}
      />

      <div className="form-row">
        <FormTextField control={control} name="duration" label="Duration (minutes)" inputMode="numeric" />
        <Controller
          control={control}
          name="done"
          render={({ field }) => (
            <div className="field field-checkbox">
              <Checkbox
                isSelected={field.value}
                onChange={(v) => setValue('done', v, { shouldDirty: true })}
                description="A planned call that took place, or a note on something done."
              >
                Happened
              </Checkbox>
            </div>
          )}
        />
      </div>

      <fieldset className="form-section">
        <legend>With and about</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="contact_ids"
            render={({ field }) => <LinksPicker kind="contact" value={field.value} onChange={field.onChange} />}
          />
          <Controller
            control={control}
            name="organization_ids"
            render={({ field }) => (
              <LinksPicker kind="organization" value={field.value} onChange={field.onChange} />
            )}
          />
        </div>
        <div className="form-row">
          <Controller
            control={control}
            name="deal_ids"
            render={({ field }) => <LinksPicker kind="deal" value={field.value} onChange={field.onChange} />}
          />
          <Controller
            control={control}
            name="project_ids"
            render={({ field }) => <LinksPicker kind="project" value={field.value} onChange={field.onChange} />}
          />
        </div>
        <FormTextField control={control} name="tags" label="Tags" description="Separated by commas." />
      </fieldset>

      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}

      <div className="form-actions">
        {extraActions && <span className="form-actions-start">{extraActions}</span>}
        {cancel}
        <Button type="submit" isDisabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  )
}
