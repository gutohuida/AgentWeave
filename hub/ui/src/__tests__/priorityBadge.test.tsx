import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { PriorityBadge } from '@/components/common/Badge'

afterEach(cleanup)

describe('PriorityBadge', () => {
  it('uses warning and danger semantics for high-impact priorities', () => {
    render(
      <>
        <PriorityBadge priority="low" />
        <PriorityBadge priority="high" />
        <PriorityBadge priority="critical" />
      </>,
    )

    expect(screen.getByTestId('priority-badge-low')).toHaveStyle({ color: 'var(--text-2)' })
    expect(screen.getByTestId('priority-badge-high')).toHaveStyle({ color: 'var(--amber)' })
    expect(screen.getByTestId('priority-badge-critical')).toHaveStyle({ color: 'var(--red)' })
    expect(screen.getByTestId('priority-badge-high').querySelector('svg')).not.toBeNull()
    expect(screen.getByTestId('priority-badge-critical').querySelector('svg')).not.toBeNull()
  })
})
