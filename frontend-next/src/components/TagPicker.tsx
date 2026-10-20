import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useRef, useState } from 'react'
import {
  Button as AriaButton,
  ComboBox,
  FieldError,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Text,
} from 'react-aria-components'
import { type Control, Controller, type FieldValues, type Path } from 'react-hook-form'
import { splitTags } from '../format'
import { tagsQuery } from '../tags'
import { Button } from './ui/Button'

export type TagOption = {
  id: string
  label: string
  isNew?: boolean
  tag: string
}

export type TagPickerProps = {
  label?: string
  placeholder?: string
  description?: string
  errorMessage?: string
  value: string[]
  onChange: (tags: string[]) => void
}

export function TagPicker({
  label = 'Tags',
  placeholder = 'Add a tag…',
  description,
  errorMessage,
  value,
  onChange,
}: TagPickerProps) {
  const { api } = useRouteContext({ from: '/_authed' })
  const { data: allTags = [] } = useQuery(tagsQuery(api))
  const [text, setText] = useState('')
  const added = useRef<string | null>(null)

  const query = text.trim()
  const queryLower = query.toLowerCase()

  // Existing tags from server not currently selected (case-insensitive)
  const availableExisting = allTags.filter((t) => !value.some((v) => v.toLowerCase() === t.toLowerCase()))

  const matchingExisting = query
    ? availableExisting.filter((t) => t.toLowerCase().includes(queryLower))
    : availableExisting

  const options: TagOption[] = matchingExisting.map((t) => ({
    id: `tag:${t}`,
    label: t,
    tag: t,
  }))

  const isAlreadySelected = value.some((v) => v.toLowerCase() === queryLower)
  const isExactExistingMatch = availableExisting.some((t) => t.toLowerCase() === queryLower)

  if (query && !isAlreadySelected && !isExactExistingMatch) {
    options.push({
      id: `new:${query}`,
      label: `Add “${query}”`,
      isNew: true,
      tag: query,
    })
  }

  const addTag = (newTag: string) => {
    const trimmed = newTag.trim()
    if (!trimmed) return
    if (!value.some((v) => v.toLowerCase() === trimmed.toLowerCase())) {
      onChange([...value, trimmed])
    }
    setText('')
  }

  const removeTag = (tagToRemove: string) => {
    onChange(value.filter((v) => v.toLowerCase() !== tagToRemove.toLowerCase()))
  }

  const handleInputChange = (t: string) => {
    if (added.current !== null && (t === added.current || t === '')) {
      added.current = null
      setText('')
      return
    }
    added.current = null

    if (t.includes(',')) {
      const parts = t.split(',')
      const last = parts.pop() ?? ''
      const toAdd = parts.map((p) => p.trim()).filter(Boolean)
      if (toAdd.length > 0) {
        const next = [...value]
        for (const tag of toAdd) {
          if (!next.some((v) => v.toLowerCase() === tag.toLowerCase())) {
            next.push(tag)
          }
        }
        onChange(next)
      }
      setText(last.trimStart())
      return
    }

    setText(t)
  }

  const handleSelectionChange = (key: string | number | null) => {
    if (!key) return
    const keyStr = String(key)
    const match = options.find((o) => o.id === keyStr)
    if (match) {
      added.current = match.label
      addTag(match.tag)
    }
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === ',') {
      e.preventDefault()
      if (text.trim()) {
        addTag(text.trim())
      }
    } else if (e.key === 'Enter') {
      const activeDescendant = e.currentTarget.getAttribute('aria-activedescendant')
      if (!activeDescendant && text.trim()) {
        e.preventDefault()
        addTag(text.trim())
      }
    } else if (e.key === 'Backspace' && text === '' && value.length > 0) {
      e.preventDefault()
      removeTag(value[value.length - 1])
    }
  }

  return (
    <div className="links-picker">
      <ComboBox
        className="field"
        items={options}
        selectedKey={null}
        onSelectionChange={handleSelectionChange}
        inputValue={text}
        onInputChange={handleInputChange}
        menuTrigger="focus"
        allowsEmptyCollection
        isInvalid={Boolean(errorMessage)}
        validationBehavior="aria"
      >
        <Label className="field-label">{label}</Label>
        <div className="picker">
          <Input
            className="input"
            placeholder={placeholder}
            onKeyDown={handleKeyDown}
            onBlur={() => addTag(text)}
          />
          <AriaButton className="picker-button" aria-label={`Show ${label.toLowerCase()} suggestions`}>
            <span aria-hidden="true">▾</span>
          </AriaButton>
        </div>
        {description && !errorMessage && (
          <Text slot="description" className="field-description">
            {description}
          </Text>
        )}
        <FieldError className="field-error">{errorMessage}</FieldError>
        <Popover className="popover" offset={4}>
          <ListBox
            className="listbox"
            renderEmptyState={() => (
              <div className="listbox-empty">
                {query ? `Press Enter to add “${query}”` : 'No tags yet.'}
              </div>
            )}
          >
            {(option: TagOption) => (
              <ListBoxItem id={option.id} textValue={option.label} className="listbox-item">
                <span>{option.label}</span>
              </ListBoxItem>
            )}
          </ListBox>
        </Popover>
      </ComboBox>
      {value.length > 0 && (
        <ul className="chips" aria-label={label}>
          {value.map((tag) => (
            <li key={tag} className="chip">
              <span>{tag}</span>
              <Button
                variant="quiet"
                className="chip-remove"
                onPress={() => removeTag(tag)}
                aria-label={`Remove tag ${tag}`}
              >
                ×
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type FormTagPickerProps<TIn extends FieldValues, TOut extends FieldValues> = {
  control: Control<TIn, unknown, TOut>
  name: Path<TIn>
  label?: string
  description?: string
  placeholder?: string
}

export function FormTagPicker<TIn extends FieldValues, TOut extends FieldValues>({
  control,
  name,
  label = 'Tags',
  description,
  placeholder,
}: FormTagPickerProps<TIn, TOut>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const tags = splitTags(field.value ?? '')
        return (
          <TagPicker
            label={label}
            description={description}
            placeholder={placeholder}
            value={tags}
            onChange={(next) => {
              field.onChange(next.join(', '))
            }}
            errorMessage={fieldState.error?.message}
          />
        )
      }}
    />
  )
}
