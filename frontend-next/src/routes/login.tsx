import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { createFileRoute, Link, redirect, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError } from '../api/client'
import { Button } from '../components/ui/Button'
import { FormTextField } from '../components/ui/FormTextField'
import { isMfaChallenge, login, type MfaChallenge, verifyMfa } from '../auth'
import { getToken, setTokens, type Tokens } from '../token'

// Only same-app paths: an absolute or protocol-relative URL here would turn
// the login page into an open redirect.
const searchSchema = z.object({
  redirect: z
    .string()
    .refine((s) => s.startsWith('/') && !s.startsWith('//'))
    .optional()
    .catch(undefined),
})

export const Route = createFileRoute('/login')({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (getToken()) throw redirect({ to: search.redirect ?? '/' })
  },
  component: LoginPage,
})

const formSchema = z.object({
  email: z.email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})

type FormValues = z.infer<typeof formSchema>

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    // fastapi-users answers bad credentials with 400 LOGIN_BAD_CREDENTIALS;
    // saying which half was wrong would help someone guessing.
    if (err.status === 400) return 'Invalid credentials.'
    if (err.status === 429) return err.message
    return `Login failed (${err.status}).`
  }
  return 'Cannot reach the server.'
}

function LoginPage() {
  const search = Route.useSearch()
  const router = useRouter()
  // Set once the password was right on an account with MFA on: the card turns
  // into the code step. Cleared again when that challenge runs out.
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null)
  const [expired, setExpired] = useState(false)

  const signedIn = async (tokens: Tokens) => {
    setTokens(tokens)
    await router.navigate({ to: search.redirect ?? '/', replace: true })
  }

  if (challenge) {
    return (
      <MfaStep
        challenge={challenge}
        onSignedIn={signedIn}
        onExpired={() => {
          setChallenge(null)
          setExpired(true)
        }}
      />
    )
  }
  return (
    <PasswordStep
      expired={expired}
      onSignedIn={signedIn}
      onChallenge={(next) => {
        setExpired(false)
        setChallenge(next)
      }}
    />
  )
}

function PasswordStep({
  expired,
  onSignedIn,
  onChallenge,
}: {
  expired: boolean
  onSignedIn: (tokens: Tokens) => Promise<void>
  onChallenge: (challenge: MfaChallenge) => void
}) {
  const { api } = Route.useRouteContext()

  const { control, handleSubmit } = useForm<FormValues, unknown, FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: '', password: '' },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => login(api, values.email, values.password),
    onSuccess: (result) => (isMfaChallenge(result) ? onChallenge(result) : onSignedIn(result)),
  })

  return (
    <div className="auth-page">
      <form className="panel auth-card" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>Sign in to continue.</p>
        </div>

        {expired && !mutation.isError && (
          <p className="form-error" role="alert">
            The sign-in took too long. Enter your password again.
          </p>
        )}

        <FormTextField
          control={control}
          name="email"
          label="Email"
          type="email"
          autoComplete="username"
          autoFocus
        />
        <FormTextField
          control={control}
          name="password"
          label="Password"
          type="password"
          autoComplete="current-password"
        />

        {mutation.isError && (
          <p className="form-error" role="alert">
            {errorText(mutation.error)}
          </p>
        )}

        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
        <Link to="/forgot-password" className="button link-button">
          Forgot password?
        </Link>
      </form>
    </div>
  )
}

const codeSchema = z.object({
  code: z.string().trim().min(1, 'Enter the code.'),
})

type CodeValues = z.infer<typeof codeSchema>

function codeErrorText(err: unknown, recovery: boolean): string {
  if (err instanceof ApiError) {
    if (err.status === 400) return recovery ? 'That recovery code is not valid.' : 'That code is not correct.'
    if (err.status === 429) return err.message
    return `Sign-in failed (${err.status}).`
  }
  return 'Cannot reach the server.'
}

// The second step with MFA on. A recovery code goes in the same field and to
// the same endpoint; the switch only changes what the field asks for.
function MfaStep({
  challenge,
  onSignedIn,
  onExpired,
}: {
  challenge: MfaChallenge
  onSignedIn: (tokens: Tokens) => Promise<void>
  onExpired: () => void
}) {
  const { api } = Route.useRouteContext()
  const [recovery, setRecovery] = useState(false)

  const { control, handleSubmit, reset } = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '' },
  })

  const mutation = useMutation({
    mutationFn: ({ code }: CodeValues) => verifyMfa(api, challenge.mfa_token, code),
    onSuccess: onSignedIn,
    // 401: the challenge expired (five minutes) — back to the password.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) onExpired()
    },
  })

  return (
    <div className="auth-page">
      <form className="panel auth-card" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>
            {recovery
              ? 'Enter one of your recovery codes. Each one works once.'
              : 'Enter the 6-digit code from your authenticator app.'}
          </p>
        </div>

        <FormTextField
          key={recovery ? 'recovery' : 'totp'}
          control={control}
          name="code"
          label={recovery ? 'Recovery code' : 'Authentication code'}
          autoComplete="one-time-code"
          inputMode={recovery ? 'text' : 'numeric'}
          autoFocus
        />

        {mutation.isError && (
          <p className="form-error" role="alert">
            {codeErrorText(mutation.error, recovery)}
          </p>
        )}

        <Button type="submit" isDisabled={mutation.isPending}>
          {mutation.isPending ? 'Verifying…' : 'Verify'}
        </Button>
        <Button
          variant="quiet"
          className="link-button"
          onPress={() => {
            setRecovery(!recovery)
            reset()
            mutation.reset()
          }}
        >
          {recovery ? 'Use the authenticator app instead' : 'Use a recovery code'}
        </Button>
      </form>
    </div>
  )
}
