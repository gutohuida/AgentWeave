import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { SpecBuildsSection } from '@/components/spec/page/SpecBuilds'
import { buildViews } from '@/components/spec/page/adapt'
import type { BuildFigures } from '@/api/buildFigures'
import type { SpecBuild } from '@/api/spec'

// The route's payload for a build shaped like AWOAW (2026-11-05): 2 h of check runs, one timed out.
const AWOAW: BuildFigures = {
  id: 'build-1',
  runs: 9,
  time: { building: 3600, reviewing: 600, checks: 300, held: 0, review: 0, waiting: 0 },
  cost: { build: 1, review: 1, lead: 0, mend: 0 },
  unpriced: 0,
  checks: { runs: 6, passed: 4, failed: 1, seconds: 7200, timed_out: 1, running_seconds: 5400, waiting_seconds: 1800, no_slot_runs: 0 },
  landing: { landed: 2, total_seconds: 19200, longest_seconds: 19080, waiting: 1, longest_waiting_seconds: 600 },
}

function card(figures: BuildFigures) {
  const build = { id: 'build-1', state: 'running', driver: 'flow', level: 'reviewed', builders: ['Dev'], reviewers: [], lead: null, landing: 'main', created_at: '2026-11-05T10:00:00Z', stopped_at: null, budget_cap_usd: null } as unknown as SpecBuild
  const builds = buildViews([build], [], { 'build-1': figures })
  render(<SpecBuildsSection builds={builds} canBuild={false} now={new Date('2026-11-05T12:00:00Z')} flash={null} onStartBuild={vi.fn()} onOpenRuns={vi.fn()} onStop={vi.fn()} onCopyLink={vi.fn()} />)
  return screen.getByTestId('build-checks-meter')
}

describe('the build card Checks meter', () => {
  it('shows running and waiting with a 2 h total, the timed-out count and the landing wait', () => {
    const meter = card(AWOAW)
    expect(within(meter).getByText('2h 0m')).toBeInTheDocument()
    expect(within(meter).getByText('Running').nextSibling?.textContent).toBe('1h 30m')
    expect(within(meter).getByText('Waiting for a slot').nextSibling?.textContent).toBe('30m 0s')
    expect(within(meter).getByTestId('build-checks-timed-out').textContent).toBe('1')
    const wait = within(meter).getByTestId('build-landing-wait').textContent ?? ''
    expect(wait).toContain('longest 5h 18m')
    expect(wait).toContain('1 still waiting')
  })

  it('reads unknown waiting as unknown, not 0', () => {
    const meter = card({ ...AWOAW, checks: { ...AWOAW.checks, running_seconds: 7200, waiting_seconds: null, no_slot_runs: 6 } })
    expect(within(meter).getByText('Waiting for a slot').nextSibling?.textContent).toBe('unknown')
    expect(within(meter).getByText('Running').nextSibling?.textContent).toBe('2h 0m')
  })
})
