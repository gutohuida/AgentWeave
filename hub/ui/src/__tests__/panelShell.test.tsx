import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PanelShell, type PanelTabDescriptor } from '@/components/spec/PanelShell'
import { usePanelTabsStore, type TabId } from '@/store/panelTabsStore'

const PROJECT = 'proj-shell'

const DESCRIPTORS: Record<string, PanelTabDescriptor> = {
  specs: { id: 'specs', label: 'Specs', icon: 'article' },
  files: { id: 'files', label: 'Files', icon: 'folder_open' },
  'spec:doc-1': { id: 'spec:doc-1', label: 'Onboarding flow', icon: 'article' },
}

function describeTab(id: TabId): PanelTabDescriptor {
  return DESCRIPTORS[id] ?? { id, label: id, icon: 'article' }
}

function renderShell(availableTabs: PanelTabDescriptor[] = [DESCRIPTORS.specs, DESCRIPTORS.files]) {
  return render(
    <PanelShell
      projectId={PROJECT}
      availableTabs={availableTabs}
      describeTab={describeTab}
      renderTabContent={(tab) => <div data-testid="content-body">content for {tab.id}</div>}
    />,
  )
}

describe('PanelShell', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
  })

  it('renders an explicit empty state rather than an empty box when nothing is open', () => {
    renderShell()

    expect(screen.getByTestId('panel-empty-state')).toBeInTheDocument()
    expect(screen.queryByTestId('panel-tab-content')).not.toBeInTheDocument()
    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })

  it('renders exactly one tab’s content at a time', () => {
    usePanelTabsStore.getState().openTab(PROJECT, 'specs')
    usePanelTabsStore.getState().openTab(PROJECT, 'files')
    renderShell()

    const bodies = screen.getAllByTestId('content-body')
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).toHaveTextContent('content for files')
    expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Specs' })).toHaveAttribute('aria-selected', 'false')
  })

  it('opens a tab from the plus menu', async () => {
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByTestId('panel-tab-add'))
    await user.click(await screen.findByRole('menuitem', { name: 'Specs' }))

    expect(await screen.findByRole('tab', { name: 'Specs' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('content-body')).toHaveTextContent('content for specs')
  })

  it('omits an already-open tab from the plus menu', async () => {
    usePanelTabsStore.getState().openTab(PROJECT, 'specs')
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByTestId('panel-tab-add'))
    const items = (await screen.findAllByRole('menuitem')).map((item) => item.textContent)
    expect(items).toEqual(['Files'])
  })

  it('hides the plus affordance once every available tab is open', () => {
    usePanelTabsStore.getState().openTab(PROJECT, 'specs')
    usePanelTabsStore.getState().openTab(PROJECT, 'files')
    renderShell()

    expect(screen.queryByTestId('panel-tab-add')).not.toBeInTheDocument()
  })

  it('closes a tab from its close control without activating it first', async () => {
    usePanelTabsStore.getState().openTab(PROJECT, 'specs')
    usePanelTabsStore.getState().openTab(PROJECT, 'files')
    usePanelTabsStore.getState().activateTab(PROJECT, 'specs')
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByTestId('panel-tab-close-files'))

    expect(screen.queryByRole('tab', { name: 'Files' })).not.toBeInTheDocument()
    // Closing a background tab must not steal activation from the one on screen.
    expect(screen.getByRole('tab', { name: 'Specs' })).toHaveAttribute('aria-selected', 'true')
  })

  it('closing every tab returns to the empty state', async () => {
    usePanelTabsStore.getState().openTab(PROJECT, 'specs')
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByTestId('panel-tab-close-specs'))

    expect(await screen.findByTestId('panel-empty-state')).toBeInTheDocument()
  })

  describe('task 6.1 — the newly active tab scrolls into view', () => {
    it('scrolls the tab into view when it becomes active by click', async () => {
      usePanelTabsStore.getState().openTab(PROJECT, 'specs')
      usePanelTabsStore.getState().openTab(PROJECT, 'files')
      usePanelTabsStore.getState().activateTab(PROJECT, 'specs')
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
      const user = userEvent.setup()
      renderShell()

      await user.click(screen.getByRole('tab', { name: 'Files' }))

      expect(scrollSpy).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' })
      // Called on the tab that is now active, not some other element in the strip.
      const lastInstance = scrollSpy.mock.instances[scrollSpy.mock.instances.length - 1]
      expect(lastInstance).toBe(screen.getByRole('tab', { name: 'Files' }))
      scrollSpy.mockRestore()
    })

    it('scrolls the tab into view when activation moves via arrow keys, not just on open', async () => {
      usePanelTabsStore.getState().openTab(PROJECT, 'specs')
      usePanelTabsStore.getState().openTab(PROJECT, 'files')
      usePanelTabsStore.getState().activateTab(PROJECT, 'specs')
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
      const user = userEvent.setup()
      renderShell()
      scrollSpy.mockClear()
      screen.getByRole('tab', { name: 'Specs' }).focus()

      await user.keyboard('{ArrowRight}')

      await waitFor(() => expect(scrollSpy).toHaveBeenCalled())
      const lastInstance = scrollSpy.mock.instances[scrollSpy.mock.instances.length - 1]
      expect(lastInstance).toBe(screen.getByRole('tab', { name: 'Files' }))
      scrollSpy.mockRestore()
    })
  })

  describe('keyboard — ARIA tablist, sequential focus, arrow keys, Enter/Space', () => {
    beforeEach(() => {
      usePanelTabsStore.getState().openTab(PROJECT, 'specs')
      usePanelTabsStore.getState().openTab(PROJECT, 'files')
      usePanelTabsStore.getState().openTab(PROJECT, 'spec:doc-1')
      usePanelTabsStore.getState().activateTab(PROJECT, 'specs')
    })

    it('puts only the active tab in the sequential Tab order', () => {
      renderShell([])

      expect(screen.getByRole('tab', { name: 'Specs' })).toHaveAttribute('tabIndex', '0')
      expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('tabIndex', '-1')
      expect(screen.getByRole('tab', { name: 'Onboarding flow' })).toHaveAttribute('tabIndex', '-1')
    })

    it('ArrowRight moves focus and activation to the next tab, wrapping at the end', async () => {
      const user = userEvent.setup()
      renderShell([])
      screen.getByRole('tab', { name: 'Specs' }).focus()

      await user.keyboard('{ArrowRight}')
      await waitFor(() => expect(screen.getByRole('tab', { name: 'Files' })).toHaveFocus())
      expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true')

      await user.keyboard('{ArrowRight}')
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Onboarding flow' })).toHaveFocus(),
      )

      await user.keyboard('{ArrowRight}')
      await waitFor(() => expect(screen.getByRole('tab', { name: 'Specs' })).toHaveFocus())
    })

    it('ArrowLeft wraps to the last tab from the first', async () => {
      const user = userEvent.setup()
      renderShell([])
      screen.getByRole('tab', { name: 'Specs' }).focus()

      await user.keyboard('{ArrowLeft}')
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Onboarding flow' })).toHaveFocus(),
      )
      expect(screen.getByRole('tab', { name: 'Onboarding flow' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })

    it('Home and End jump to the first and last tab', async () => {
      const user = userEvent.setup()
      renderShell([])
      screen.getByRole('tab', { name: 'Specs' }).focus()

      await user.keyboard('{End}')
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Onboarding flow' })).toHaveFocus(),
      )

      await user.keyboard('{Home}')
      await waitFor(() => expect(screen.getByRole('tab', { name: 'Specs' })).toHaveFocus())
    })

    it('Enter/Space activate a focused tab via native button behaviour', async () => {
      const user = userEvent.setup()
      renderShell([])
      screen.getByRole('tab', { name: 'Files' }).focus()

      await user.keyboard('{Enter}')
      expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true')
    })

    it('the close control is keyboard-reachable and keyboard-operable', async () => {
      const user = userEvent.setup()
      renderShell([])

      const closeButton = screen.getByTestId('panel-tab-close-files')
      closeButton.focus()
      await user.keyboard('{Enter}')

      expect(screen.queryByRole('tab', { name: 'Files' })).not.toBeInTheDocument()
    })

    it('the plus menu trigger is itself keyboard-reachable', async () => {
      const user = userEvent.setup()
      renderShell([DESCRIPTORS.specs, DESCRIPTORS.files])
      usePanelTabsStore.getState().closeTab(PROJECT, 'files')

      const trigger = await screen.findByTestId('panel-tab-add')
      trigger.focus()
      await user.keyboard('{Enter}')

      expect(await screen.findByRole('menuitem', { name: 'Files' })).toBeInTheDocument()
    })
  })
})
