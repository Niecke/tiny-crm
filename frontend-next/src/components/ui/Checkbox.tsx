import type { ReactNode } from 'react'
import { Checkbox as AriaCheckbox } from 'react-aria-components'

// React Aria's Checkbox: a real, visually hidden <input type="checkbox"> under
// our own box, so it toggles with Space and reads correctly to screen readers.
export function Checkbox({
  isSelected,
  onChange,
  children,
  description,
}: {
  isSelected: boolean
  onChange: (isSelected: boolean) => void
  children: ReactNode
  description?: string
}) {
  return (
    <AriaCheckbox className="checkbox" isSelected={isSelected} onChange={onChange}>
      <span className="checkbox-box" aria-hidden="true">
        ✓
      </span>
      <span className="checkbox-text">
        <span>{children}</span>
        {description && <span className="row-meta">{description}</span>}
      </span>
    </AriaCheckbox>
  )
}
