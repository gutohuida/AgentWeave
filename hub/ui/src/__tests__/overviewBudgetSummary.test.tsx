import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OverviewBudgetSummary } from '@/components/overview/OverviewBudgetSummary'

vi.mock('@/api/accounting', () => ({
  useAccounting: () => ({
    isLoading: false,
    data: {
      project: { total_tokens: 2608590, measured_turns: 45, unavailable_turns: 0 },
      agents: [
        { agent: 'alice', total_tokens: 1060898 },
        { agent: 'bob', total_tokens: 885388 },
      ],
      budget: { exhausted: false },
      preferred_display: {
        kind: 'allowance',
        label: 'Rate-limit allowance',
        allowance: { status: 'rejected', rateLimitType: 'seven_day', resetsAt: 1787493600 },
      },
    },
  }),
}))

describe('overview budget summary', () => {
  it('keeps the landing page compact and translates allowance telemetry', () => {
    render(<OverviewBudgetSummary />)

    expect(screen.getByLabelText('Budget summary')).toHaveTextContent('2,608,590 tokens')
    expect(screen.getByText(/Weekly allowance exhausted/)).toBeInTheDocument()
    expect(screen.queryByText('Project token budget')).not.toBeInTheDocument()
    expect(screen.queryByText(/\{"status"/)).not.toBeInTheDocument()
  })
})
