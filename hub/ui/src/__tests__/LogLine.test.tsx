import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LogLine } from '@/components/logs/LogLine'

const entry = {
  id: 'log-1',
  event_type: 'task_updated',
  severity: 'info',
  timestamp: '2026-08-22T15:00:00Z',
  agent: 'codex',
  data: { task_id: 'task-1', status: 'in_progress' },
}

describe('LogLine disclosure', () => {
  it('is keyboard reachable and toggles detail with Enter and Space', () => {
    render(<LogLine entry={entry} />)
    const disclosure = screen.getByRole('button', { name: 'Expand task_updated log entry' })

    expect(disclosure).toHaveAttribute('tabindex', '0')
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')

    fireEvent.keyDown(disclosure, { key: 'Enter' })
    expect(screen.getByRole('button', { name: 'Collapse task_updated log entry' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/"task_id": "task-1"/)).toBeInTheDocument()

    fireEvent.keyDown(disclosure, { key: ' ' })
    expect(screen.queryByText(/"task_id": "task-1"/)).not.toBeInTheDocument()
  })

  it('does not make a data-less row pretend to be expandable', () => {
    render(<LogLine entry={{ ...entry, id: 'log-2', data: {} }} />)
    expect(screen.queryByRole('button', { name: /task_updated log entry/ })).not.toBeInTheDocument()
  })
})

describe('LogLine state styling', () => {
  // Hover used to be an inline onMouseEnter handler, which no keyboard user could ever trigger.
  // The class is the seam CSS hangs :hover and :focus-visible off, so the name is worth pinning:
  // renaming it in one place and not the other silently removes both states.
  it('carries the CSS hook that owns hover and focus, not an inline background', () => {
    render(<LogLine entry={entry} />)
    const row = screen.getByRole('button', { name: 'Expand task_updated log entry' })

    expect(row).toHaveClass('log-row-main')
    expect(row.style.background).toBe('')
  })

  it('flags an arriving row for the flash only while it is new', () => {
    const { rerender } = render(<LogLine entry={entry} isNew />)
    expect(screen.getByRole('button', { name: /task_updated log entry/ })).toHaveClass('is-new')

    rerender(<LogLine entry={entry} />)
    expect(screen.getByRole('button', { name: /task_updated log entry/ })).not.toHaveClass('is-new')
  })

  it('confirms a copy in green, the same colour EventRow uses for the same confirmation', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    })
    render(<LogLine entry={entry} />)

    fireEvent.click(screen.getByTitle('Copy entry'))

    await waitFor(() => {
      const tick = screen.getByTitle('Copy entry').querySelector('svg')
      expect(tick).toHaveStyle({ color: 'var(--green)' })
    })
  })
})
