import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

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
