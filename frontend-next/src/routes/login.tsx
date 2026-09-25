import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { createFileRoute, redirect, useRouter } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError } from '../api'
import { login } from '../auth'
import { getToken, setToken } from '../token'

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
  const { config } = Route.useRouteContext()
  const search = Route.useSearch()
  const router = useRouter()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema) })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => login(config.apiUrl, values.email, values.password),
    onSuccess: async (token) => {
      setToken(token)
      await router.navigate({ to: search.redirect ?? '/', replace: true })
    },
  })

  return (
    <div className="auth-page">
      <form className="panel auth-card" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
        <div className="auth-header">
          <div className="brand">tinyCRM</div>
          <p>Sign in to continue.</p>
        </div>

        <label className="field">
          <span className="field-label">Email</span>
          <input
            className="input"
            type="email"
            autoComplete="username"
            autoFocus
            aria-invalid={errors.email ? true : undefined}
            {...register('email')}
          />
          {errors.email && <span className="field-error">{errors.email.message}</span>}
        </label>

        <label className="field">
          <span className="field-label">Password</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            aria-invalid={errors.password ? true : undefined}
            {...register('password')}
          />
          {errors.password && <span className="field-error">{errors.password.message}</span>}
        </label>

        {mutation.isError && (
          <p className="form-error" role="alert">
            {errorText(mutation.error)}
          </p>
        )}

        <button className="button" type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
