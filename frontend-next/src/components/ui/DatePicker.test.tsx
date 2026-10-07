import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { DatePicker } from './DatePicker'
import { today, getLocalTimeZone } from '@internationalized/date'

describe('DatePicker', () => {
  test('opens calendar focused on current month / today when value is empty', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker label="Event date" value="" onChange={onChange} />)

    const button = screen.getByRole('button', { name: /pick event date from a calendar/i })
    await user.click(button)

    const grid = screen.getByRole('grid')
    expect(grid).toBeInTheDocument()

    const todayCell = document.querySelector('.calendar-cell[data-today="true"]')
    expect(todayCell).toBeInTheDocument()
    expect(todayCell?.getAttribute('data-current')).toBe('true')
    expect(document.activeElement).toBe(todayCell)

    // Other date cells in the month should not have data-current or data-today
    const nonTodayCells = document.querySelectorAll('.calendar-cell:not([data-today="true"])')
    expect(nonTodayCells.length).toBeGreaterThan(0)
    for (const cell of nonTodayCells) {
      expect(cell.getAttribute('data-current')).toBeNull()
    }
  })

  test('today cell retains data-current when selected', async () => {
    const todayStr = today(getLocalTimeZone()).toString()
    render(<DatePicker label="Event date" value={todayStr} onChange={() => {}} />)

    const button = screen.getByRole('button', { name: /pick event date from a calendar/i })
    await userEvent.click(button)

    const todayCell = document.querySelector('.calendar-cell[data-today="true"]')
    expect(todayCell).toBeInTheDocument()
    expect(todayCell?.getAttribute('data-current')).toBe('true')
    expect(todayCell?.getAttribute('data-selected')).toBe('true')
  })

  test('selecting a date calls onChange with formatted date', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker label="Event date" value="" onChange={onChange} />)

    const button = screen.getByRole('button', { name: /pick event date from a calendar/i })
    await user.click(button)

    const todayCell = document.querySelector('.calendar-cell[data-today="true"]')
    expect(todayCell).toBeInTheDocument()
    await user.click(todayCell!)

    const todayStr = today(getLocalTimeZone()).toString()
    expect(onChange).toHaveBeenCalledWith(todayStr)
  })

  test('clearing value via clear button resets value', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker label="Event date" value="2026-10-15" onChange={onChange} />)

    const clearBtn = screen.getByRole('button', { name: /clear event date/i })
    await user.click(clearBtn)
    expect(onChange).toHaveBeenCalledWith('')
  })

  test('works with withTime mode and selects date-time', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker label="Meeting" value="" onChange={onChange} withTime />)

    const button = screen.getByRole('button', { name: /pick meeting from a calendar/i })
    await user.click(button)

    const todayCell = document.querySelector('.calendar-cell[data-today="true"]')
    expect(todayCell).toBeInTheDocument()
    await user.click(todayCell!)

    const todayStr = today(getLocalTimeZone()).toString()
    expect(onChange).toHaveBeenCalledWith(expect.stringContaining(todayStr))
  })

  test('navigating month and closing without selection resets focus to current month on reopen', async () => {
    const user = userEvent.setup()
    render(<DatePicker label="Event date" value="" onChange={() => {}} />)

    const button = screen.getByRole('button', { name: /pick event date from a calendar/i })
    await user.click(button)

    // Navigate to next month
    const nextBtn = screen.getAllByRole('button', { name: /next/i })[0]
    await user.click(nextBtn)

    // Close popover with Escape
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()

    // Reopen popover
    await user.click(button)

    // Check if today is shown and focused
    const todayCell = document.querySelector('.calendar-cell[data-today="true"]')
    expect(todayCell).toBeInTheDocument()
    expect(todayCell?.getAttribute('data-current')).toBe('true')
    expect(document.activeElement).toBe(todayCell)
  })
})
