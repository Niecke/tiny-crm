import { Button as AriaButton, type ButtonProps as AriaButtonProps } from 'react-aria-components'

// React Aria's Button: press handling that behaves the same for mouse, touch
// and keyboard, and a real `disabled` that screen readers announce. The look is
// ours (.button in styles.css). Navigation is not a button — use a router
// <Link> with className="button" for that.
type ButtonProps = Omit<AriaButtonProps, 'className'> & {
  variant?: 'primary' | 'quiet'
  className?: string
}

export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  const classes = ['button', variant === 'quiet' && 'button-quiet', className].filter(Boolean).join(' ')
  return <AriaButton {...props} className={classes} />
}
