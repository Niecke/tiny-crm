import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import type { TaskCreate, TaskRead } from '../api/types'

// What the form edits: everything but `done`, which is ticked off in lists
// and on the task's page, never in the form.
export type TaskFields = Omit<TaskCreate, 'done'>
import { endOfLocalDay, localDay, splitTags } from '../format'
import { MAX_RECURRENCE_INTERVAL, priorityOptions, recurrenceOptions } from '../tasks'
import { ContactPicker, DealPicker } from './RecordPickers'
import { Button } from './ui/Button'
import { DatePicker } from './ui/DatePicker'
import { FormTextField } from './ui/FormTextField'
import { MarkdownField } from './ui/MarkdownField'
import { Segmented } from './ui/Segmented'
import { Select } from './ui/Select'

const optional = z.string().trim()

// The backend's rules (schemas/task.py, validate_recurrence), checked here so
// they are reported on the field instead of coming back as a 422.
const formSchema = z
  .object({
    title: z.string().trim().min(1, 'Title is required.'),
    description: optional,
    due: z.string(),
    rule: z.enum(['', ...recurrenceOptions.map((o) => o.value)]),
    interval: optional.refine(
      (v) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= MAX_RECURRENCE_INTERVAL,
      `A whole number from 1 to ${MAX_RECURRENCE_INTERVAL}.`,
    ),
    until: z.string(),
    contact_id: z.string().nullable(),
    deal_id: z.string().nullable(),
    interaction_id: z.string().nullable(),
    priority: z.enum(['0', '1', '2']),
    tags: optional,
  })
  .refine((v) => !v.rule || v.due, { path: ['due'], message: 'A repeating task needs a due date to repeat from.' })
  .refine((v) => !v.rule || !v.until || !v.due || v.until >= v.due, {
    path: ['until'],
    message: 'Cannot end before the due date.',
  })

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

// Every field is sent. The links and the recurrence rule go as null when
// empty — that is how a link is removed and a repeat switched off — and an
// emptied description is cleared rather than left as it was.
const toBody = (v: FormOutput): TaskFields => ({
  title: v.title,
  description: v.description || null,
  due_date: v.due ? endOfLocalDay(v.due) : null,
  recurrence_rule: v.rule || null,
  recurrence_interval: v.rule ? Number(v.interval) : 1,
  recurrence_until: v.rule && v.until ? endOfLocalDay(v.until) : null,
  contact_id: v.contact_id,
  deal_id: v.deal_id,
  interaction_id: v.interaction_id,
  priority: Number(v.priority),
  tags: splitTags(v.tags),
})

export type TaskLinks = {
  contact?: { id: string; name: string }
  deal?: { id: string; title: string }
  interaction?: { id: string; subject: string }
}

const toDefaults = (t: TaskRead | undefined, links: TaskLinks): FormInput => ({
  title: t?.title ?? '',
  description: t?.description ?? '',
  due: t?.due_date ? localDay(t.due_date) : '',
  rule: t?.recurrence_rule ?? '',
  interval: String(t?.recurrence_interval ?? 1),
  until: t?.recurrence_until ? localDay(t.recurrence_until) : '',
  contact_id: t ? (t.contact_id ?? null) : (links.contact?.id ?? null),
  deal_id: t ? (t.deal_id ?? null) : (links.deal?.id ?? null),
  interaction_id: t ? (t.interaction_id ?? null) : (links.interaction?.id ?? null),
  priority: String(Math.min(2, Math.max(0, t?.priority ?? 0))) as '0' | '1' | '2',
  tags: t?.tags.join(', ') ?? '',
})

export function TaskForm({
  initial,
  links = {},
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
  extraActions,
}: {
  // Absent for a new task.
  initial?: TaskRead
  // Preselected on a new task opened from a contact, deal or interaction.
  links?: TaskLinks
  onSubmit: (body: TaskFields) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
  // Left of Cancel: Delete, on an existing task.
  extraActions?: ReactNode
}) {
  const { control, handleSubmit, setValue } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial, links),
  })
  const rule = useWatch({ control, name: 'rule' })
  const interactionId = useWatch({ control, name: 'interaction_id' })
  const unit = recurrenceOptions.find((o) => o.value === rule)
  const interactionSubject = initial?.interaction_subject ?? links.interaction?.subject

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <FormTextField control={control} name="title" label="Title" autoFocus />

      <Controller
        control={control}
        name="description"
        render={({ field }) => (
          <MarkdownField
            label="Description"
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            inputRef={field.ref}
            rows={4}
          />
        )}
      />

      <div className="form-row">
        <Controller
          control={control}
          name="due"
          render={({ field, fieldState }) => (
            <DatePicker
              label="Due"
              value={field.value}
              onChange={field.onChange}
              description="Due by the end of that day."
              errorMessage={fieldState.error?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="priority"
          render={({ field }) => (
            <div className="field">
              <span className="field-label" aria-hidden="true">
                Priority
              </span>
              <Segmented
                label="Priority"
                value={field.value}
                onChange={field.onChange}
                options={priorityOptions.map((o) => ({ value: o.value, label: o.label }))}
              />
            </div>
          )}
        />
      </div>

      <fieldset className="form-section">
        <legend>Repeats</legend>
        <Controller
          control={control}
          name="rule"
          render={({ field }) => (
            <Select
              label="Repeats"
              emptyLabel="Does not repeat"
              options={recurrenceOptions.map((o) => ({ value: o.value, label: o.label }))}
              value={field.value}
              onChange={(v) => {
                field.onChange(v)
                // No end date without a repeat: the API refuses one.
                if (!v) setValue('until', '')
              }}
            />
          )}
        />
        {rule && (
          <div className="form-row">
            <FormTextField
              control={control}
              name="interval"
              label={`Every how many ${unit?.units ?? 'periods'}`}
              inputMode="numeric"
            />
            <Controller
              control={control}
              name="until"
              render={({ field, fieldState }) => (
                <DatePicker
                  label="Repeat until"
                  value={field.value}
                  onChange={field.onChange}
                  description="Optional."
                  errorMessage={fieldState.error?.message}
                />
              )}
            />
          </div>
        )}
        {rule && <p className="muted small">Ticking it off creates the next one.</p>}
      </fieldset>

      <fieldset className="form-section">
        <legend>About</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="contact_id"
            render={({ field }) => (
              <ContactPicker
                label="Contact"
                placeholder="Optional"
                value={field.value}
                onChange={field.onChange}
                initialLabel={initial?.contact_name ?? links.contact?.name}
              />
            )}
          />
          <Controller
            control={control}
            name="deal_id"
            render={({ field }) => (
              <DealPicker
                value={field.value}
                onChange={field.onChange}
                initialLabel={initial?.deal_title ?? links.deal?.title}
              />
            )}
          />
        </div>
        {interactionId && (
          <div className="follow-up">
            <span className="row-main">
              <span className="field-label">Following up on</span>
              <span>{interactionSubject ?? 'an interaction'}</span>
            </span>
            <Button variant="quiet" onPress={() => setValue('interaction_id', null, { shouldDirty: true })}>
              Detach
            </Button>
          </div>
        )}
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
