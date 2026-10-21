import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { contact } from '../test/fixtures'
import { withQueryClient } from '../test/query'
import { http, server, testApi } from '../test/server'
import { LinksPicker } from './LinksPicker'

// The picker reads the API client from the authed route; a test has no router.
vi.mock('@tanstack/react-router', () => ({ useRouteContext: () => ({ api: testApi() }) }))

// `count` contacts, sorted by name and cut to the page asked for, as the API
// does it. Records the limit of each request.
function contactsEndpoint(count: number) {
  const all = Array.from({ length: count }, (_, i) => {
    const n = String(i + 1).padStart(2, '0')
    return contact({ id: `contact-${n}`, name: `Contact ${n}` })
  })
  const limits: number[] = []
  const handler = http.get('/contacts/', ({ query, response }) => {
    const limit = Number(query.get('limit'))
    limits.push(limit)
    const search = query.get('search')?.toLowerCase() ?? ''
    const matches = all.filter((c) => c.name.toLowerCase().includes(search))
    return response(200).json({ items: matches.slice(0, limit), total: matches.length, skip: 0, limit })
  })
  return { handler, limits }
}

async function open(count: number) {
  const endpoint = contactsEndpoint(count)
  server.use(endpoint.handler)
  const { wrapper } = withQueryClient()
  const user = userEvent.setup()
  render(<LinksPicker kind="contact" value={[]} onChange={() => {}} />, { wrapper })
  await user.click(screen.getByRole('combobox', { name: 'Contacts' }))
  return { user, ...endpoint }
}

describe('LinksPicker', () => {
  // #228: the dropdown used to stop at ten, so the eleventh contact by name
  // could not be picked without knowing to type for it.
  test('offers a contact past the tenth by name', async () => {
    const { limits } = await open(12)

    expect(await screen.findByRole('option', { name: 'Contact 11' })).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(12)
    expect(limits).toEqual([50])
    expect(screen.queryByText(/more not shown/)).not.toBeInTheDocument()
  })

  // Fifty rows of React Aria in jsdom are slow, so this one looks rows up by
  // their text and pastes rather than types.
  test('says how many it left out, until a search narrows the list to all of them', async () => {
    const { user } = await open(60)

    expect(await screen.findByText('10 more not shown. Type to narrow the list.')).toBeInTheDocument()
    expect(screen.queryByText('Contact 55')).not.toBeInTheDocument()

    await user.paste('55')

    expect(await screen.findByText('Contact 55')).toBeInTheDocument()
    expect(screen.queryByText(/more not shown/)).not.toBeInTheDocument()
  }, 15_000)

  // #269: a row reads "Maria Huber · ACME", so typing ACME has to find it.
  test('typing an organization name offers contacts at that organization', async () => {
    const maria = contact({ id: 'contact-maria', name: 'Maria Huber', job_title: 'CTO', organization_name: 'ACME' })
    const ada = contact({ id: 'contact-ada', name: 'Ada Lovelace', organization_name: 'Initech' })
    const searches: string[] = []
    server.use(
      http.get('/contacts/', ({ query, response }) => {
        const search = query.get('search')?.toLowerCase() ?? ''
        searches.push(search)
        const matches = [maria, ada].filter((c) =>
          [c.name, c.job_title, c.organization_name].some((field) => field?.toLowerCase().includes(search)),
        )
        return response(200).json({ items: matches, total: matches.length, skip: 0, limit: 50 })
      }),
    )
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    render(<LinksPicker kind="contact" value={[]} onChange={() => {}} />, { wrapper })

    const combobox = screen.getByRole('combobox', { name: 'Contacts' })
    expect(combobox).toHaveAttribute('placeholder', 'Search contacts to link')
    await user.click(combobox)
    await user.paste('acme')

    await waitFor(() => expect(screen.queryByRole('option', { name: /Ada Lovelace/ })).not.toBeInTheDocument())
    expect(screen.getByRole('option', { name: /Maria Huber/ })).toHaveTextContent('CTO · ACME')
    expect(searches).toContain('acme')
  })
})
