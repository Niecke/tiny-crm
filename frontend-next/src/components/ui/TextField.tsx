import type { Ref } from 'react'
import {
  TextField as AriaTextField,
  type TextFieldProps as AriaTextFieldProps,
  FieldError,
  Input,
  Label,
  TextArea,
} from 'react-aria-components'

// Label, input and error message wired together by React Aria: the label
// names the input, the error is announced with it, and the invalid state
// reaches both. Validation itself stays in zod — this only shows the result,
// hence validationBehavior="aria" (no native browser bubbles).
export type TextFieldProps = Omit<AriaTextFieldProps, 'className' | 'children'> & {
  label: string
  errorMessage?: string
  placeholder?: string
  // A <textarea> instead of an <input>.
  rows?: number
  inputRef?: Ref<HTMLInputElement & HTMLTextAreaElement>
}

export function TextField({ label, errorMessage, placeholder, rows, inputRef, ...props }: TextFieldProps) {
  return (
    <AriaTextField {...props} className="field" validationBehavior="aria">
      <Label className="field-label">{label}</Label>
      {rows ? (
        <TextArea className="input" rows={rows} placeholder={placeholder} ref={inputRef} />
      ) : (
        <Input className="input" placeholder={placeholder} ref={inputRef} />
      )}
      <FieldError className="field-error">{errorMessage}</FieldError>
    </AriaTextField>
  )
}
