import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { describe, expect, test, vi } from 'vitest'
import { withQueryClient } from '../test/query'
import { http, server, testApi } from '../test/server'
import { FormTagPicker, TagPicker } from './TagPicker'

vi.mock('@tanstack/react-router', () => ({ useRouteContext: () => ({ api: testApi() }) }))

function ControlledTagPicker({
  initialTags = [],
  onChange = () => {},
}: {
  initialTags?: string[]
  onChange?: (tags: string[]) => void
}) {
  const [tags, setTags] = useState<string[]>(initialTags)
  return (
    <TagPicker
      label="Tags"
      value={tags}
      onChange={(next) => {
        setTags(next)
        onChange(next)
      }}
    />
  )
}

function FormWithTagPicker({
  defaultTags = '',
  onSubmit = () => {},
}: {
  defaultTags?: string
  onSubmit?: (data: { tags: string }) => void
}) {
  const { control, handleSubmit } = useForm({ defaultValues: { tags: defaultTags } })
  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <FormTagPicker control={control} name="tags" label="Tags" />
      <button type="submit">Submit</button>
    </form>
  )
}

describe('TagPicker', () => {
  test('renders initial tags as chips', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['vip', 'lead', 'client'])))
    const { wrapper } = withQueryClient()

    render(<ControlledTagPicker initialTags={['vip', 'client']} />, { wrapper })

    expect(screen.getByText('vip')).toBeInTheDocument()
    expect(screen.getByText('client')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove tag vip' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove tag client' })).toBeInTheDocument()
  })

  test('clicking combobox opens existing tag suggestions excluding already selected tags', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['vip', 'lead', 'client'])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledTagPicker initialTags={['vip']} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.click(combobox)

    expect(await screen.findByRole('option', { name: 'lead' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'client' })).toBeInTheDocument()
    // 'vip' is already selected, so it should not be in suggestions
    expect(screen.queryByRole('option', { name: 'vip' })).not.toBeInTheDocument()
  })

  test('selecting an existing tag from dropdown adds it as chip and clears input', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['lead', 'partner'])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={[]} onChange={onChange} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.click(combobox)
    const option = await screen.findByRole('option', { name: 'lead' })
    await user.click(option)

    expect(onChange).toHaveBeenCalledWith(['lead'])
    expect(await screen.findByText('lead')).toBeInTheDocument()
    expect(combobox).toHaveValue('')
  })

  test('typing an arbitrary new tag and pressing Enter adds it', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['lead'])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={[]} onChange={onChange} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.type(combobox, 'custom-tag{enter}')

    expect(onChange).toHaveBeenCalledWith(['custom-tag'])
    expect(await screen.findByText('custom-tag')).toBeInTheDocument()
    expect(combobox).toHaveValue('')
  })

  test('typing a tag name followed by comma adds it', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json([])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={[]} onChange={onChange} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.type(combobox, 'first,second,')

    expect(await screen.findByText('first')).toBeInTheDocument()
    expect(await screen.findByText('second')).toBeInTheDocument()
    expect(combobox).toHaveValue('')
  })

  test('clicking chip remove button removes the tag', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json([])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={['removethis', 'keepthis']} onChange={onChange} />, { wrapper })

    expect(screen.getByText('removethis')).toBeInTheDocument()
    const removeBtn = screen.getByRole('button', { name: 'Remove tag removethis' })
    await user.click(removeBtn)

    expect(onChange).toHaveBeenCalledWith(['keepthis'])
    expect(screen.queryByText('removethis')).not.toBeInTheDocument()
    expect(screen.getByText('keepthis')).toBeInTheDocument()
  })

  test('pressing Backspace in empty input removes last tag', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json([])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={['first', 'second']} onChange={onChange} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.click(combobox)
    await user.keyboard('{backspace}')

    expect(onChange).toHaveBeenCalledWith(['first'])
    expect(screen.queryByText('second')).not.toBeInTheDocument()
  })

  test('typing partial text offers matching existing tags and an Add option', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['frontend', 'freeze'])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()

    render(<ControlledTagPicker initialTags={[]} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.type(combobox, 'free')

    expect(await screen.findByRole('option', { name: 'freeze' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Add “free”' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'frontend' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('option', { name: 'Add “free”' }))
    expect(await screen.findByText('free')).toBeInTheDocument()
  })

  test('does not add duplicate tags regardless of casing', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json([])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ControlledTagPicker initialTags={['lead']} onChange={onChange} />, { wrapper })
    const combobox = screen.getByRole('combobox', { name: 'Tags' })

    await user.type(combobox, 'LEAD{enter}')

    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getAllByText('lead')).toHaveLength(1)
  })

  test('FormTagPicker binds with react-hook-form as comma-separated string', async () => {
    server.use(http.get('/tags', ({ response }) => response(200).json(['existing'])))
    const { wrapper } = withQueryClient()
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(<FormWithTagPicker defaultTags="existing" onSubmit={onSubmit} />, { wrapper })

    expect(screen.getByText('existing')).toBeInTheDocument()

    const combobox = screen.getByRole('combobox', { name: 'Tags' })
    await user.type(combobox, 'added{enter}')

    expect(await screen.findByText('added')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    expect(onSubmit).toHaveBeenCalledWith({ tags: 'existing, added' }, expect.anything())
  })
})
