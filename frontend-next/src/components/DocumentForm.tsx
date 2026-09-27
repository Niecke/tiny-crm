import { zodResolver } from '@hookform/resolvers/zod'
import { type ReactNode, useState } from 'react'
import { FileTrigger } from 'react-aria-components'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import type { DocumentRead } from '../api/types'
import { ACCEPTED_TYPES, MAX_BYTES } from '../documents'
import { formatBytes, splitTags } from '../format'
import { LinksPicker } from './LinksPicker'
import { Button } from './ui/Button'
import { FormTextField } from './ui/FormTextField'

const formSchema = z.object({
  title: z.string().trim().min(1, 'Title is required.'),
  description: z.string().trim(),
  tags: z.string().trim(),
  contact_ids: z.array(z.string()),
  organization_ids: z.array(z.string()),
  deal_ids: z.array(z.string()),
  project_ids: z.array(z.string()),
})

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

export type DocumentFields = {
  title: string
  description: string | null
  tags: string[]
  contact_ids: string[]
  organization_ids: string[]
  deal_ids: string[]
  project_ids: string[]
}

export type DocumentPreset = Partial<Record<'contact_id' | 'organization_id' | 'deal_id' | 'project_id', string>>

const toDefaults = (d: DocumentRead | undefined, preset: DocumentPreset): FormInput => ({
  title: d?.title ?? '',
  description: d?.description ?? '',
  tags: d?.tags.join(', ') ?? '',
  contact_ids: d?.contact_ids ?? (preset.contact_id ? [preset.contact_id] : []),
  organization_ids: d?.organization_ids ?? (preset.organization_id ? [preset.organization_id] : []),
  deal_ids: d?.deal_ids ?? (preset.deal_id ? [preset.deal_id] : []),
  project_ids: d?.project_ids ?? (preset.project_id ? [preset.project_id] : []),
})

// Upload (with a file) or edit a document's details (without). The details are
// the same either way: a title, a description, tags, and the records it is
// filed under.
export function DocumentForm({
  initial,
  preset = {},
  withFile,
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
  extraActions,
}: {
  initial?: DocumentRead
  preset?: DocumentPreset
  // Upload mode: a file must be chosen, and its name pre-fills the title.
  withFile?: boolean
  onSubmit: (fields: DocumentFields, file: File | null) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
  extraActions?: ReactNode
}) {
  const { control, handleSubmit, getValues, setValue } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial, preset),
  })
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  return (
    <form
      className="panel form"
      onSubmit={(e) => {
        // Checked alongside the fields, so a missing file and a missing title
        // are both reported at once.
        if (withFile && !file) setFileError('Choose a file to upload.')
        void handleSubmit((v) => {
          if (withFile && !file) return
          onSubmit(
          {
            title: v.title,
            description: v.description || null,
            tags: splitTags(v.tags),
            contact_ids: v.contact_ids,
            organization_ids: v.organization_ids,
            deal_ids: v.deal_ids,
            project_ids: v.project_ids,
          },
          file,
        )
        })(e)
      }}
      noValidate
    >
      {withFile && (
        <FilePicker
          file={file}
          error={fileError}
          onChange={(f, problem) => {
            setFile(f)
            setFileError(problem)
            // The file's name, less its extension, is the usual title.
            if (f && !getValues('title')) setValue('title', f.name.replace(/\.[^.]+$/, ''))
          }}
        />
      )}

      <FormTextField control={control} name="title" label="Title" autoFocus={!withFile} />
      <FormTextField control={control} name="description" label="Description" rows={3} />
      <FormTextField control={control} name="tags" label="Tags" description="Separated by commas." />

      <fieldset className="form-section">
        <legend>Filed under</legend>
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

// One file, checked here for type and size so a wrong pick is caught before
// 25 MB goes over the wire.
export function FilePicker({
  file,
  error,
  onChange,
  label = 'File',
}: {
  file: File | null
  error: string | null
  onChange: (file: File | null, problem: string | null) => void
  label?: string
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="file-picker" data-invalid={error ? true : undefined}>
        <FileTrigger
          acceptedFileTypes={ACCEPTED_TYPES}
          onSelect={(list) => {
            const f = list?.[0] ?? null
            if (!f) return
            if (!/\.(pdf|md|markdown|txt)$/i.test(f.name)) onChange(null, 'Only PDF, Markdown and text files.')
            else if (f.size > MAX_BYTES) onChange(null, `Larger than ${formatBytes(MAX_BYTES)}.`)
            else onChange(f, null)
          }}
        >
          <Button variant="quiet">{file ? 'Choose another file' : 'Choose a file'}</Button>
        </FileTrigger>
        <span className={file ? undefined : 'muted'}>
          {file ? `${file.name} · ${formatBytes(file.size)}` : 'PDF, Markdown or text, up to 25 MB.'}
        </span>
      </div>
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
