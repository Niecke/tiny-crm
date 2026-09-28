import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useRef, useState } from 'react'
import { contactOptionsQuery } from '../contacts'
import { documentOptionsQuery } from '../documents'
import { taskOptionsQuery } from '../tasks'
import { useDebounced } from '../useDebounced'
import { SearchPicker } from './ui/SearchPicker'

// Search for a record to link to the one on screen; picking one links it, and
// the field clears for the next. Records already linked are not offered.
type Kind = 'contact' | 'task' | 'document'

const nouns: Record<Kind, string> = { contact: 'contact', task: 'task', document: 'document' }

export function AddLinkPicker({
  kind,
  exclude,
  onAdd,
  isDisabled,
}: {
  kind: Kind
  exclude: string[]
  onAdd: (id: string) => void
  isDisabled?: boolean
}) {
  const { api } = useRouteContext({ from: '/_authed' })
  const [text, setText] = useState('')
  const search = useDebounced(text.trim())
  const contacts = useQuery({ ...contactOptionsQuery(api, search), enabled: kind === 'contact' })
  const tasks = useQuery({ ...taskOptionsQuery(api, search), enabled: kind === 'task' })
  const documents = useQuery({ ...documentOptionsQuery(api, search), enabled: kind === 'document' })
  const options = (
    kind === 'contact'
      ? (contacts.data?.items ?? []).map((c) => ({ id: c.id, label: c.name, description: c.organization_name }))
      : kind === 'task'
        ? (tasks.data?.items ?? []).map((t) => ({ id: t.id, label: t.title, description: t.contact_name }))
        : (documents.data?.items ?? []).map((d) => ({ id: d.id, label: d.title, description: d.format }))
  ).filter((o) => !exclude.includes(o.id))
  // The combobox writes the chosen label into the field right after the
  // choice; the field is for finding the next one, so that write is swallowed.
  const added = useRef<string | null>(null)
  const noun = nouns[kind]

  return (
    <div className="add-link" aria-disabled={isDisabled || undefined}>
      <SearchPicker
        label={`Link a ${noun}`}
        placeholder={`Search ${noun}s to link`}
        options={options}
        value={null}
        onChange={(id) => {
          if (id && !isDisabled) {
            added.current = options.find((o) => o.id === id)?.label ?? null
            onAdd(id)
          }
          setText('')
        }}
        inputValue={text}
        onInputChange={(t) => {
          if (added.current !== null && t === added.current) {
            added.current = null
            return
          }
          added.current = null
          setText(t)
        }}
        emptyText={search ? `No ${noun} matches “${search}”.` : `Nothing left to link.`}
      />
    </div>
  )
}
