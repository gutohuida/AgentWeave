import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import type { Stall } from '@/api/stalls'
import type { Task } from '@/api/tasks'
import { BuildView } from '@/components/builds/BuildView'
import { NO_ADDRESS, type BuildRead } from '@/components/builds/buildViewModel'
import { StallRemedies } from '@/components/stalls/StallRemedies'
import { stallNotice } from '@/lib/stalls'
import { TaskCard } from '@/components/tasks/TaskCard'

/** `a-two-profile-build-cannot-deadlock-and-a-stall-says-so`, D5: a stall reads Stalled on the
 *  build page header and the task's board card (FR-7), offers its remedies as controls that act in
 *  place (FR-8), and its notice reads as a sentence in the operator's words (FR-9). The stall is
 *  the shape `GET /stalls?open=true` returns for the checker-has-no-runner case
 *  (`unstaffed-names-missing-runner`). */

const nameCheckerMutate = vi.fn()
const agents = [
  { name: 'Developer', runner_id: 'runner-1' },
  { name: 'QA', runner_id: null },
  { name: 'QA2', runner_id: 'runner-2' },
  { name: 'mender', runner_id: 'runner-3' },
]

// The tasks route's payload for T: finished, waiting for a review nobody can take.
const T = {
  id: 'task-5bb70fe79ee0',
  readable_id: 'TPBCD-4',
  title: 'A stall reads Stalled',
  status: 'completed',
  priority: 'medium',
  assignee: 'Developer',
  builder: 'Developer',
  checker: 'QA',
  stage: 'waiting_for_review',
  stage_since: '2026-11-21T15:00:00Z',
} as unknown as Task

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: agents }),
}))
vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  useTask: () => ({ data: T }),
}))
vi.mock('@/api/stalls', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/stalls')>()),
  useNameChecker: () => ({ mutate: nameCheckerMutate, isPending: false }),
}))
// The operator's review is the task drawer (Land it reviews and approves); its own tests cover it.
vi.mock('@/components/tasks/TaskDetailDrawer', () => ({
  TaskDetailDrawer: ({ task, onClose, initialView }: { task: Task; onClose: () => void; initialView?: string }) => (
    <div role="dialog" aria-label={`Your review of ${task.readable_id}`} data-view={initialView}>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </div>
  ),
}))

const REASON =
  "TPBCD-4's checker QA has no runner bound, so its check is held and given to nobody else. Bind a runner to QA, or name a different checker."

function stall(over: Partial<Stall> = {}): Stall {
  return {
    id: 'stall-1a2b3c4d5e6f',
    key: 'review_unstaffed:task-5bb70fe79ee0',
    cause: 'review_unstaffed',
    reason: REASON,
    task_id: T.id,
    loop_id: 'loop-85f2eaedf613',
    first_seen_at: '2026-11-21T15:05:00+00:00',
    last_seen_at: '2026-11-21T15:10:00+00:00',
    seen_count: 2,
    conversation_id: null,
    mender_turns: 0,
    outcome: 'open',
    outcome_detail: '',
    ended_at: null,
    remedies: ['name_checker', 'review_yourself'],
    ...over,
  }
}

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>)
}

const READ: BuildRead = {
  build: {
    id: 'build-98c8e72b7b5f',
    document_id: 'spdoc-a9382cf4b71e',
    document_title: 'A two-profile build cannot deadlock',
    document_path: null,
    state: 'running',
    level: 'reviewed',
    created_at: '2026-11-21T14:32:01Z',
    stopped_at: null,
    stop_reason: null,
    // The build list's own need, which the sidebar reads as Stalled.
    needs_operator: { kind: 'stalled', text: REASON },
    attention_dismissed: false,
  },
  tasks: [
    {
      id: T.id,
      ref: 'TPBCD-4',
      title: T.title,
      status: 'completed',
      declared: true,
      builder: 'Developer',
      checker: 'QA',
      last_change_at: '2026-11-21T15:00:00Z',
      needs_operator: { kind: 'stalled', text: REASON },
      requirements: [],
      runs: [],
      send_backs: [],
    },
  ],
  build_runs: [],
  as_of: '2026-11-21T15:10:00Z',
}

beforeEach(() => nameCheckerMutate.mockReset())
afterEach(cleanup)

describe('a stall reads Stalled (FR-7, stalled-build-header-and-card)', () => {
  it('shows Stalled with its icon on T’s card, over Ready for review', () => {
    wrap(<TaskCard task={T} stall={stall()} onOpen={() => {}} />)
    const line = screen.getByTestId(`task-stage-${T.id}`)
    expect(line).toHaveTextContent('Stalled')
    expect(line.querySelector('svg')).not.toBeNull()
    expect(line).not.toHaveTextContent('Ready for review')
    expect(line).not.toHaveTextContent('Running')
  })

  it('shows the stage again for the same card with no open stall, and for a closed task', () => {
    const { rerender } = wrap(<TaskCard task={T} onOpen={() => {}} />)
    expect(screen.getByTestId(`task-stage-${T.id}`)).toHaveTextContent('Ready for review')
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TaskCard task={{ ...T, status: 'approved' }} stall={stall()} onOpen={() => {}} />
      </QueryClientProvider>,
    )
    expect(screen.getByTestId(`task-stage-${T.id}`)).not.toHaveTextContent('Stalled')
  })

  it('shows Stalled with its icon in the build page header, not Running', () => {
    wrap(<BuildView read={READ} status="ready" now={new Date('2026-11-21T15:11:00Z')} address={NO_ADDRESS} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} stalls={[stall()]} />)
    const state = screen.getByTestId('build-state')
    expect(state).toHaveTextContent(/^Stalled$/)
    expect(state.querySelector('svg')).not.toBeNull()
    expect(screen.getByRole('banner')).not.toHaveTextContent('Running')
  })

  it('reads Running while nothing about the build stalled', () => {
    const calm: BuildRead = { ...READ, build: { ...READ.build, needs_operator: null }, tasks: [{ ...READ.tasks[0]!, needs_operator: null }] }
    wrap(<BuildView read={calm} status="ready" now={new Date('2026-11-21T15:11:00Z')} address={NO_ADDRESS} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} stalls={[]} />)
    expect(screen.getByTestId('build-state')).toHaveTextContent(/^Running$/)
  })
})

describe('a stall’s remedies are controls (FR-8, stall-remedy-controls-work)', () => {
  it('names a different checker from the card, in place, offering only profiles that can check', () => {
    const onOpen = vi.fn()
    wrap(<TaskCard task={T} stall={stall()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Name a different checker for TPBCD-4' }))
    const picker = screen.getByRole('group', { name: 'Who checks TPBCD-4 instead' })
    // Not the builder, not the stalled checker, not the mender; one with no runner is not offered as able.
    expect(within(picker).queryByRole('button', { name: /Developer/ })).toBeNull()
    expect(within(picker).queryByRole('button', { name: /mender/ })).toBeNull()
    expect(within(picker).queryByRole('button', { name: 'Make QA the checker of TPBCD-4' })).toBeNull()
    fireEvent.click(within(picker).getByRole('button', { name: 'Make QA2 the checker of TPBCD-4' }))
    expect(nameCheckerMutate).toHaveBeenCalledTimes(1)
    expect(nameCheckerMutate.mock.calls[0]![0]).toEqual({ taskId: T.id, agent: 'QA2', taskRef: 'TPBCD-4' })
    // The Hub's answer is said beside the controls; the card was never opened.
    act(() => nameCheckerMutate.mock.calls[0]![1].onSuccess({ next_turn: "QA2 is TPBCD-4's checker, and its review turn is queued." }))
    expect(screen.getByRole('status')).toHaveTextContent("QA2 is TPBCD-4's checker, and its review turn is queued.")
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('says the Hub’s refusal beside the controls', () => {
    wrap(<StallRemedies stall={stall()} taskRef="TPBCD-4" />)
    fireEvent.click(screen.getByRole('button', { name: 'Name a different checker for TPBCD-4' }))
    fireEvent.click(screen.getByRole('button', { name: 'Make QA2 the checker of TPBCD-4' }))
    act(() => nameCheckerMutate.mock.calls[0]![1].onError(new ApiError(422, JSON.stringify({ detail: 'QA2 has no runner bound, so it cannot check this task.' }))))
    expect(screen.getByRole('alert')).toHaveTextContent('QA2 has no runner bound')
  })

  it('opens the operator’s review of T over the build page, without leaving it', () => {
    const onAddressChange = vi.fn()
    wrap(<BuildView read={READ} status="ready" now={new Date('2026-11-21T15:11:00Z')} address={NO_ADDRESS} onAddressChange={onAddressChange} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} stalls={[stall()]} />)
    const notice = screen.getByRole('region', { name: 'Stalled: TPBCD-4' })
    expect(within(notice).getByRole('button', { name: 'Name a different checker for TPBCD-4' })).toBeInTheDocument()
    fireEvent.click(within(notice).getByRole('button', { name: 'Review TPBCD-4 yourself' }))
    // Opened on Details, where the operator's review is (Land it).
    expect(screen.getByRole('dialog', { name: 'Your review of TPBCD-4' })).toHaveAttribute('data-view', 'details')
    expect(onAddressChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('offers no control for a stall whose cause has no remedy, or from a Hub that sends none', () => {
    const { container, rerender } = wrap(<StallRemedies stall={stall({ cause: 'dead_run', remedies: [] })} />)
    expect(container).toBeEmptyDOMElement()
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <StallRemedies stall={stall({ remedies: undefined })} />
      </QueryClientProvider>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('a stall notice reads as a sentence (FR-9, stall-notice-sentence-case)', () => {
  it('starts with a capital and carries no conv- or task- identifiers', () => {
    const lower =
      "this task names 'QA' as its reviewer, and that agent is the one that completed task-5bb70fe79ee0 in conv-12fa014cd8e5"
    for (const text of [stallNotice(lower, 'TPBCD-4'), stallNotice(lower), stallNotice(REASON, 'TPBCD-4')]) {
      expect(text.charAt(0)).toMatch(/[A-Z]/)
      expect(text).not.toMatch(/\b(task|conv)-[0-9a-f]+/)
      expect(text).toMatch(/[.!?]$/)
    }
    expect(stallNotice(lower, 'TPBCD-4')).toBe(
      "This task names 'QA' as its reviewer, and that agent is the one that completed TPBCD-4 in a thread.",
    )
    expect(stallNotice(REASON)).toBe(REASON)
  })

  it('is what the build page shows beside the controls, naming profiles by name', () => {
    const lower = { ...stall(), reason: "this task names 'QA' as its checker; see conv-12fa014cd8e5" }
    wrap(<BuildView read={READ} status="ready" now={new Date('2026-11-21T15:11:00Z')} address={NO_ADDRESS} onAddressChange={vi.fn()} onRetry={vi.fn()} onOpenDocument={vi.fn()} onOpenConversation={vi.fn()} stalls={[lower]} />)
    const notice = screen.getByRole('region', { name: 'Stalled: TPBCD-4' })
    expect(notice).toHaveTextContent("This task names 'QA' as its checker; see a thread.")
    expect(notice.textContent).not.toMatch(/\b(task|conv)-[0-9a-f]+/)
  })
})
