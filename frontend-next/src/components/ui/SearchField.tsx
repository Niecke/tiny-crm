import { Button, Input, SearchField as AriaSearchField } from 'react-aria-components'

// React Aria's SearchField: Escape clears it, and the clear button is a real,
// labelled button rather than the browser's own (which differs per browser
// and is hidden in styles.css).
export function SearchField({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string
  onChange: (value: string) => void
  // Not shown — the placeholder and the page heading say what it searches —
  // but announced by screen readers.
  label: string
  placeholder?: string
}) {
  return (
    <AriaSearchField className="search" value={value} onChange={onChange} aria-label={label}>
      <Input className="input" placeholder={placeholder} />
      <Button className="search-clear" aria-label="Clear search">
        ×
      </Button>
    </AriaSearchField>
  )
}
