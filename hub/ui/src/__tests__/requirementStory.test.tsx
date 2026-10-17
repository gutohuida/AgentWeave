import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RequirementStory } from '@/components/spec/RequirementStory'
import type { SpecRequirementDetail } from '@/api/spec'
import { wordDiff } from '@/lib/wordDiff'
import { parseDestination, requirementDestination, serializeDestination } from '@/lib/navigation'

/**
 * A requirement's story (slice requirement-story). `DETAIL.revisions` is in the order
 * `GET /spec/requirements/{identifier}` returns them (oldest first, `created_at` then id), so a
 * renderer that reversed or re-sorted them fails the order test (CLAUDE.md: the route's order).
 */

const DOC = 'spec/changes/watch/spec.json'

function revision(overrides: Partial<NonNullable<SpecRequirementDetail['revisions']>[number]> & { id: string }) {
  return {
    classification: 'reworded' as const,
    source: 'hub',
    actor_kind: 'agent',
    actor: 'Architect',
    run_id: null,
    statement: null,
    digest: 'd',
    previous_digest: null,
    created_at: '2026-10-17T10:00:00Z',
    ...overrides,
  }
}

const DETAIL: SpecRequirementDetail = {
  requirement: {
    id: 'spreq-1', identifier: 'FR-2', key: 'rename', document_id: 'spdoc-1', state: 'active',
    digest: 'd3', anchor: 'fr-2',
    statement: 'A watched folder can be renamed while Terra runs.',
    document: { path: DOC, title: 'Folder watching' },
  },
  revisions: [
    revision({
      id: 'sprev-a', classification: 'created', statement: null, created_at: '2026-10-10T10:00:00Z',
      folded_from: { path: 'spec/changes/watch-folders/spec.json', title: 'Watch folders', at: '2026-10-10T10:00:00Z' },
    }),
    revision({ id: 'sprev-b', statement: 'A watched folder can be renamed.', created_at: '2026-10-12T10:00:00Z' }),
    revision({
      id: 'sprev-c', actor_kind: 'operator', actor: 'operator',
      statement: 'A watched folder can be renamed while Terra runs.', created_at: '2026-10-14T10:00:00Z',
    }),
  ],
  drift: [
    {
      id: 'drift-1', evidence_id: 'ev-9', state: 'resolved', observed: null, resolution: 'still_holds',
      resolved_by: 'operator', resolved_at: '2026-10-15T10:00:00Z', created_at: '2026-10-15T09:00:00Z',
    },
  ],
  tasks: [{ id: 'task-1', title: 'Rename watched folders', status: 'approved', assignee: 'Builder' }],
  evidence: [],
  coverage: null,
}

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return { ...actual, useSpecRequirement: () => ({ data: DETAIL, isLoading: false, isError: false }) }
})

function story() {
  const onOpenDocument = vi.fn()
  const onOpenTask = vi.fn()
  render(<RequirementStory document={DOC} identifier="FR-2" onOpenDocument={onOpenDocument} onOpenTask={onOpenTask} />)
  return { onOpenDocument, onOpenTask }
}

describe('RequirementStory', () => {
  it('shows the current wording, and every revision in the route’s order', () => {
    story()
    expect(screen.getByTestId('requirement-story-statement').textContent).toBe(
      'A watched folder can be renamed while Terra runs.',
    )
    const ids = within(screen.getByTestId('requirement-revisions'))
      .getAllByTestId(/^requirement-revision-sprev-/)
      .map((item) => item.getAttribute('data-testid'))
    expect(ids).toEqual(['requirement-revision-sprev-a', 'requirement-revision-sprev-b', 'requirement-revision-sprev-c'])
  })

  it('says when a wording was not recorded, and shows the next one whole', () => {
    story()
    expect(screen.getByTestId('requirement-revision-unrecorded-sprev-a')).toBeTruthy()
    const second = screen.getByTestId('requirement-revision-sprev-b')
    expect(second.querySelector('ins, del')).toBeNull()
    expect(second.textContent).toContain('was not recorded, so this is shown whole')
  })

  it('shows a rewording as a word diff, and names who made it', () => {
    story()
    const third = screen.getByTestId('requirement-revision-sprev-c')
    expect(third.textContent).toContain('You reworded it')
    expect([...third.querySelectorAll('ins')].map((n) => n.textContent)).toEqual(['renamed while Terra runs.'])
    expect([...third.querySelectorAll('del')].map((n) => n.textContent)).toEqual(['renamed.'])
  })

  it('names the change a folded revision came from, and opens it', async () => {
    const { onOpenDocument } = story()
    const folded = screen.getByTestId('requirement-revision-folded-sprev-a')
    expect(folded.textContent).toContain('folded it in from Watch folders')
    await userEvent.click(within(folded).getByText('Watch folders'))
    expect(onOpenDocument).toHaveBeenCalledWith('spec/changes/watch-folders/spec.json')
  })

  it('lists drift with its resolution, and opens a task and the document', async () => {
    const { onOpenDocument, onOpenTask } = story()
    expect(screen.getByTestId('requirement-story-drift').textContent).toContain('still holds by operator')
    await userEvent.click(screen.getByText('Rename watched folders'))
    expect(onOpenTask).toHaveBeenCalledWith('task-1')
    await userEvent.click(screen.getByTestId('requirement-story-back'))
    expect(onOpenDocument).toHaveBeenCalledWith(DOC)
  })
})

describe('wordDiff', () => {
  it('joins back to both wordings', () => {
    const before = 'hello.py MUST print hello world.'
    const after = "hello.py MUST print 'hello, world' followed by a newline."
    const parts = wordDiff(before, after)
    expect(parts.filter((p) => p.kind !== 'added').map((p) => p.text).join('')).toBe(before)
    expect(parts.filter((p) => p.kind !== 'removed').map((p) => p.text).join('')).toBe(after)
  })
})

describe('requirementDestination', () => {
  it('round-trips through the URL, and an unparseable path lands on the Spec tab', () => {
    const destination = requirementDestination('proj-1', DOC, 'FR-2')
    expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    expect(requirementDestination('proj-1', '../etc', 'FR-2')).toEqual({ kind: 'project', projectId: 'proj-1', tab: 'spec' })
  })
})
