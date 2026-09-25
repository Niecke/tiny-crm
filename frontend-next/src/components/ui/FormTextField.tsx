import { type Control, Controller, type FieldValues, type Path } from 'react-hook-form'
import { TextField, type TextFieldProps } from './TextField'

// A TextField bound to a react-hook-form field. React Aria inputs are
// controlled (value + onChange), so they go through Controller rather than
// register(); the ref still reaches the input, so a failed submit focuses the
// first invalid field.
type FormTextFieldProps<TIn extends FieldValues, TOut extends FieldValues> = Omit<
  TextFieldProps,
  'name' | 'value' | 'onChange' | 'onBlur' | 'isInvalid' | 'errorMessage' | 'inputRef'
> & {
  control: Control<TIn, unknown, TOut>
  name: Path<TIn>
}

export function FormTextField<TIn extends FieldValues, TOut extends FieldValues>({
  control,
  name,
  ...props
}: FormTextFieldProps<TIn, TOut>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <TextField
          {...props}
          name={field.name}
          value={field.value ?? ''}
          onChange={field.onChange}
          onBlur={field.onBlur}
          inputRef={field.ref}
          isInvalid={fieldState.invalid}
          errorMessage={fieldState.error?.message}
        />
      )}
    />
  )
}
