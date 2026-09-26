import { type Ref, useState } from 'react'
import { Markdown } from '../Markdown'
import { Segmented } from './Segmented'
import { TextField } from './TextField'

// A Markdown text with a preview: write, then check how it reads. The preview
// replaces the textarea at the same height, so the form does not jump.
export function MarkdownField({
  label,
  value,
  onChange,
  onBlur,
  inputRef,
  rows = 6,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  inputRef?: Ref<HTMLInputElement & HTMLTextAreaElement>
  rows?: number
}) {
  const [mode, setMode] = useState<'write' | 'preview'>('write')
  return (
    <div className="markdown-field">
      {/* Top right, level with the field's label. */}
      <div className="markdown-field-toggle">
        <Segmented
          label={`${label}: write or preview`}
          value={mode}
          onChange={setMode}
          options={[
            { value: 'write', label: 'Write' },
            { value: 'preview', label: 'Preview' },
          ]}
        />
      </div>
      {mode === 'write' ? (
        <TextField
          label={label}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          inputRef={inputRef}
          rows={rows}
          description="Markdown: **bold**, *italic*, - lists, [links](https://…)."
        />
      ) : (
        <div className="field">
          <span className="field-label">{label}</span>
          <div className="markdown-preview" style={{ minHeight: `${rows * 1.5 + 1}rem` }}>
            {value.trim() ? <Markdown>{value}</Markdown> : <p className="muted">Nothing to preview.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
