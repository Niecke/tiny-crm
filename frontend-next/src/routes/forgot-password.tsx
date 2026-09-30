import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { unwrap } from '../api/client'
import { Button } from '../components/ui/Button'
import { FormTextField } from '../components/ui/FormTextField'

// Public, like /login. The mailed link lands on /reset-password.
export const Route = createFileRoute('/forgot-password')({
  component: ForgotPasswordPage,
})

const formSchema = z.object({
  email: z.email('Enter a valid email address.'),
})

type FormValues = z.infer<typeof formSchema>

function ForgotPasswordPage() {
  const { api } = Route.useRouteContext()

  const { control, handleSubmit } = useForm<FormValues, unknown, FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: '' },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => unwrap(api.POST('/auth/forgot-password', { body: values })),
  })

  // The API answers 202 whether or not the address has an account, so this
  // page cannot say which — and must not pretend to know.
  if (mutation.isSuccess) {
    return (
      <div className="auth-page">
        <div className="panel auth-card">
          <div className="auth-header">
            <div className="brand">tinyCRM</div>
            <p>Check your mail.</p>
          </div>
          <p>
            If <strong>{mutation.variables.email}</strong> belongs to an account, a link to choose a new password is on
            its way. It works once, and only for a limited time.
          </p>
          <Link to="/login" className="button">
            Back to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <form className="panel auth-card" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>Enter your email address and we will send you a link to choose a new password.</p>
        </div>

        <FormTextField control={control} name="email" label="Email" type="email" autoComplete="username" autoFocus />

        {mutation.isError && (
          <p className="form-error" role="alert">
            Cannot reach the server.
          </p>
        )}

        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Sending…' : 'Send link'}
        </Button>
        <Link to="/login" className="button link-button">
          Back to sign in
        </Link>
      </form>
    </div>
  )
}
