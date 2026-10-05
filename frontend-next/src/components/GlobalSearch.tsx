import { useQuery } from '@tanstack/react-query'
import { useNavigate, useRouteContext } from '@tanstack/react-router'
import { type KeyboardEvent, useRef, useState } from 'react'
import {
  Button,
  ComboBox,
  Header,
  Input,
  ListBox,
  ListBoxItem,
  ListBoxSection,
  Popover,
} from 'react-aria-components'
import type { SearchHit } from '../api/types'
import { hitLink, hitMeta, isSearchable, MIN_QUERY_LENGTH, searchQuery, typeLabels } from '../search'
import { useDebounced } from '../useDebounced'

const SEE_ALL = 'see-all'
const keyOf = (hit: SearchHit) => `${hit.type}:${hit.id}`

// The one search box, in the app bar on every page (#126). Typing lists the
// best few hits of every type; picking one opens it. Enter with nothing
// picked — or the last row — opens the full results page, which keeps the
// query in its URL.
//
// React Aria's ComboBox rather than a plain field with a dropdown: arrow keys,
// Escape, the listbox roles and the announcements come with it. The query is
// the server's job, so React Aria's own filtering is switched off.
export function GlobalSearch() {
  const { api } = useRouteContext({ from: '/_authed' })
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const q = useDebounced(input.trim())
  const { data, error, isFetching } = useQuery(searchQuery(api, q))

  // Not `data` alone: for a query too short to send, it is still the hits of
  // the longer one typed before it.
  const groups = isSearchable(q) ? (data?.groups ?? []).filter((g) => g.items.length > 0) : []
  const hits = new Map(groups.flatMap((g) => g.items.map((hit) => [keyOf(hit), hit] as const)))

  function openAll() {
    const text = input.trim()
    if (!text) return
    setInput('')
    // The ComboBox never saw this Enter, so its list is still open; leaving
    // the field closes it.
    inputRef.current?.blur()
    void navigate({ to: '/search', search: { q: text } })
  }

  function open(key: string | number | null) {
    if (key === null) return
    if (key === SEE_ALL) return openAll()
    const hit = hits.get(String(key))
    if (!hit) return
    setInput('')
    void navigate(hitLink(hit))
  }

  // Enter while no row is highlighted: the ComboBox would only close its
  // list. A highlighted row is the input's aria-activedescendant, and then
  // the ComboBox's own Enter picks it.
  // What the list says while it has no rows. A failed search says so: "Nothing
  // found." would be an answer the server never gave.
  function emptyState() {
    if (!isSearchable(input))
      return <div className="listbox-empty">Type at least {MIN_QUERY_LENGTH} characters.</div>
    if (isFetching || q !== input.trim()) return <div className="listbox-empty">Searching…</div>
    if (error)
      return (
        <div className="listbox-empty global-search-error" role="alert">
          Search failed: {error.message}
        </div>
      )
    return <div className="listbox-empty">Nothing found.</div>
  }

  function onKeyDownCapture(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== 'Enter' || !(e.target instanceof HTMLInputElement)) return
    if (e.target.getAttribute('aria-activedescendant')) return
    e.preventDefault()
    e.stopPropagation()
    openAll()
  }

  return (
    <div className="global-search" role="search" onKeyDownCapture={onKeyDownCapture}>
      <ComboBox
        aria-label="Search everything"
        className="global-search-box"
        inputValue={input}
        onInputChange={setInput}
        value={null}
        onChange={open}
        defaultFilter={() => true}
        menuTrigger="input"
        allowsCustomValue
        allowsEmptyCollection
      >
        <div className="search">
          <Input ref={inputRef} className="input" placeholder="Search everything" />
          {input && (
            <Button className="search-clear" aria-label="Clear search" onPress={() => setInput('')}>
              ×
            </Button>
          )}
        </div>
        <Popover className="popover global-search-popover" offset={4} placement="bottom start">
          <ListBox className="listbox" renderEmptyState={emptyState}>
            {groups.map((group) => (
              <ListBoxSection key={group.type} id={group.type} className="global-search-section">
                <Header className="global-search-header">
                  {typeLabels[group.type]}
                  {group.total > group.items.length && <span className="muted"> · {group.total}</span>}
                </Header>
                {group.items.map((hit) => (
                  <ListBoxItem key={keyOf(hit)} id={keyOf(hit)} textValue={hit.title} className="listbox-item">
                    <span>{hit.title}</span>
                    {hitMeta(hit) && <span className="row-meta">{hitMeta(hit)}</span>}
                  </ListBoxItem>
                ))}
              </ListBoxSection>
            ))}
            {groups.length > 0 && (
              <ListBoxItem id={SEE_ALL} textValue="See all results" className="listbox-item global-search-all">
                See all results for “{input.trim()}”
              </ListBoxItem>
            )}
          </ListBox>
        </Popover>
      </ComboBox>
    </div>
  )
}
