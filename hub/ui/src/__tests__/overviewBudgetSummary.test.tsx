import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OverviewBudgetSummary } from '@/components/overview/OverviewBudgetSummary'

/** `project.ai_nano_aiu` lands at task 6.1 (`a-copilot-run-shows-its-credits`, design D6's
 *  byte-identity test). Mutable so task 1.18's tests can add it without a type the project doesn't
 *  carry yet; today's project object has no such key, matching the real route's current response. */
let project: Record<string, unknown> = { total_tokens: 2608590, measured_turns: 45, unavailable_turns: 0 }

vi.mock('@/api/accounting', () => ({
  useAccounting: () => ({
    isLoading: false,
    data: {
      project,
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
  beforeEach(() => {
    project = { total_tokens: 2608590, measured_turns: 45, unavailable_turns: 0 }
  })

  it('keeps the landing page compact and translates allowance telemetry', () => {
    render(<OverviewBudgetSummary />)

    expect(screen.getByLabelText('Budget summary')).toHaveTextContent('2,608,590 tokens')
    expect(screen.getByText(/Weekly allowance exhausted/)).toBeInTheDocument()
    expect(screen.queryByText('Project token budget')).not.toBeInTheDocument()
    expect(screen.queryByText(/\{"status"/)).not.toBeInTheDocument()
  })

  describe('AI credits row (task 1.18)', () => {
    it('shows an AI credits row when the project reports credits', () => {
      project = { ...project, ai_nano_aiu: 275_856_000 }
      const { container } = render(<OverviewBudgetSummary />)
      expect(container.textContent).toContain('0.28 AI credits')
    })

    it('shows no AI credits row when the project has nothing to report (control)', () => {
      const { container } = render(<OverviewBudgetSummary />)
      expect(container.textContent).not.toContain('AI credits')
    })
  })
})
