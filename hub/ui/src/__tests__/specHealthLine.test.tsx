import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { CoverageEntry } from '@/api/spec'
import { SpecHealthLine } from '@/components/spec/SpecHealthLine'
import { openMenu } from './testUtils/menus'

/**
 * The document header's one line of facts (ui-finesse), in place of the coverage, drift, vault,
 * tasks-link and manifest strips: a fact the Hub could not answer is left out rather than shown
 * as fine, a fact that needs the operator takes its colour (the verified-but-not-merged result the
 * coverage strip surfaced at rest included), and each fact opens its full detail on request.
 */

function entry(identifier: string, state: CoverageEntry['state'], integration: CoverageEntry['integration'] = 'not_applicable'): CoverageEntry {
  return {
    identifier,
    requirement_id: `req-${identifier}`,
    document_id: 'doc',
    state,
    integration,
    evidence_count: 0,
    accepted_count: 0,
    linked_task_ids: [],
  }
}

function renderLine(props: Partial<React.ComponentProps<typeof SpecHealthLine>> = {}) {
  const handlers = {
    onScanDrift: vi.fn(),
    onCheckVault: vi.fn(),
    onOpenTasks: vi.fn(),
    onOpenRequirement: vi.fn(),
    onShowDetail: vi.fn(),
  }
  render(
    <SpecHealthLine
      coverage={[entry('FR-1', 'verified', 'integrated'), entry('FR-2', 'verified', 'not_integrated'), entry('FR-3', 'rejected')]}
      driftCount={0}
      vaultWarnings={2}
      indexIssues={0}
      tasks={[{ id: 't1', title: 'Build it', status: 'approved' }]}
      history={[]}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

afterEach(cleanup)

describe('the health line', () => {
  it('states coverage, and says a verified requirement is not merged', () => {
    renderLine()
    const fact = screen.getByTestId('spec-health-requirements')
    expect(fact).toHaveTextContent('2/3 verified')
    expect(fact).toHaveTextContent('1 rejected')
    expect(fact).toHaveTextContent('1 not merged')
    expect(fact).toHaveAttribute('data-tone', 'warn')
  })

  it('leaves out what the Hub could not answer', () => {
    renderLine({ coverage: [], driftCount: null, vaultWarnings: null, tasks: [] })
    expect(screen.queryByTestId('spec-health-requirements')).toBeNull()
    expect(screen.queryByTestId('spec-health-drift')).toBeNull()
    expect(screen.queryByTestId('spec-health-vault')).toBeNull()
    expect(screen.queryByTestId('spec-health-tasks')).toBeNull()
  })

  it('colours a vault conflict, and keeps a fine fact quiet', () => {
    renderLine()
    expect(screen.getByTestId('spec-health-vault')).toHaveTextContent('2 vault conflicts')
    expect(screen.getByTestId('spec-health-vault')).toHaveAttribute('data-tone', 'warn')
    expect(screen.getByTestId('spec-health-drift')).toHaveTextContent('No drift')
    expect(screen.getByTestId('spec-health-drift')).not.toHaveAttribute('data-tone')
  })

  it('opens a fact, and asks for its details', () => {
    const { onShowDetail, onOpenRequirement } = renderLine()
    openMenu(screen.getByTestId('spec-health-requirements'))
    expect(screen.getByText(/Verified, not in the main line: FR-2/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /FR-3/ }))
    expect(onOpenRequirement).toHaveBeenCalledWith('FR-3')

    openMenu(screen.getByTestId('spec-health-vault'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Show details' }))
    expect(onShowDetail).toHaveBeenCalledWith('vault')
  })

  it('says Hide details for the fact whose details are open', () => {
    renderLine({ activeDetail: 'drift' })
    expect(screen.getByTestId('spec-health-drift')).toHaveAttribute('data-active', 'true')
    openMenu(screen.getByTestId('spec-health-drift'))
    expect(screen.getByRole('menuitem', { name: 'Hide details' })).toBeInTheDocument()
  })

  it('shows the document tasks on the board', () => {
    const { onOpenTasks } = renderLine()
    openMenu(screen.getByTestId('spec-health-tasks'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Show these on the board' }))
    expect(onOpenTasks).toHaveBeenCalled()
  })
})
