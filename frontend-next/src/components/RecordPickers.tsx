import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useState } from 'react'
import { contactOptionsQuery } from '../contacts'
import { organizationOptionsQuery } from '../organizations'
import { useDebounced } from '../useDebounced'
import { SearchPicker } from './ui/SearchPicker'

// Pick one contact or organization by typing part of its name, with the
// suggestions coming from the server. On an edit form the current record's
// name is passed as `initialLabel`, so the field shows it before anything is
// typed.
type PickerProps = {
  value: string | null
  onChange: (id: string | null) => void
  initialLabel?: string | null
  label?: string
  placeholder?: string
  errorMessage?: string
}

export function ContactPicker({
  value,
  onChange,
  initialLabel,
  label = 'Contact',
  placeholder = 'Type a name',
  errorMessage,
}: PickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const [text, setText] = useState(initialLabel ?? '')
  const search = useDebounced(text.trim())
  // The typed text is the name that is already chosen: show everything rather
  // than that one match, so the list is useful when it opens.
  const { data } = useQuery(contactOptionsQuery(api, value && text === initialLabel ? '' : search))
  const options = (data?.items ?? []).map((c) => ({
    id: c.id,
    label: c.name,
    description: [c.job_title, c.organization_name].filter(Boolean).join(' · ') || null,
  }))
  if (value && initialLabel && !options.some((o) => o.id === value)) options.unshift({ id: value, label: initialLabel, description: null })
  return (
    <SearchPicker
      label={label}
      placeholder={placeholder}
      options={options}
      value={value}
      onChange={onChange}
      inputValue={text}
      onInputChange={(t) => {
        setText(t)
        // Clearing the text clears the choice; otherwise a stale id would be
        // submitted behind an empty field.
        if (!t) onChange(null)
      }}
      emptyText={search ? `No contact called “${search}”.` : 'No contacts yet.'}
      errorMessage={errorMessage}
    />
  )
}

export function OrganizationPicker({
  value,
  onChange,
  initialLabel,
  label = 'Organization',
  placeholder = 'Optional',
  errorMessage,
}: PickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const [text, setText] = useState(initialLabel ?? '')
  const search = useDebounced(text.trim())
  const { data } = useQuery(organizationOptionsQuery(api, value && text === initialLabel ? '' : search))
  const options = (data?.items ?? []).map((o) => ({ id: o.id, label: o.name, description: o.domain }))
  if (value && initialLabel && !options.some((o) => o.id === value)) options.unshift({ id: value, label: initialLabel, description: null })
  return (
    <SearchPicker
      label={label}
      placeholder={placeholder}
      options={options}
      value={value}
      onChange={onChange}
      inputValue={text}
      onInputChange={(t) => {
        setText(t)
        if (!t) onChange(null)
      }}
      emptyText={search ? `No organization matches “${search}”.` : 'No organizations yet.'}
      errorMessage={errorMessage}
    />
  )
}
