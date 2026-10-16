import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'
import { contact, deal } from '../test/fixtures'
import { withQueryClient } from '../test/query'
import { http, server, testApi } from '../test/server'
import { ContactPicker, DealPicker, OrganizationPicker } from './RecordPickers'

vi.mock('@tanstack/react-router', () => ({ useRouteContext: () => ({ api: testApi() }) }))

function ControlledDealPicker({ initialLabel, initialValue = null }: { initialLabel?: string | null; initialValue?: string | null }) {
  const [value, setValue] = useState<string | null>(initialValue)
  return <DealPicker value={value} onChange={setValue} initialLabel={initialLabel} />
}

function ControlledContactPicker({ initialLabel, initialValue = null }: { initialLabel?: string | null; initialValue?: string | null }) {
  const [value, setValue] = useState<string | null>(initialValue)
  return <ContactPicker value={value} onChange={setValue} initialLabel={initialLabel} />
}

function ControlledOrganizationPicker({ initialLabel, initialValue = null }: { initialLabel?: string | null; initialValue?: string | null }) {
  const [value, setValue] = useState<string | null>(initialValue)
  return <OrganizationPicker value={value} onChange={setValue} initialLabel={initialLabel} />
}

describe('RecordPickers', () => {
  test('DealPicker: clicking an option without typing immediately displays deal title', async () => {
    server.use(
      http.get('/deals/', ({ response }) =>
        response(200).json({
          items: [deal({ id: 'deal-1', title: 'Big Solar Contract' })],
          total: 1,
          skip: 0,
          limit: 50,
        }),
      ),
    )
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledDealPicker />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Deal' })
    expect(combobox).toHaveValue('')

    await user.click(combobox)
    const option = await screen.findByRole('option', { name: /Big Solar Contract/ })
    await user.click(option)

    expect(combobox).toHaveValue('Big Solar Contract')
  })

  test('DealPicker: selecting an option after partial search replaces search text with full deal title', async () => {
    server.use(
      http.get('/deals/', ({ response }) =>
        response(200).json({
          items: [deal({ id: 'deal-1', title: 'Big Solar Contract' })],
          total: 1,
          skip: 0,
          limit: 50,
        }),
      ),
    )
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledDealPicker />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Deal' })

    await user.type(combobox, 'Solar')
    const option = await screen.findByRole('option', { name: /Big Solar Contract/ })
    await user.click(option)

    expect(combobox).toHaveValue('Big Solar Contract')
  })

  test('ContactPicker: updates input value with contact name on selection', async () => {
    server.use(
      http.get('/contacts/', ({ response }) =>
        response(200).json({
          items: [contact({ id: 'contact-1', name: 'Maria Huber' })],
          total: 1,
          skip: 0,
          limit: 50,
        }),
      ),
    )
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledContactPicker />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Contact' })

    await user.click(combobox)
    const option = await screen.findByRole('option', { name: /Maria Huber/ })
    await user.click(option)

    expect(combobox).toHaveValue('Maria Huber')
  })

  test('OrganizationPicker: updates input value with organization name on selection', async () => {
    server.use(
      http.get('/organizations/', ({ response }) =>
        response(200).json({
          items: [{ id: 'org-1', name: 'Acme Solar GmbH', domain: 'acme.at', contact_count: 0, created_at: '', updated_at: '', version: 1 }],
          total: 1,
          skip: 0,
          limit: 50,
        }),
      ),
    )
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledOrganizationPicker />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Organization' })

    await user.click(combobox)
    const option = await screen.findByRole('option', { name: /Acme Solar GmbH/ })
    await user.click(option)

    expect(combobox).toHaveValue('Acme Solar GmbH')
  })
})
