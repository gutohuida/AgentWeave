import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { PanelShell, type PanelTabDescriptor } from '@/components/spec/PanelShell'
import { SpecTree } from '@/components/spec/SpecTree'
import type { SpecInventory, SpecNode } from '@/components/spec/specNavigation'
import { usePanelTabsStore, type TabId } from '@/store/panelTabsStore'

/**
 * The S3 `considered` mock's two additions over `restrained` on the side panel: the Loops launcher
 * carrying the count the app already had, and `SpecTree` getting the interaction pass `FileTree`
 * beside it already had.
 */

afterEach(cleanup)

describe('S3 — the Running launcher reports what is running', () => {
  it('badges the launcher card when a count is supplied, and shows nothing at zero', () => {
    usePanelTabsStore.setState({ projects: {} })
    const describeTab = (id: TabId): PanelTabDescriptor => ({ id, label: id, icon: 'article' })
    const tabs: PanelTabDescriptor[] = [
      { id: 'specs', label: 'Specs', icon: 'article' },
      { id: 'running', label: 'Running', icon: 'sync', count: 3 },
    ]
    render(
      <PanelShell
        projectId="proj-badge"
        availableTabs={tabs}
        describeTab={describeTab}
        renderTabContent={() => null}
      />,
    )

    expect(screen.getByTestId('panel-launch-badge-running')).toHaveTextContent('3')
    // A badge is a reason to look; a panel with nothing waiting gets none rather than a "0".
    expect(screen.queryByTestId('panel-launch-badge-specs')).not.toBeInTheDocument()
  })
})

describe('S3 — SpecTree gets the same row treatment FileTree has', () => {
  // `SpecTree` reads `inventory.nodes` and nothing else, so the nodes are stated directly rather
  // than round-tripped through `buildInventory` — that function's own contract is tested next door
  // in `specNavigation.test.ts`.
  function makeNode(path: string, title: string): SpecNode {
    return {
      path,
      title,
      state: 'filed',
      parent: null,
      order: 0,
      archived: false,
      archiveDate: null,
      changeName: null,
      missing: false,
      documentId: null,
    }
  }
  const inventory = {
    nodes: [makeNode('spec/roadmap/one.json', 'One'), makeNode('spec/roadmap/two.json', 'Two')],
  } as SpecInventory

  function renderTree(density: 'dialog' | 'rail' = 'dialog') {
    return render(
      <SpecTree inventory={inventory} currentPath="spec/roadmap/one.json" onSelect={vi.fn()} density={density} />,
    )
  }

  it('renders every row as a .row-item, so hover and press behave as they do next door', () => {
    localStorage.clear()
    renderTree()

    expect(screen.getByTestId('spec-tree-directory-spec/roadmap')).toHaveClass('row-item')
    const document = screen.getByTestId('spec-tree-document-spec/roadmap/one.json')
    expect(document).toHaveClass('row-item')
    expect(document).toHaveClass('panel-tree-row')
    // The open document is marked by weight and colour, not by a resting fill — the fill is
    // reserved for hover and press.
    expect(document).toHaveAttribute('data-active', 'true')
    expect(document.style.background).toBe('')
  })

  it('shows a folded directory as a closed folder, not an open one', () => {
    localStorage.clear()
    renderTree()

    const directory = screen.getByTestId('spec-tree-directory-spec/roadmap')
    expect(directory).toHaveAttribute('aria-expanded', 'true')
    expect(directory.querySelector('.lucide-folder-open')).not.toBeNull()

    fireEvent.click(directory)
    expect(directory).toHaveAttribute('aria-expanded', 'false')
    expect(directory.querySelector('.lucide-folder-open')).toBeNull()
    expect(directory.querySelector('.lucide-folder')).not.toBeNull()
  })
})
