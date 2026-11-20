import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { Facts, Notes } from './RecordPage'

describe('Notes', () => {
  test('is a region named Notes with the text and its line breaks', () => {
    render(<Notes>{'first\nsecond'}</Notes>)
    const region = screen.getByRole('region', { name: 'Notes' })
    expect(region.textContent).toContain('first\nsecond')
  })

  test('label overrides the name', () => {
    render(<Notes label="Description">text</Notes>)
    expect(screen.getByRole('region', { name: 'Description' })).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'Notes' })).toBeNull()
  })
})

describe('Facts', () => {
  test('without facts says so', () => {
    render(<Facts>{null}</Facts>)
    expect(screen.getByText('No details yet.')).toBeTruthy()
  })
})
