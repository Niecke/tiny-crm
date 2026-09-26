import {
  Button,
  ComboBox,
  FieldError,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
} from 'react-aria-components'

export type PickerOption = { id: string; label: string; description?: string | null }

// Pick one record by typing part of its name: React Aria's ComboBox with the
// suggestions coming from the server. Passing `items` switches off React
// Aria's own filtering, so the caller's search is the only filter; the caller
// owns the typed text (to query with) and the chosen id (to submit).
export function SearchPicker({
  label,
  options,
  value,
  onChange,
  inputValue,
  onInputChange,
  placeholder,
  emptyText = 'No matches.',
  errorMessage,
}: {
  label: string
  options: PickerOption[]
  value: string | null
  onChange: (id: string | null) => void
  inputValue: string
  onInputChange: (text: string) => void
  placeholder?: string
  emptyText?: string
  errorMessage?: string
}) {
  return (
    <ComboBox
      className="field"
      items={options}
      value={value}
      onChange={(key) => onChange(key === null ? null : String(key))}
      inputValue={inputValue}
      onInputChange={onInputChange}
      menuTrigger="focus"
      allowsEmptyCollection
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
    >
      <Label className="field-label">{label}</Label>
      <div className="picker">
        <Input className="input" placeholder={placeholder} />
        <Button className="picker-button" aria-label={`Show ${label.toLowerCase()} suggestions`}>
          ▾
        </Button>
      </div>
      <FieldError className="field-error">{errorMessage}</FieldError>
      <Popover className="popover" offset={4}>
        <ListBox className="listbox" renderEmptyState={() => <div className="listbox-empty">{emptyText}</div>}>
          {(option: PickerOption) => (
            <ListBoxItem id={option.id} textValue={option.label} className="listbox-item">
              <span>{option.label}</span>
              {option.description && <span className="row-meta">{option.description}</span>}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </ComboBox>
  )
}
