import {
  Button,
  FieldError,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Select as AriaSelect,
  SelectValue,
} from 'react-aria-components'

// One choice from a short, fixed list: React Aria's Select, a button that
// opens a listbox, with type-ahead and arrow keys. `''` is the "nothing
// chosen" value, so a form field can hold it as a plain string and send null.
export type SelectOption<T extends string> = { value: T; label: string }

export function Select<T extends string>({
  label,
  options,
  value,
  onChange,
  emptyLabel,
  errorMessage,
  hideLabel,
}: {
  label: string
  options: SelectOption<T>[]
  value: T | ''
  onChange: (value: T | '') => void
  // Offered as the first option when set; without it the field has no
  // "nothing" choice once something is picked.
  emptyLabel?: string
  errorMessage?: string
  // For a filter in a toolbar, where the options say what it is.
  hideLabel?: boolean
}) {
  const items: SelectOption<T | ''>[] = emptyLabel ? [{ value: '', label: emptyLabel }, ...options] : options
  return (
    <AriaSelect
      className="field"
      selectedKey={value}
      onSelectionChange={(key) => onChange((key ?? '') as T | '')}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      aria-label={hideLabel ? label : undefined}
    >
      {!hideLabel && <Label className="field-label">{label}</Label>}
      <Button className="input select-button">
        <SelectValue className="select-value" />
        <span aria-hidden="true" className="muted">
          ▾
        </span>
      </Button>
      <FieldError className="field-error">{errorMessage}</FieldError>
      <Popover className="popover" offset={4}>
        <ListBox className="listbox" items={items}>
          {(o) => (
            <ListBoxItem id={o.value} textValue={o.label} className="listbox-item">
              {o.label}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </AriaSelect>
  )
}
