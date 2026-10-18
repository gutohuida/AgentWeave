import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvidenceBrowser } from '@/components/evidence/EvidenceBrowser'
import { EvidenceLink } from '@/components/evidence/EvidenceLink'
import { useConfigStore } from '@/store/configStore'
import type { EvidencePiece } from '@/api/spec'

/**
 * The evidence browser (slice evidence-browser). `EVIDENCE` is in the order `GET /spec/evidence`
 * returns — oldest first — and the browser deliberately shows newest first, so a renderer that
 * kept the route's order, or sorted by something else, fails the ordering test (CLAUDE.md: a
 * consumer's test uses the route's real order).
 *
 * Two documents each have an `FR-1`: the reason links focus a requirement by its durable id.
 */

function piece(overrides: Partial<EvidencePiece> & { id: string }): EvidencePiece {
  return {
    summary: '',
    kind: 'test_result',
    locator: null,
    actor_kind: 'agent',
    actor: 'Builder',
    run_id: null,
    task_id: 'task-a',
    review_state: 'awaiting',
    latest_review: null,
    produced_at: '2026-10-17T10:00:00Z',
    footprint: null,
    command: null,
    output: null,
    covers: null,
    superseded_by: null,
    ...overrides,
  }
}

const WATCH = { path: 'spec/changes/watch/spec.json', title: 'Folder watching' }
const TAGS = { path: 'spec/changes/tags/spec.json', title: 'Tags' }

const EVIDENCE: EvidencePiece[] = [
  piece({
    id: 'ev-1', summary: 'rename works', produced_at: '2026-10-17T10:00:00Z', review_state: 'accepted',
    requirement_id: 'spreq-watch-1',
    requirement: { identifier: 'FR-1', statement: 'A watched folder can be renamed.', document: WATCH },
  }),
  piece({
    id: 'ev-2', summary: 'tag list loads', produced_at: '2026-10-17T11:00:00Z', task_id: 'task-b',
    actor: 'Tester', command: 'npm run tags',
    requirement_id: 'spreq-tags-1',
    requirement: { identifier: 'FR-1', statement: 'Tags are listed.', document: TAGS },
  }),
  piece({
    id: 'ev-3', summary: 'rename survives restart', produced_at: '2026-10-17T12:00:00Z', review_state: 'rejected',
    requirement_id: 'spreq-watch-1',
    requirement: { identifier: 'FR-1', statement: 'A watched folder can be renamed.', document: WATCH },
  }),
]

let served: EvidencePiece[] = EVIDENCE

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useProjectEvidence: () => ({ data: { evidence: served }, isLoading: false, isError: false }),
    useEvidenceReviews: () => ({ data: { reviews: [] }, isError: false }),
    useEvidenceDiff: () => ({ data: undefined, isLoading: false, isError: false }),
  }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({
      data: {
        tasks: [
          { id: 'task-a', title: 'Watch folders', status: 'approved' },
          { id: 'task-b', title: 'List tags', status: 'in_progress' },
        ],
      },
      error: null,
    }),
  }
})

function browse(focus: string | null = null) {
  const onFocus = vi.fn()
  const onOpenTask = vi.fn()
  render(<EvidenceBrowser focus={focus} onFocus={onFocus} onOpenTask={onOpenTask} />)
  return { onFocus, onOpenTask }
}

function rowIds(): string[] {
  return screen
    .getAllByTestId(/^evidence-row-ev-/)
    .map((row) => row.getAttribute('data-testid')!.replace('evidence-row-', ''))
}

describe('EvidenceBrowser', () => {
  it('keeps two documents’ FR-1 apart, each named by its document, newest first', () => {
    browse()
    const watch = screen.getByTestId('evidence-group-spreq-watch-1')
    const tags = screen.getByTestId('evidence-group-spreq-tags-1')
    expect(within(watch).getByText('Folder watching')).toBeTruthy()
    expect(within(tags).getByText('Tags')).toBeTruthy()
    // ev-3 (newest) leads its group, and its group leads the page; the route sent it last.
    expect(rowIds()).toEqual(['ev-3', 'ev-1', 'ev-2'])
  })

  it('counts and filters by state', async () => {
    browse()
    expect(screen.getByTestId('evidence-filter-all').textContent).toContain('3')
    expect(screen.getByTestId('evidence-filter-awaiting').textContent).toContain('1')
    await userEvent.click(screen.getByTestId('evidence-filter-rejected'))
    expect(rowIds()).toEqual(['ev-3'])
  })

  it('counts a piece recorded for an earlier wording apart from accepted evidence (F691)', async () => {
    served = [
      piece({
        id: 'ev-0', summary: 'rename worked before the rewording', produced_at: '2026-10-16T10:00:00Z',
        review_state: 'accepted', for_current_wording: false,
        requirement_id: 'spreq-watch-1',
        requirement: { identifier: 'FR-1', statement: 'A watched folder can be renamed.', document: WATCH },
      }),
      ...EVIDENCE.map((p) => ({ ...p, for_current_wording: true })),
    ]
    try {
      browse()
      expect(screen.getByTestId('evidence-filter-accepted').textContent).toContain('1')
      expect(screen.getByTestId('evidence-filter-earlier').textContent).toContain('1')
      expect(screen.getByTestId('evidence-row-earlier-ev-0').textContent).toContain('earlier wording')
      await userEvent.click(screen.getByTestId('evidence-filter-accepted'))
      expect(rowIds()).toEqual(['ev-1'])
      await userEvent.click(screen.getByTestId('evidence-filter-earlier'))
      expect(rowIds()).toEqual(['ev-0'])
    } finally {
      served = EVIDENCE
    }
  })

  it('a requirement focus narrows to that document’s FR-1 only, and names it', async () => {
    const { onFocus } = browse('spreq-watch-1')
    expect(rowIds()).toEqual(['ev-3', 'ev-1'])
    const chip = screen.getByTestId('evidence-focus')
    expect(chip.textContent).toContain('FR-1 · Folder watching')
    await userEvent.click(chip)
    expect(onFocus).toHaveBeenCalledWith(null)
  })

  it('a task focus narrows to the task and groups by task', () => {
    browse('task-b')
    expect(rowIds()).toEqual(['ev-2'])
    expect(screen.getByTestId('evidence-focus').textContent).toContain('List tags')
    expect(screen.getByTestId('evidence-group-task-b')).toBeTruthy()
  })

  it('searches commands and filters by agent', async () => {
    browse()
    await userEvent.type(screen.getByTestId('evidence-search'), 'npm run')
    expect(rowIds()).toEqual(['ev-2'])
    await userEvent.clear(screen.getByTestId('evidence-search'))
    await userEvent.selectOptions(screen.getByTestId('evidence-agent'), 'Builder')
    expect(rowIds()).toEqual(['ev-3', 'ev-1'])
  })
})

describe('EvidenceLink', () => {
  beforeEach(() => {
    useConfigStore.setState({ selectedProjectId: 'proj-1' })
    window.history.replaceState(null, '', '/')
  })

  it('opens the evidence view focused on what it names', async () => {
    const heard = vi.fn()
    window.addEventListener('popstate', heard)
    render(<EvidenceLink focus="spreq-watch-1" testId="link" />)
    await userEvent.click(screen.getByTestId('link'))
    window.removeEventListener('popstate', heard)
    const params = new URLSearchParams(window.location.search)
    expect(params.get('tab')).toBe('spec')
    expect(params.get('view')).toBe('evidence')
    expect(params.get('focus')).toBe('spreq-watch-1')
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it('renders nothing without a project to open it in', () => {
    useConfigStore.setState({ selectedProjectId: null })
    const { container } = render(<EvidenceLink focus={null} />)
    expect(container.textContent).toBe('')
  })
})
