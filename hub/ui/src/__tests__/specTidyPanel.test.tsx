import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpecTidyPanel } from '@/components/spec/SpecTidyPanel'

/**
 * `an-agent-the-operator-trusts-can-tidy-the-specs`, FR-6, FR-10, FR-13: the unreviewed acts (the
 * route answers a bare list), a requirement changed to match the code marked apart, and the batch
 * archive of the selected superseded documents.
 */
const markReviewed = vi.fn()
const archiveBatch = vi.fn()

const acts = [
  { id: 'a1', act: 'fold', path: 'spec/changes/x/spec.json', agent: 'Tidy', run_id: 'run-1', at: 't', reason: 'built', code_wins: null, reviewed: false },
  {
    id: 'a2', act: 'edit_capability', path: 'spec/capabilities/c/spec.json', agent: 'Tidy', run_id: 'run-1', at: 't', reason: 'code differs', reviewed: false,
    code_wins: { requirement: 'FR-2', before: 'old text', after: 'new text', cited: 'src/thing.py' },
  },
]
const docs = ['a', 'b', 'c'].map((n) => ({
  id: n, path: `spec/changes/${n}/spec.json`, title: `Doc ${n}`, superseded: { at: 't', by: 'Tidy', reason: 'dead', successor: null },
}))

vi.mock('@/api/specTidy', () => ({
  useTidyActs: () => ({ data: acts, error: null }),
  useSupersededDocuments: () => ({ data: { documents: docs }, error: null }),
  useMarkTidyReviewed: () => ({ mutate: markReviewed, isPending: false }),
  useArchiveBatch: () => ({ mutate: archiveBatch, isPending: false }),
}))

describe('SpecTidyPanel', () => {
  it('lists the acts, marks the code-wins one apart, and marks all reviewed', async () => {
    render(<SpecTidyPanel onSelect={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Tidy acts to review/ }))
    const rows = screen.getAllByTestId('spec-tidy-act')
    expect(rows.map((r) => r.getAttribute('data-code-wins'))).toEqual(['false', 'true'])
    expect(screen.getByTestId('spec-tidy-code-wins')).toHaveTextContent('src/thing.py')
    await userEvent.click(screen.getByTestId('spec-tidy-review-all'))
    expect(markReviewed).toHaveBeenCalledWith({ all: true }, expect.anything())
  })

  it('archives exactly the selected superseded documents', async () => {
    render(<SpecTidyPanel onSelect={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Superseded documents/ }))
    await userEvent.click(screen.getByLabelText('Select Doc a'))
    await userEvent.click(screen.getByLabelText('Select Doc c'))
    await userEvent.click(screen.getByTestId('spec-superseded-archive'))
    expect(archiveBatch).toHaveBeenCalledWith({ paths: ['spec/changes/a/spec.json', 'spec/changes/c/spec.json'] }, expect.anything())
  })
})
