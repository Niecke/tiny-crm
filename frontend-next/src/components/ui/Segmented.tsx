import { Radio, RadioGroup } from 'react-aria-components'

// A choice between a few options that are all visible at once, built on React
// Aria's RadioGroup: arrow keys move the selection, and it announces as a
// group of radio buttons.
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <RadioGroup
      className="segmented"
      aria-label={label}
      orientation="horizontal"
      value={value}
      onChange={(next) => onChange(next as T)}
    >
      {options.map((o) => (
        <Radio key={o.value} value={o.value} className="segment">
          {o.label}
        </Radio>
      ))}
    </RadioGroup>
  )
}
