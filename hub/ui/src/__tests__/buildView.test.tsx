import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BuildSummary } from '@/components/builds/BuildSummary'
import { BuildView } from '@/components/builds/BuildView'
import {
  addressQuery,
  buildTotals,
  costTotal,
  leftOut,
  NO_ADDRESS,
  parseAddress,
  summaryOf,
  timelineOf,
  totalCell,
  type BuildRead,
  type BuildRunRead,
  type BuildTaskRead,
  type SendBackRead,
} from '@/components/builds/buildViewModel'

const NOW = new Date('2026-11-17T12:00:00Z')

function run(id: string, over: Partial<BuildRunRead> = {}): BuildRunRead {
  return {
    id,
    role: 'build',
    agent: 'Developer',
    model: 'claude-sonnet-5',
    conversation_id: `conv-${id}`,
    started_at: '2026-11-17T09:00:00Z',
    ended_at: '2026-11-17T09:10:00Z',
    status: 'completed',
    cost_state: 'measured',
    cost_usd_micros: 1_000_000,
    tokens: null,
    moves: [{ from: 'in_progress', to: 'completed' }],
    mend: null,
    ...over,
  }
}

function sendBack(at: string, over: Partial<SendBackRead> = {}): SendBackRead {
  return { sequence: 1, at, to: 'revision_needed', by: { kind: 'agent', agent: 'QA' }, run_id: 'r2', reason_class: 'defect', reason: 'Sent back as defect: the total ignores unpriced runs', note: '', ...over }
}

function task(id: string, over: Partial<BuildTaskRead> = {}): BuildTaskRead {
  return {
    id,
    ref: id.toUpperCase(),
    title: `Task ${id}`,
    status: 'approved',
    declared: true,
    builder: 'Developer',
    checker: 'QA',
    last_change_at: '2026-11-17T11:00:00Z',
    needs_operator: null,
    requirements: [],
    runs: [],
    send_backs: [],
    ...over,
  }
}

/** A built, sent back (defect), rebuilt, reviewed and approved task with a mender turn; a task with
 *  an unpriced run beside a priced one; a task with only unpriced runs that waits on the operator;
 *  and a fix task added later. */
const READ: BuildRead = {
  build: { id: 'build-1', document_id: 'doc-1', document_title: 'A build', document_path: null, state: 'running', level: 'reviewed', created_at: '2026-11-17T08:00:00Z', stopped_at: null, stop_reason: null },
  tasks: [
    task('a-1', {
      requirements: [
        { identifier: 'FR-1', evidence: 'accepted' },
        { identifier: 'FR-2', evidence: 'awaiting' },
      ],
      runs: [
        run('r1', { started_at: '2026-11-17T09:00:00Z' }),
        run('r2', { role: 'review', agent: 'QA', started_at: '2026-11-17T09:20:00Z', ended_at: '2026-11-17T09:30:00Z', moves: [{ from: 'under_review', to: 'revision_needed' }] }),
        run('r3', { started_at: '2026-11-17T09:40:00Z', ended_at: '2026-11-17T09:50:00Z' }),
        run('r4', { role: 'mender', agent: 'mender', started_at: '2026-11-17T09:55:00Z', ended_at: '2026-11-17T09:56:00Z', moves: [], mend: { cause: 'stuck_task', outcome: 'fixed', detail: null } }),
        run('r5', { role: 'review', agent: 'QA', started_at: '2026-11-17T10:00:00Z', ended_at: '2026-11-17T10:05:00Z', moves: [{ from: 'under_review', to: 'approved' }] }),
      ],
      send_backs: [sendBack('2026-11-17T09:29:00Z')],
    }),
    task('b-2', { runs: [run('r6'), run('r7', { cost_state: 'unpriced', cost_usd_micros: null, started_at: '2026-11-17T09:30:00Z' })] }),
    task('c-3', {
      status: 'under_review',
      needs_operator: { kind: 'stalled', text: 'QA could not start' },
      runs: [run('r8', { cost_state: 'unpriced', cost_usd_micros: null })],
    }),
    task('fix-4', { declared: false, runs: [] }),
  ],
  build_runs: [],
  as_of: '2026-11-17T12:00:00Z',
}

function renderView(read: BuildRead, address = NO_ADDRESS) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <BuildView read={read} status="ready" now={NOW} address={address} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('build view model', () => {
  it('places a send-back between the build it judged and the rebuild it caused, oldest first', () => {
    const t = READ.tasks[0]!
    const labels = timelineOf(t.runs, t.send_backs, NOW).map((i) => i.label)
    expect(labels).toEqual(['Build 1', 'Review 1', 'Send-back 1', 'Build 2', 'Mender 1', 'Review 2'])
    // The route's order does not decide the story: the same runs given newest first read the same.
    expect(timelineOf([...t.runs].reverse(), t.send_backs, NOW).map((i) => i.label)).toEqual(labels)
  })

  it('collapses repeated mender turns into one counted row showing the worst outcome', () => {
    const runs = [
      run('m1', { role: 'mender', agent: 'mender', started_at: '2026-11-17T09:00:00Z', moves: [], mend: { cause: 'stuck_task', outcome: 'fixed', detail: null } }),
      run('m2', { role: 'mender', agent: 'mender', started_at: '2026-11-17T09:10:00Z', moves: [], mend: { cause: 'stuck_task', outcome: 'gave_up', detail: null } }),
      run('m3', { role: 'mender', agent: 'mender', started_at: '2026-11-17T09:20:00Z', moves: [], mend: { cause: 'stuck_task', outcome: 'fixed', detail: null } }),
    ]
    const [group] = timelineOf(runs, [], NOW)
    expect(group).toMatchObject({ kind: 'group', label: 'Mender ×3', move: { tone: 'bad' } })
  })

  it('collapses a build bounced by the same failing checks again and again into one row, keeping every run', () => {
    const runs = Array.from({ length: 5 }, (_, i) => run(`b${i}`, { role: 'build', agent: 'Dev', started_at: `2026-11-17T09:${String(i * 10).padStart(2, '0')}:00Z` }))
    const sendBacks = Array.from({ length: 4 }, (_, i) => ({
      sequence: i + 1,
      at: `2026-11-17T09:${String(i * 10 + 5).padStart(2, '0')}:00Z`,
      to: 'revision_needed' as const,
      by: { kind: 'checks' as const },
      run_id: null,
      reason_class: 'broken-check',
      reason: `The project's checks failed on check run chk-${i}a${i}b.`,
      note: '',
    }))
    const items = timelineOf(runs, sendBacks, NOW)
    expect(items.map((i) => i.label)).toEqual(['Build ×4', 'Build 5'])
    const [group] = items
    expect(group).toMatchObject({
      kind: 'group',
      detail: 'Build 1 to Build 4, each sent back by the landing checks',
      sendBacks: 4,
      reason: "The project's checks failed.",
      move: { text: 'Sent back 4 times', tone: 'bad' },
    })
    // Every run is still there to open, in order.
    expect(group!.kind === 'group' && group.runs.map((r) => r.label)).toEqual(['Build 1', 'Build 2', 'Build 3', 'Build 4'])
  })

  it('collapses one agent building again and again, but not two builds in a row', () => {
    const many = Array.from({ length: 4 }, (_, i) => run(`b${i}`, { role: 'build', agent: 'Dev', started_at: `2026-11-17T09:0${i}:00Z` }))
    expect(timelineOf(many, [], NOW).map((i) => i.label)).toEqual(['Build ×4'])
    expect(timelineOf(many.slice(0, 2), [], NOW).map((i) => i.label)).toEqual(['Build 1', 'Build 2'])
  })

  it('never totals unpriced as zero, and says what a total leaves out', () => {
    const mixed = costTotal(READ.tasks[1]!.runs)
    expect(totalCell(mixed)).toEqual({ kind: 'cost', usd: 1 })
    expect(leftOut(mixed)).toBe('Leaves out 1 unpriced run')
    const only = costTotal(READ.tasks[2]!.runs)
    expect(totalCell(only)).toEqual({ kind: 'unpriced' })
  })

  it('round-trips the address', () => {
    const address = { task: 'A-1', run: 'r3', filter: 'needs-you' as const }
    expect(parseAddress(addressQuery(address))).toEqual(address)
  })
})

describe('build view', () => {
  it('lists every task once, in the route order, with status in words', () => {
    renderView(READ)
    const rows = within(screen.getByRole('region', { name: 'Tasks' })).getAllByRole('button', { name: /^Open runs of / })
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(['Open runs of A-1', 'Open runs of B-2', 'Open runs of C-3', 'Open runs of FIX-4'])
    expect(screen.getByText('added later')).toBeInTheDocument()
    expect(screen.getAllByText('Approved').length).toBeGreaterThan(0)
  })

  it('opens a task at its address, with each run named for its trace', () => {
    renderView(READ, { ...NO_ADDRESS, task: 'A-1' })
    const timeline = screen.getByRole('list', { name: 'Runs of A-1' })
    expect(within(timeline).getByRole('button', { name: 'Open trace: Build 2' })).toBeInTheDocument()
    expect(within(timeline).getByText('Defect')).toBeInTheDocument()
    expect(within(timeline).getByText('The total ignores unpriced runs')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Evidence of A-1' })).toHaveTextContent('FR-2 awaiting')
  })

  it('shows the same counts in both summaries and the full view (summary parity)', () => {
    const summary = summaryOf(READ, NOW)
    const totals = buildTotals(READ, NOW)
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <div data-testid="panel">
          <BuildSummary variant="panel" summary={summary} hrefFor={() => '#'} />
        </div>
        <div data-testid="strip">
          <BuildSummary variant="strip" summary={summary} hrefFor={() => '#'} />
        </div>
      </QueryClientProvider>,
    )
    renderView(READ)
    for (const id of ['panel', 'strip']) {
      const box = screen.getByTestId(id)
      expect(within(box).getByTestId('summary-send-backs')).toHaveTextContent(String(totals.sendBacks))
      expect(within(box).getByTestId('summary-needs')).toHaveTextContent('1 needs you')
      expect(within(box).getByRole('link', { name: 'Open build' })).toBeInTheDocument()
    }
    // The strip sits in the spec page's build card, whose head and meters carry state, tasks and cost.
    const panel = screen.getByTestId('panel')
    expect(within(panel).getByTestId('summary-approved')).toHaveTextContent(`${totals.approved} of ${totals.tasks} approved`)
    expect(within(panel).getByTestId('summary-cost')).toHaveTextContent('$6.00')
    expect(within(panel).getByTestId('summary-cost')).toHaveTextContent('+2 unpriced')
    expect(screen.getByTestId('build-approved')).toHaveTextContent(`${totals.approved} of ${totals.tasks}`)
    expect(screen.getByTestId('build-send-backs')).toHaveTextContent(String(totals.sendBacks))
    expect(screen.getByTestId('build-needs')).toHaveTextContent('1 task')
    expect(screen.getByTestId('build-cost')).toHaveTextContent('$6.00')
    expect(screen.getByTestId('build-cost-note')).toHaveTextContent('Leaves out 2 unpriced runs')
  })
})
