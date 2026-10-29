import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectWork, WorkView } from '@/components/activity/ProjectWork'
import type { Grouping, WorkTally } from '@/api/stats'
import payload from './fixtures/workTally.json'

/**
 * The project's Work section (`project-stats-come-from-the-same-records`, task `view`). `TALLY` is
 * the Hub's own answer: `fixtures/workTally.json` is `GET /stats` read on the seeded project of
 * `hub/tests/test_project_stats_come_from_the_same_records.py` (two specs, one with two builds and
 * one with work before any build, a mender stall, an unpriced run, a Copilot run), not a shape
 * written by hand, and the groups are in the order the route returned them.
 */
const TALLY = payload as unknown as WorkTally

const stats = vi.hoisted(() => ({ since: [] as Array<string | null> }))
vi.mock('@/api/stats', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/stats')>()
  return {
    ...actual,
    useProjectStats: (since: string | null) => {
      stats.since.push(since)
      return { data: payload, isLoading: false, isError: false }
    },
  }
})

function view(grouping: Grouping) {
  return render(<WorkView tally={TALLY} grouping={grouping} onGrouping={vi.fn()} since="" onSince={vi.fn()} />)
}

describe('ProjectWork', () => {
  it('shows each spec with the mender on a line of its own and unpriced runs beside the cost', () => {
    view('spec')
    const a = screen.getByTestId('work-row-spec-doc-a')
    expect(within(a).getByTestId('work-cost').textContent).toContain('$6.50')
    expect(within(a).getByTestId('work-mending').textContent).toContain('$0.50')
    expect(within(a).getByTestId('work-mending').textContent).toContain('1 run')
    expect(within(a).getByTestId('work-building').textContent).toContain('$5.00')
    expect(within(a).getByTestId('work-reviewing').textContent).toContain('$1.00')
    // The unpriced run is counted beside the cost, never added as $0.
    const b = screen.getByTestId('work-row-spec-doc-b')
    expect(within(b).getByTestId('work-cost').textContent).toContain('1 unpriced')
    expect(within(b).getByTestId('work-cost').textContent).toContain('$0.90')
    // Copilot credits are in their own unit.
    const none = screen.getByTestId('work-row-spec-none')
    expect(within(none).getByTestId('work-cost').textContent).toContain('4.00 AIU')
  })

  it('lists a spec’s builds and its work before any build under it', () => {
    view('spec')
    expect(screen.getByTestId('work-build-b-a1').textContent).toContain('Build 1')
    expect(screen.getByTestId('work-build-b-a2').textContent).toContain('Build 2')
    expect(screen.getByTestId('work-before-doc-b')).toBeInTheDocument()
    // The spec’s check line equals its build’s.
    expect(within(screen.getByTestId('work-row-spec-doc-a')).getByTestId('work-checks').textContent).toContain('1 run')
  })

  it('renders the totals row of every grouping with the same cost', () => {
    for (const grouping of ['spec', 'agent', 'model', 'level'] as Grouping[]) {
      const { unmount } = view(grouping)
      expect(within(screen.getByTestId('work-totals')).getByTestId('work-cost').textContent).toContain('$7.65')
      unmount()
    }
  })

  it('groups by agent, model and level, with what has none under its own label', () => {
    const { unmount } = view('agent')
    expect(screen.getByTestId('work-row-agent-qa')).toBeInTheDocument()
    expect(screen.getByTestId('work-row-agent-mender')).toBeInTheDocument()
    unmount()
    const model = view('model')
    expect(screen.getByTestId('work-row-model-opus')).toBeInTheDocument()
    model.unmount()
    view('level')
    expect(screen.getByTestId('work-row-level-reviewed')).toBeInTheDocument()
    expect(screen.getByTestId('work-row-level-none').textContent).toContain('no level recorded')
  })

  it('names the Hub’s own calls apart from the rows', () => {
    view('spec')
    expect(screen.getByTestId('work-hub-line').textContent).toContain('$0.10')
  })

  it('switches grouping and reads from the date chosen', async () => {
    stats.since.length = 0
    render(<ProjectWork />)
    expect(screen.getByTestId('work-row-spec-doc-a')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    expect(screen.getByTestId('work-row-agent-qa')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Since'), '2026-10-26')
    expect(stats.since[0]).toBeNull()
    expect(stats.since[stats.since.length - 1]).toBe('2026-10-26T00:00:00Z')
  })
})
