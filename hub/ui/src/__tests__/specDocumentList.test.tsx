import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import { SpecDocumentList, type SpecListDocument } from '@/components/spec/SpecDocumentList'

/**
 * The Spec tab's document list (ui-finesse), which took over from the rail's spec mode
 * (`SpecRailNav`): every document the corpus holds — archived and missing ones too, as the old
 * tree had them — grouped by kind, the Evidence view with its count, and the host's footer (the
 * defects report). The rail's own assertions moved here.
 */

const DOCS: SpecListDocument[] = [
  { path: 'spec/spec.json', title: 'Specification', kind: 'baseline', phase: '' },
  { path: 'spec/roadmaps/r1/spec.json', title: 'The plan', kind: 'roadmap', phase: 'approved' },
  { path: 'spec/changes/watcher/spec.json', title: 'Watcher', kind: 'change-spec', phase: 'exploring' },
  { path: 'spec/capabilities/sync/spec.json', title: 'Sync', kind: 'capability', phase: 'current' },
  { path: 'spec/changes/archive/2026-09-01-old/spec.json', title: 'Old change', kind: 'change-spec', phase: 'archived', archived: true },
  { path: 'spec/changes/gone/spec.json', title: 'Gone', kind: 'change-spec', phase: '', missing: true },
]

beforeEach(() => localStorage.clear())
afterEach(cleanup)

function renderList(props: Partial<React.ComponentProps<typeof SpecDocumentList>> = {}) {
  const onOpen = vi.fn()
  const onOpenEvidence = vi.fn()
  render(
    <SpecDocumentList
      documents={DOCS}
      active="spec/changes/watcher/spec.json"
      evidenceCount={44}
      onOpen={onOpen}
      onOpenEvidence={onOpenEvidence}
      {...props}
    />,
  )
  return { onOpen, onOpenEvidence }
}

describe('the spec document list', () => {
  it('groups every live document by kind, and marks the open one', () => {
    renderList()
    const nav = screen.getByRole('navigation', { name: 'Spec documents' })
    for (const label of ['Overview', 'Roadmaps', 'Changes', 'Capabilities']) {
      expect(within(nav).getByRole('button', { name: new RegExp(`^${label}`) })).toHaveAttribute('aria-expanded', 'true')
    }
    expect(screen.getByTestId('spec-list-row-spec/changes/watcher/spec.json')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('spec-list-row-spec/changes/watcher/spec.json')).toHaveTextContent('draft')
  })

  it('keeps archived documents findable, folded until asked for', () => {
    renderList()
    const archived = screen.getByRole('button', { name: /^Archived/ })
    expect(archived).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Old change')).toBeNull()
    fireEvent.click(archived)
    expect(screen.getByText('Old change')).toBeInTheDocument()
  })

  it('opens the archived group by itself when the open document is in it', () => {
    renderList({ active: 'spec/changes/archive/2026-09-01-old/spec.json' })
    expect(screen.getByTestId('spec-list-row-spec/changes/archive/2026-09-01-old/spec.json')).toHaveAttribute('aria-current', 'page')
  })

  it('lists a missing document, marked and not openable', () => {
    const { onOpen } = renderList()
    const row = screen.getByTestId('spec-list-row-spec/changes/gone/spec.json')
    expect(row).toBeDisabled()
    expect(row).toHaveTextContent('missing')
    fireEvent.click(row)
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('opens a document, and opens Evidence with its count', () => {
    const { onOpen, onOpenEvidence } = renderList()
    fireEvent.click(screen.getByText('Sync'))
    expect(onOpen).toHaveBeenCalledWith('spec/capabilities/sync/spec.json')
    const evidence = screen.getByTestId('spec-list-evidence')
    expect(evidence).toHaveTextContent('44')
    fireEvent.click(evidence)
    expect(onOpenEvidence).toHaveBeenCalled()
  })

  it('says the evidence count could not be read, rather than showing none', () => {
    renderList({ evidenceCount: 'error', evidenceActive: true })
    const evidence = screen.getByTestId('spec-list-evidence')
    expect(evidence).toHaveTextContent('—')
    expect(evidence).toHaveAttribute('aria-current', 'page')
  })

  it('remembers a folded group', () => {
    renderList()
    fireEvent.click(screen.getByRole('button', { name: /^Capabilities/ }))
    expect(screen.queryByText('Sync')).toBeNull()
    cleanup()
    renderList()
    expect(screen.queryByText('Sync')).toBeNull()
  })

  it('carries the host footer (the defects report)', () => {
    renderList({ footer: <section data-testid="spec-defects">Defects by step</section> })
    expect(within(screen.getByRole('navigation', { name: 'Spec documents' })).getByTestId('spec-defects')).toBeInTheDocument()
  })
})
