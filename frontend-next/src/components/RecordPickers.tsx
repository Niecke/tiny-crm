import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useState } from 'react'
import { contactOptionsQuery, notShown } from '../contacts'
import { dealOptionsQuery } from '../deals'
import { organizationOptionsQuery } from '../organizations'
import { useDebounced } from '../useDebounced'
import { type PickerOption, SearchPicker } from './ui/SearchPicker'

// Pick one contact or organization by typing part of its name, with the
// suggestions coming from the server. On an edit form the current record's
// name is passed as `initialLabel`, so the field shows it before anything is
// typed. It is read once: a caller whose chosen record changes underneath the
// picker remounts it with a `key`, so the label and the id cannot drift apart.
type PickerProps = {
  value: string | null
  onChange: (id: string | null) => void
  initialLabel?: string | null
  label?: string
  placeholder?: string
  errorMessage?: string
}

function useRecordPickerState(initialLabel?: string | null) {
  const [text, setText] = useState(initialLabel ?? '')
  const [selectedLabel, setSelectedLabel] = useState(initialLabel ?? '')

  const onSelect = (id: string | null, options: PickerOption[], onChange: (id: string | null) => void) => {
    onChange(id)
    if (!id) {
      setSelectedLabel('')
      setText('')
    } else {
      const match = options.find((o) => o.id === id)
      if (match) {
        setSelectedLabel(match.label)
        setText(match.label)
      }
    }
  }

  const onInput = (t: string, onChange: (id: string | null) => void) => {
    setText(t)
    if (!t) {
      setSelectedLabel('')
      onChange(null)
    }
  }

  return { text, selectedLabel, onSelect, onInput }
}

export function ContactPicker({
  value,
  onChange,
  initialLabel,
  label = 'Contact',
  placeholder = 'Search contacts',
  errorMessage,
}: PickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const { text, selectedLabel, onSelect, onInput } = useRecordPickerState(initialLabel)
  const search = useDebounced(text.trim())
  // The typed text is the name that is already chosen: show everything rather
  // than that one match, so the list is useful when it opens.
  const { data } = useQuery(contactOptionsQuery(api, value && text === selectedLabel ? '' : search))
  const options = (data?.items ?? []).map((c) => ({
    id: c.id,
    label: c.name,
    description: [c.job_title, c.organization_name].filter(Boolean).join(' · ') || null,
  }))
  if (value && selectedLabel && !options.some((o) => o.id === value)) {
    options.unshift({ id: value, label: selectedLabel, description: null })
  }
  return (
    <SearchPicker
      label={label}
      placeholder={placeholder}
      options={options}
      more={notShown(data)}
      value={value}
      onChange={(id) => onSelect(id, options, onChange)}
      inputValue={text}
      onInputChange={(t) => onInput(t, onChange)}
      emptyText={search ? `No contact matches “${search}”.` : 'No contacts yet.'}
      errorMessage={errorMessage}
    />
  )
}

export function OrganizationPicker({
  value,
  onChange,
  initialLabel,
  label = 'Organization',
  placeholder = 'Search organizations',
  errorMessage,
}: PickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const { text, selectedLabel, onSelect, onInput } = useRecordPickerState(initialLabel)
  const search = useDebounced(text.trim())
  const { data } = useQuery(organizationOptionsQuery(api, value && text === selectedLabel ? '' : search))
  const options = (data?.items ?? []).map((o) => ({ id: o.id, label: o.name, description: o.domain }))
  if (value && selectedLabel && !options.some((o) => o.id === value)) {
    options.unshift({ id: value, label: selectedLabel, description: null })
  }
  return (
    <SearchPicker
      label={label}
      placeholder={placeholder}
      options={options}
      more={notShown(data)}
      value={value}
      onChange={(id) => onSelect(id, options, onChange)}
      inputValue={text}
      onInputChange={(t) => onInput(t, onChange)}
      emptyText={search ? `No organization matches “${search}”.` : 'No organizations yet.'}
      errorMessage={errorMessage}
    />
  )
}

export function DealPicker({
  value,
  onChange,
  initialLabel,
  label = 'Deal',
  placeholder = 'Search deals',
  errorMessage,
}: PickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const { text, selectedLabel, onSelect, onInput } = useRecordPickerState(initialLabel)
  const search = useDebounced(text.trim())
  const { data } = useQuery(dealOptionsQuery(api, value && text === selectedLabel ? '' : search))
  const options = (data?.items ?? []).map((d) => ({
    id: d.id,
    label: d.title,
    description: [d.organization_name, d.contact_name, d.stage].filter(Boolean).join(' · ') || null,
  }))
  if (value && selectedLabel && !options.some((o) => o.id === value)) {
    options.unshift({ id: value, label: selectedLabel, description: null })
  }
  return (
    <SearchPicker
      label={label}
      placeholder={placeholder}
      options={options}
      more={notShown(data)}
      value={value}
      onChange={(id) => onSelect(id, options, onChange)}
      inputValue={text}
      onInputChange={(t) => onInput(t, onChange)}
      emptyText={search ? `No deal matches “${search}”.` : 'No deals yet.'}
      errorMessage={errorMessage}
    />
  )
}
