import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, unwrap } from '../api/client'
import { MIN_PASSWORD_LENGTH } from '../auth'
import { Button } from '../components/ui/Button'
import { FormTextField } from '../components/ui/FormTextField'

// Public: where the invite and the password-reset mail both land
// (backend/app/mail.py, RESET_PATH). Same token, same endpoint — an invite is a
// reset for an account whose password nobody knows yet.
export const Route = createFileRoute('/reset-password')({
  component: ResetPasswordPage,
})

// The token rides in the fragment (#token=…), which the browser never sends to
// a server, so it stays out of access logs and Referer headers.
function tokenFromHash(): string | null {
  return new URLSearchParams(window.location.hash.slice(1)).get('token')
}

const formSchema = z
  .object({
    password: z.string().min(MIN_PASSWORD_LENGTH, `At least ${MIN_PASSWORD_LENGTH} characters.`),
    confirm: z.string(),
  })
  .refine((v) => v.confirm === v.password, { path: ['confirm'], message: 'Does not match the password.' })

type FormValues = z.infer<typeof formSchema>

// fastapi-users answers a bad, expired or spent token — and an inactive
// account — with this one code.
function isBadToken(error: Error | null): boolean {
  return error instanceof ApiError && error.detail === 'RESET_PASSWORD_BAD_TOKEN'
}

function invalidPasswordReason(error: Error | null): string | null {
  if (!(error instanceof ApiError)) return null
  const detail = error.detail as { code?: unknown; reason?: unknown } | undefined
  return detail?.code === 'RESET_PASSWORD_INVALID_PASSWORD' ? String(detail.reason ?? 'Not accepted.') : null
}

function AuthCard({ lead, children }: { lead: string; children: ReactNode }) {
  return (
    <div className="auth-page">
      <div className="panel auth-card">
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>{lead}</p>
        </div>
        {children}
      </div>
    </div>
  )
}

function DeadLink() {
  return (
    <AuthCard lead="This link does not work.">
      <p>It may have expired, or it was already used. Links work once and only for a limited time.</p>
      <Link to="/forgot-password" className="button">
        Send a new link
      </Link>
    </AuthCard>
  )
}

function ResetPasswordPage() {
  const { api } = Route.useRouteContext()
  // Read once: the fragment is not part of the router's search state.
  const [token] = useState(tokenFromHash)

  const { control, handleSubmit, setError } = useForm<FormValues, unknown, FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { password: '', confirm: '' },
  })

  const mutation = useMutation({
    mutationFn: ({ password }: FormValues) =>
      unwrap(api.POST('/auth/reset-password', { body: { token: token ?? '', password } })),
    onError: (error) => {
      const reason = invalidPasswordReason(error)
      if (reason) setError('password', { message: reason }, { shouldFocus: true })
    },
  })

  if (!token || isBadToken(mutation.error)) return <DeadLink />

  if (mutation.isSuccess) {
    return (
      <AuthCard lead="Password set.">
        <p>Sign in with your email address and the new password.</p>
        <Link to="/login" className="button">
          Sign in
        </Link>
      </AuthCard>
    )
  }

  // A rejected password is shown on its field; anything else (a 422, the API
  // down) goes in the banner.
  const bannerError =
    mutation.error && !invalidPasswordReason(mutation.error)
      ? mutation.error instanceof ApiError
        ? `Could not set the password (${mutation.error.status}).`
        : 'Cannot reach the server.'
      : null

  return (
    <div className="auth-page">
      <form className="panel auth-card" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>Choose a password.</p>
        </div>

        <FormTextField
          control={control}
          name="password"
          label="New password"
          type="password"
          autoComplete="new-password"
          description={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          autoFocus
        />
        <FormTextField
          control={control}
          name="confirm"
          label="Confirm password"
          type="password"
          autoComplete="new-password"
        />

        {bannerError && (
          <p className="form-error" role="alert">
            {bannerError}
          </p>
        )}

        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Set password'}
        </Button>
      </form>
    </div>
  )
}
