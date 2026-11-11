import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { unwrap } from '../../../api/client'
import {
  type ApiToken,
  apiTokensQuery,
  EXPIRY_OPTIONS,
  type Expiry,
  expiresAt,
  statusLabel,
  statusTone,
} from '../../../apiTokens'
import { Button } from '../../../components/ui/Button'
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog'
import { FormTextField } from '../../../components/ui/FormTextField'
import { Modal } from '../../../components/ui/Modal'
import { Select } from '../../../components/ui/Select'
import { formatDateTime, formatTimeAgo } from '../../../format'

export const Route = createFileRoute('/_authed/account/api-tokens')({
  component: ApiTokensPage,
})

// Credentials for agents (backend/app/auth/api_tokens.py): named, read-only,
// revocable. The secret exists in the response that creates a token and
// nowhere else, so it is held here only while the dialog shows it.
function ApiTokensPage() {
  const { api, config } = Route.useRouteContext()
  const { data: tokens, error, isPending } = useQuery(apiTokensQuery(api))
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<ApiToken | null>(null)

  return (
    <div className="page page-narrow">
      <Link to="/account" className="back-link">
        ← Account
      </Link>
      <header className="page-header">
        <h1>API tokens</h1>
        <p>Read-only access for agents such as Claude Code or Cursor. Make one token per tool, so each can be revoked on its own.</p>
      </header>

      <section className="panel">
        <div className="panel-body">
          {isPending ? (
            <p className="muted">Loading…</p>
          ) : error ? (
            <p className="form-error">{error.message}</p>
          ) : tokens.length === 0 ? (
            <p className="muted">No tokens yet.</p>
          ) : (
            <ul className="rows">
              {tokens.map((token) => (
                <TokenRow key={token.id} token={token} onRevoke={() => setRevoking(token)} />
              ))}
            </ul>
          )}
        </div>
      </section>

      <div className="form-actions account-actions">
        <Button onPress={() => setCreating(true)}>Generate token</Button>
      </div>

      <section className="panel">
        <div className="panel-body">
          <p>Send the token with every request to the agent API, in either header:</p>
          <p>
            <code className="token-secret">Authorization: Bearer tc_live_…</code>
          </p>
          <p>
            <code className="token-secret">X-API-Key: tc_live_…</code>
          </p>
          <p className="muted">
            The base URL is <code>{new URL(config.apiUrl, window.location.origin).href.replace(/\/$/, '')}/v1/agent</code>. A token works there and nowhere else. The MCP
            server in <code>mcp/</code> reads it from <code>TINYCRM_API_TOKEN</code>.
          </p>
        </div>
      </section>

      <CreateDialog isOpen={creating} onOpenChange={setCreating} />
      <RevokeDialog token={revoking} onClose={() => setRevoking(null)} />
    </div>
  )
}

function TokenRow({ token, onRevoke }: { token: ApiToken; onRevoke: () => void }) {
  return (
    <li className="token-row" data-status={token.status}>
      <div className="token-info">
        <strong>{token.name}</strong>
        <span className="muted">
          Created {formatDateTime(token.created_at)} · Last used{' '}
          {token.last_used_at ? formatTimeAgo(token.last_used_at) : 'never'}
          {token.expires_at && token.status === 'active' ? ` · Expires ${formatDateTime(token.expires_at)}` : ''}
        </span>
      </div>
      <span className="badge" data-tone={statusTone(token.status)}>
        {statusLabel(token.status)}
      </span>
      {token.status === 'active' && (
        <Button variant="quiet" onPress={onRevoke} aria-label={`Revoke ${token.name}`}>
          Revoke
        </Button>
      )}
    </li>
  )
}

function RevokeDialog({ token, onClose }: { token: ApiToken | null; onClose: () => void }) {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const revoke = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST('/users/me/api-tokens/{token_id}/revoke', { params: { path: { token_id: id } } })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: apiTokensQuery(api).queryKey })
      onClose()
    },
  })

  return (
    <ConfirmDialog
      title="Revoke token"
      isOpen={token !== null}
      onOpenChange={(open) => {
        if (!open) {
          revoke.reset()
          onClose()
        }
      }}
      onConfirm={() => token && revoke.mutate(token.id)}
      confirmLabel="Revoke"
      pendingLabel="Revoking…"
      pending={revoke.isPending}
      error={revoke.error}
    >
      <p>
        <strong>{token?.name}</strong> stops working immediately, for every agent using it. This cannot be undone.
      </p>
    </ConfirmDialog>
  )
}

const schema = z.object({ name: z.string().trim().min(1, 'Give the token a name.').max(100, 'At most 100 characters.') })

function CreateDialog({ isOpen, onOpenChange }: { isOpen: boolean; onOpenChange: (open: boolean) => void }) {
  const { api } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const [expiry, setExpiry] = useState<Expiry | ''>('')
  const [copied, setCopied] = useState(false)
  const { control, handleSubmit, reset } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: '' },
  })
  const create = useMutation({
    mutationFn: ({ name }: { name: string }) =>
      unwrap(api.POST('/users/me/api-tokens/', { body: { name, expires_at: expiresAt(expiry) } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: apiTokensQuery(api).queryKey }),
  })

  // Closing discards the secret: it is not stored anywhere that could show it again.
  function close(open: boolean) {
    onOpenChange(open)
    if (!open) {
      create.reset()
      reset()
      setExpiry('')
      setCopied(false)
    }
  }

  async function copy(token: string) {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Modal title={create.data ? 'Token created' : 'Generate token'} isOpen={isOpen} onOpenChange={close}>
      {create.data ? (
        <div className="form">
          <p>
            <strong>{create.data.name}</strong>: copy the token now. <strong>This token is shown only once.</strong>
          </p>
          <code className="token-secret" data-testid="new-token">
            {create.data.token}
          </code>
          <div className="form-actions">
            <Button variant="quiet" onPress={() => copy(create.data.token)}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
            <Button onPress={() => close(false)}>Done</Button>
          </div>
        </div>
      ) : (
        <form className="form" onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
          <FormTextField control={control} name="name" label="Name" autoComplete="off" />
          <Select
            label="Expires"
            options={EXPIRY_OPTIONS.filter((o) => o.value !== '').map((o) => ({ value: o.value, label: o.label }))}
            emptyLabel="Never"
            value={expiry}
            onChange={setExpiry}
          />
          {create.isError && (
            <p className="form-error" role="alert">
              {create.error.message}
            </p>
          )}
          <div className="form-actions">
            <Button variant="quiet" onPress={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" isDisabled={create.isPending}>
              {create.isPending ? 'Generating…' : 'Generate'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}
