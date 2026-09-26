import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, unwrap } from '../../../api/client'
import { meQuery } from '../../../auth'
import { Button } from '../../../components/ui/Button'
import { FormTextField } from '../../../components/ui/FormTextField'

export const Route = createFileRoute('/_authed/account/password')({
  component: ChangePassword,
})

// The backend's own rule (PasswordChange.new_password, min_length=8), checked
// here first so the common mistake never needs a round trip.
const MIN_LENGTH = 8

const formSchema = z
  .object({
    old_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(MIN_LENGTH, `At least ${MIN_LENGTH} characters.`),
    confirm: z.string(),
  })
  .refine((v) => v.confirm === v.new_password, { path: ['confirm'], message: 'Does not match the new password.' })

type FormValues = z.infer<typeof formSchema>

// The API's refusals, in words. A wrong current password is a 400 with a code
// rather than a 401, so it does not sign the user out (src/api/client.ts).
function describe(error: Error): string {
  if (error instanceof ApiError) {
    if (error.detail === 'INVALID_OLD_PASSWORD') return 'The current password is not correct.'
    const detail = error.detail as { code?: unknown; reason?: unknown } | undefined
    if (detail?.code === 'INVALID_PASSWORD') return `The new password is not accepted: ${String(detail.reason ?? '')}`
  }
  return error.message
}

function ChangePassword() {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const { control, handleSubmit, setError } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { old_password: '', new_password: '', confirm: '' },
  })

  const mutation = useMutation({
    mutationFn: ({ old_password, new_password }: FormValues) =>
      unwrap(api.POST('/users/me/password', { body: { old_password, new_password } })),
    // "Password last changed" on the account page is stale now. The token is
    // not: the JWT does not depend on the password, so this tab stays signed in.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQuery(api).queryKey }),
    onError: (error) => {
      if (error instanceof ApiError && error.detail === 'INVALID_OLD_PASSWORD') {
        setError('old_password', { message: describe(error) }, { shouldFocus: true })
      }
    },
  })

  if (mutation.isSuccess) {
    return (
      <div className="page page-narrow">
        <header className="page-header">
          <h1>Password changed</h1>
          <p>Use the new password the next time you sign in, here and in the current app.</p>
        </header>
        <div className="form-actions account-actions">
          <Link to="/account" className="button">
            Back to account
          </Link>
        </div>
      </div>
    )
  }

  // Shown on the field it belongs to when there is one; everything else
  // (a 422, the API down) goes in the banner.
  const bannerError =
    mutation.error && !(mutation.error instanceof ApiError && mutation.error.detail === 'INVALID_OLD_PASSWORD')
      ? describe(mutation.error)
      : null

  return (
    <div className="page page-narrow">
      <Link to="/account" className="back-link">
        ← Account
      </Link>
      <header className="page-header">
        <h1>Change password</h1>
      </header>

      <form className="panel form" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <FormTextField
          control={control}
          name="old_password"
          label="Current password"
          type="password"
          autoComplete="current-password"
          autoFocus
        />
        <FormTextField
          control={control}
          name="new_password"
          label="New password"
          type="password"
          autoComplete="new-password"
          description={`At least ${MIN_LENGTH} characters.`}
        />
        <FormTextField
          control={control}
          name="confirm"
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
        />

        {bannerError && (
          <p className="form-error" role="alert">
            {bannerError}
          </p>
        )}

        <div className="form-actions">
          <Link to="/account" className="button button-quiet">
            Cancel
          </Link>
          <Button type="submit" isDisabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Change password'}
          </Button>
        </div>
      </form>
    </div>
  )
}
