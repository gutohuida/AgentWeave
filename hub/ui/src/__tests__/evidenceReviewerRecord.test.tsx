import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { EvidenceProof } from '@/components/evidence/EvidenceProof'
import type { EvidencePiece } from '@/api/spec'

/* FR-3 of `evidence-review-sends-work-back-only-for-what-is-wrong-with-it`: a piece a reviewer
 * accepted with its own reproduction shows the reviewer's record beside the author's, attributed.
 * The fixture is the list route's payload (`spec._evidence_view`'s keys). Only the app's
 * evidence view renders this; the record itself is asserted at the routes, in
 * `hub/tests/test_a_reviewer_verifies_evidence.py`. */

function piece(reviewer: EvidencePiece['reviewer_record']): EvidencePiece {
  return {
    id: 'ev-1',
    summary: 'ran the tests',
    kind: 'test_result',
    locator: '',
    actor_kind: 'agent',
    actor: 'builder',
    run_id: 'run-b',
    task_id: 'task-1',
    review_state: 'accepted',
    latest_review: { decision: 'accepted', reason: 're-ran it', actor_kind: 'agent', actor: 'checker' },
    produced_at: '2026-11-10T09:00:00+00:00',
    footprint: { kind: 'git', branch: 'agentweave/task/task-1', commit_sha: 'bbbbbbbbbbbb', outside_workspace_writes: [] },
    command: 'pytest -k feature',
    output: '1 passed',
    covers: null,
    requirement: { identifier: 'FR-1', statement: 'It works' },
    reviewer_record: reviewer,
  }
}

function show(value: EvidencePiece) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EvidenceProof piece={value} open={false} />
    </QueryClientProvider>,
  )
}

afterEach(cleanup)

describe('EvidenceProof reviewer record', () => {
  it("shows the reviewer's reproduction beside the author's proof", () => {
    show(
      piece({
        actor_kind: 'agent',
        actor: 'checker',
        run_id: 'run-r',
        command: 'pytest -k feature --tip',
        output: '2 passed',
        commit: 'bbbbbbbbbbbb',
        anchored_from_commit: 'aaaaaaaaaaaa',
        summary: 'passes on the merged tip',
        covers: null,
      }),
    )
    const record = screen.getByTestId('evidence-reviewer-record-ev-1')
    expect(within(record).getByText('Reproduced by checker')).toBeTruthy()
    expect(within(record).getByText('pytest -k feature --tip')).toBeTruthy()
    expect(within(record).getByText('2 passed')).toBeTruthy()
    expect(within(record).getByText('passes on the merged tip')).toBeTruthy()
    expect(record.textContent).toContain("re-anchored from the author's aaaaaaaa")
    // The author's own proof is still there, as recorded.
    expect(screen.getByText('pytest -k feature')).toBeTruthy()
    expect(screen.getByText('1 passed')).toBeTruthy()
  })

  it('shows nothing extra where no reviewer reproduced it', () => {
    show(piece(null))
    expect(screen.queryByTestId('evidence-reviewer-record-ev-1')).toBeNull()
  })
})
