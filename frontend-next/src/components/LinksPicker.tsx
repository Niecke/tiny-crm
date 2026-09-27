import { useQuery } from '@tanstack/react-query'
import { useRouteContext } from '@tanstack/react-router'
import { useRef, useState } from 'react'
import { contactOptionsQuery, contactQuery } from '../contacts'
import { dealOptionsQuery, dealQuery } from '../deals'
import { organizationOptionsQuery, organizationQuery } from '../organizations'
import { projectOptionsQuery, projectQuery } from '../projects'
import { useDebounced } from '../useDebounced'
import { Button } from './ui/Button'
import { SearchPicker } from './ui/SearchPicker'

// Many records of one type, attached to an interaction or a document: the
// chosen ones as removable chips, and a search to add another. Records only
// come back as ids, so each chip looks up its own name — through the query
// cache, so a record already seen costs nothing.
export type LinkKind = 'contact' | 'organization' | 'deal' | 'project'

const nouns: Record<LinkKind, [string, string]> = {
  contact: ['contact', 'contacts'],
  organization: ['organization', 'organizations'],
  deal: ['deal', 'deals'],
  project: ['project', 'projects'],
}

function useRecordName(kind: LinkKind, id: string): string | undefined {
  const { api } = useRouteContext({ from: '/_authed' })
  // One of four queries, picked by kind; the others are disabled.
  const contact = useQuery({ ...contactQuery(api, id), enabled: kind === 'contact', staleTime: 300_000 })
  const organization = useQuery({ ...organizationQuery(api, id), enabled: kind === 'organization', staleTime: 300_000 })
  const deal = useQuery({ ...dealQuery(api, id), enabled: kind === 'deal', staleTime: 300_000 })
  const project = useQuery({ ...projectQuery(api, id), enabled: kind === 'project', staleTime: 300_000 })
  if (kind === 'contact') return contact.data?.name ?? (contact.isError ? '(deleted)' : undefined)
  if (kind === 'organization') return organization.data?.name ?? (organization.isError ? '(deleted)' : undefined)
  if (kind === 'deal') return deal.data?.title ?? (deal.isError ? '(deleted)' : undefined)
  return project.data?.name ?? (project.isError ? '(deleted)' : undefined)
}

// A linked record's name, for a row that only has its id.
export function RecordName({ kind, id }: { kind: LinkKind; id: string }) {
  return <>{useRecordName(kind, id) ?? '…'}</>
}

function useOptions(kind: LinkKind, search: string) {
  const { api } = useRouteContext({ from: '/_authed' })
  const contacts = useQuery({ ...contactOptionsQuery(api, search), enabled: kind === 'contact' })
  const organizations = useQuery({ ...organizationOptionsQuery(api, search), enabled: kind === 'organization' })
  const deals = useQuery({ ...dealOptionsQuery(api, search), enabled: kind === 'deal' })
  const projects = useQuery({ ...projectOptionsQuery(api, search), enabled: kind === 'project' })
  if (kind === 'contact')
    return (contacts.data?.items ?? []).map((c) => ({ id: c.id, label: c.name, description: c.organization_name }))
  if (kind === 'organization')
    return (organizations.data?.items ?? []).map((o) => ({ id: o.id, label: o.name, description: o.domain }))
  if (kind === 'deal')
    return (deals.data?.items ?? []).map((d) => ({ id: d.id, label: d.title, description: d.organization_name }))
  return (projects.data?.items ?? []).map((p) => ({ id: p.id, label: p.name, description: null }))
}

export function LinksPicker({
  kind,
  value,
  onChange,
}: {
  kind: LinkKind
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const [one, many] = nouns[kind]
  const [text, setText] = useState('')
  const search = useDebounced(text.trim())
  const options = useOptions(kind, search).filter((o) => !value.includes(o.id))
  // Choosing an option makes the combobox write its label into the field
  // right after the choice; the field is for finding the next one, so that
  // write is swallowed.
  const added = useRef<string | null>(null)

  return (
    <div className="links-picker">
      <SearchPicker
        label={many[0].toUpperCase() + many.slice(1)}
        placeholder={`Link a ${one}`}
        options={options}
        value={null}
        onChange={(id) => {
          if (id && !value.includes(id)) {
            added.current = options.find((o) => o.id === id)?.label ?? null
            onChange([...value, id])
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
        emptyText={search ? `No ${one} matches “${search}”.` : `No ${many} to link.`}
      />
      {value.length > 0 && (
        <ul className="chips" aria-label={`Linked ${many}`}>
          {value.map((id) => (
            <LinkChip key={id} kind={kind} id={id} onRemove={() => onChange(value.filter((v) => v !== id))} />
          ))}
        </ul>
      )}
    </div>
  )
}

function LinkChip({ kind, id, onRemove }: { kind: LinkKind; id: string; onRemove: () => void }) {
  const name = useRecordName(kind, id)
  return (
    <li className="chip">
      <span>{name ?? '…'}</span>
      <Button variant="quiet" className="chip-remove" onPress={onRemove} aria-label={`Unlink ${name ?? kind}`}>
        ×
      </Button>
    </li>
  )
}
