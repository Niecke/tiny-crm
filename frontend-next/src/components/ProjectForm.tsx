import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import type { ProjectRead } from '../api/types'
import { Button } from './ui/Button'
import { DatePicker } from './ui/DatePicker'
import { FormTextField } from './ui/FormTextField'
import { MarkdownField } from './ui/MarkdownField'

const formSchema = z
  .object({
    name: z.string().trim().min(1, 'Name is required.'),
    description: z.string().trim(),
    start_date: z.string().min(1, 'When does it start?'),
    end_date: z.string(),
  })
  .refine((v) => !v.end_date || !v.start_date || v.end_date >= v.start_date, {
    path: ['end_date'],
    message: 'Cannot end before it starts.',
  })

type FormValues = z.infer<typeof formSchema>

// Name, description and dates. What is linked to the project is managed on
// its page, not here, so saving the form never touches the links.
export type ProjectFields = { name: string; description: string | null; start_date: string; end_date: string | null }

export function ProjectForm({
  initial,
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
}: {
  initial?: ProjectRead
  onSubmit: (fields: ProjectFields) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
}) {
  const { control, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: initial?.name ?? '',
      description: initial?.description ?? '',
      start_date: initial?.start_date ?? '',
      end_date: initial?.end_date ?? '',
    },
  })

  return (
    <form
      className="panel form"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          name: v.name,
          // Sent as null when emptied, so an edit clears it — the Flutter form
          // left the old description in place.
          description: v.description || null,
          start_date: v.start_date,
          end_date: v.end_date || null,
        }),
      )}
      noValidate
    >
      <FormTextField control={control} name="name" label="Name" autoFocus />
      <Controller
        control={control}
        name="description"
        render={({ field }) => (
          <MarkdownField
            label="Description"
            value={field.value}
            onChange={field.onChange}
            onBlur={field.onBlur}
            inputRef={field.ref}
            rows={6}
          />
        )}
      />
      <div className="form-row">
        <Controller
          control={control}
          name="start_date"
          render={({ field, fieldState }) => (
            <DatePicker label="Start" value={field.value} onChange={field.onChange} errorMessage={fieldState.error?.message} />
          )}
        />
        <Controller
          control={control}
          name="end_date"
          render={({ field, fieldState }) => (
            <DatePicker
              label="End"
              value={field.value}
              onChange={field.onChange}
              description="Optional."
              errorMessage={fieldState.error?.message}
            />
          )}
        />
      </div>

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
