import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import QRCode from 'qrcode'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, unwrap } from '../../../api/client'
import { meQuery } from '../../../auth'
import { Button } from '../../../components/ui/Button'
import { FormTextField } from '../../../components/ui/FormTextField'
import { formatDateTime } from '../../../format'

export const Route = createFileRoute('/_authed/account/mfa')({
  component: TwoFactorPage,
})

// Two-factor sign-in (backend/app/auth/mfa.py). Off: set it up — scan, confirm
// with the first code, keep the recovery codes. On: new recovery codes, or
// turn it off with the password and a code.
function TwoFactorPage() {
  const { api } = Route.useRouteContext()
  const { data: me } = useQuery(meQuery(api))
  // Recovery codes just issued, shown until the user leaves the page. Kept
  // here rather than in the steps, so the refetch of /users/me that turning
  // MFA on causes does not unmount them.
  // `afterSetup`: MFA was just turned on, which signed out every other device;
  // a mere new set of codes leaves them signed in.
  const [issued, setIssued] = useState<{ codes: string[]; afterSetup: boolean } | null>(null)

  return (
    <div className="page page-narrow">
      <Link to="/account" className="back-link">
        ← Account
      </Link>
      <header className="page-header">
        <h1>Two-factor sign-in</h1>
        <p>A code from an authenticator app such as Google Authenticator or Microsoft Authenticator, asked for after the password at every sign-in.</p>
      </header>

      {issued ? (
        <RecoveryCodes codes={issued.codes} afterSetup={issued.afterSetup} />
      ) : !me ? (
        <p className="muted">Loading…</p>
      ) : me.mfa_enabled_at ? (
        <Manage enabledAt={me.mfa_enabled_at} onCodes={(codes) => setIssued({ codes, afterSetup: false })} />
      ) : (
        <Setup onCodes={(codes) => setIssued({ codes, afterSetup: true })} />
      )}
    </div>
  )
}

function describe(error: Error): string {
  if (error instanceof ApiError) {
    if (error.detail === 'MFA_CODE_INVALID') return 'That code is not correct.'
    if (error.detail === 'PASSWORD_INCORRECT') return 'The password is not correct.'
    if (error.detail === 'MFA_SETUP_CHANGED') return 'Setup was restarted elsewhere. Scan the new code and try again.'
  }
  return error.message
}

const codeSchema = z.object({ code: z.string().trim().min(1, 'Enter the code from the app.') })

function Setup({ onCodes }: { onCodes: (codes: string[]) => void }) {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()

  const start = useMutation({ mutationFn: () => unwrap(api.POST('/users/me/mfa/setup')) })

  const { control, handleSubmit } = useForm<z.infer<typeof codeSchema>>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '' },
  })
  const confirm = useMutation({
    mutationFn: ({ code }: { code: string }) => unwrap(api.POST('/users/me/mfa/confirm', { body: { code } })),
    onSuccess: async ({ recovery_codes }) => {
      onCodes(recovery_codes)
      await queryClient.invalidateQueries({ queryKey: meQuery(api).queryKey })
    },
  })

  if (!start.data) {
    return (
      <section className="panel form">
        <p>Off. Signing in needs only the password.</p>
        {start.isError && (
          <p className="form-error" role="alert">
            {describe(start.error)}
          </p>
        )}
        <div className="form-actions">
          <Button onPress={() => start.mutate()} isDisabled={start.isPending}>
            {start.isPending ? 'Starting…' : 'Set up two-factor sign-in'}
          </Button>
        </div>
      </section>
    )
  }

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => confirm.mutate(values))} noValidate>
      <p>1. Scan this code with the authenticator app.</p>
      <QrCode value={start.data.otpauth_uri} />
      <p className="muted">
        Cannot scan it? Enter this key in the app instead: <code className="mfa-secret">{groupKey(start.data.secret)}</code>
      </p>
      <p>2. Enter the 6-digit code the app shows now.</p>
      <FormTextField
        control={control}
        name="code"
        label="Authentication code"
        autoComplete="one-time-code"
        inputMode="numeric"
      />
      {confirm.isError && (
        <p className="form-error" role="alert">
          {describe(confirm.error)}
        </p>
      )}
      <div className="form-actions">
        <Link to="/account" className="button button-quiet">
          Cancel
        </Link>
        <Button type="submit" isDisabled={confirm.isPending}>
          {confirm.isPending ? 'Checking…' : 'Turn on'}
        </Button>
      </div>
    </form>
  )
}

// The base32 key in groups of four, the way authenticator apps show it.
function groupKey(secret: string): string {
  return secret.replace(/(.{4})/g, '$1 ').trim()
}

function QrCode({ value }: { value: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let current = true
    QRCode.toDataURL(value, { margin: 1, width: 200 }).then(
      (url) => current && setSrc(url),
      () => current && setSrc(null),
    )
    return () => {
      current = false
    }
  }, [value])
  return src ? <img className="mfa-qr" src={src} alt="QR code for the authenticator app" width={200} height={200} /> : null
}

function RecoveryCodes({ codes, afterSetup }: { codes: string[]; afterSetup: boolean }) {
  const [copied, setCopied] = useState(false)
  const text = codes.join('\n') + '\n'

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'tinycrm-recovery-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="panel form">
      {afterSetup ? (
        <p>
          <strong>Two-factor sign-in is on.</strong> Every other device has been signed out.
        </p>
      ) : (
        <p>
          <strong>New recovery codes.</strong> The ones issued before no longer work.
        </p>
      )}
      <p>
        Keep these recovery codes somewhere safe. Each one signs in once in place of a code from the app — for when the
        phone is lost. They are shown only now.
      </p>
      <ul className="recovery-codes">
        {codes.map((code) => (
          <li key={code}>
            <code>{code}</code>
          </li>
        ))}
      </ul>
      <div className="form-actions">
        <Button
          variant="quiet"
          onPress={() => navigator.clipboard.writeText(text).then(() => setCopied(true), () => setCopied(false))}
        >
          {copied ? 'Copied' : 'Copy'}
        </Button>
        <Button variant="quiet" onPress={download}>
          Download
        </Button>
        <Link to="/account" className="button">
          Done
        </Link>
      </div>
    </section>
  )
}

const passwordSchema = z.object({ password: z.string().min(1, 'Enter your password.') })
const disableSchema = passwordSchema.extend({
  code: z.string().trim().min(1, 'Enter a code from the app or a recovery code.'),
})

function Manage({ enabledAt, onCodes }: { enabledAt: string; onCodes: (codes: string[]) => void }) {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()

  const regenerateForm = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: '' },
  })
  const regenerate = useMutation({
    mutationFn: ({ password }: { password: string }) =>
      unwrap(api.POST('/users/me/mfa/recovery-codes', { body: { password } })),
    onSuccess: ({ recovery_codes }) => onCodes(recovery_codes),
  })

  const disableForm = useForm<z.infer<typeof disableSchema>>({
    resolver: zodResolver(disableSchema),
    defaultValues: { password: '', code: '' },
  })
  const disable = useMutation({
    mutationFn: (body: { password: string; code: string }) => unwrap(api.POST('/users/me/mfa/disable', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQuery(api).queryKey }),
  })

  return (
    <>
      <section className="panel form">
        <p>On since {formatDateTime(enabledAt)}.</p>
      </section>

      <form
        className="panel form"
        onSubmit={regenerateForm.handleSubmit((values) => regenerate.mutate(values))}
        noValidate
      >
        <h2>New recovery codes</h2>
        <p className="muted">Replaces every recovery code issued before.</p>
        <FormTextField
          control={regenerateForm.control}
          name="password"
          label="Password"
          type="password"
          autoComplete="current-password"
        />
        {regenerate.isError && (
          <p className="form-error" role="alert">
            {describe(regenerate.error)}
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" isDisabled={regenerate.isPending}>
            {regenerate.isPending ? 'Creating…' : 'Create new codes'}
          </Button>
        </div>
      </form>

      <form className="panel form" onSubmit={disableForm.handleSubmit((values) => disable.mutate(values))} noValidate>
        <h2>Turn off</h2>
        <p className="muted">Signing in will need only the password again. Every other device is signed out.</p>
        <FormTextField
          control={disableForm.control}
          name="password"
          label="Password"
          type="password"
          autoComplete="current-password"
        />
        <FormTextField
          control={disableForm.control}
          name="code"
          label="Authentication or recovery code"
          autoComplete="one-time-code"
        />
        {disable.isError && (
          <p className="form-error" role="alert">
            {describe(disable.error)}
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" isDisabled={disable.isPending}>
            {disable.isPending ? 'Turning off…' : 'Turn off two-factor sign-in'}
          </Button>
        </div>
      </form>
    </>
  )
}
