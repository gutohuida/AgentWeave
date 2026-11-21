import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { presentContextUsage } from '@/components/context/contextPresentation'
import { ConversationBar } from '@/components/conversation/ConversationBar'
import { PanelShell } from '@/components/spec/PanelShell'
import { usePanelTabsStore } from '@/store/panelTabsStore'

/**
 * F1201 (spec the-thread-bar-and-composer-survive-a-wide-side-panel). jsdom lays nothing out, so
 * these pin the wiring the acceptance drive measures for real: the bar's compaction steps, where
 * Checkpoint goes at the last one, the title's full name, the context label's compact form and
 * the side panel's own close control. Widths themselves are the drive's
 * (scripts/drive/d1121_f1201_side_panel_overlap.py --assert).
 */

const agent: AgentSummary = { name: 'alice', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }
const TITLE = 'A thread whose title is long enough to need truncating beside the side panel, by some margin'
const conversation = {
  id: 'conv-1',
  title: TITLE,
  context_usage: { status: 'measured', context_tokens: 86551, limit_tokens: 1000000, percent: 8.66 },
} as unknown as AgentConversation

function renderBar(props: Partial<React.ComponentProps<typeof ConversationBar>> = {}) {
  return render(
    <ConversationBar
      agent={agent}
      conversation={conversation}
      title={TITLE}
      onRename={() => undefined}
      isRunning={false}
      elapsedSeconds={null}
      onCheckpoint={() => undefined}
      diagnosticsHidden={false}
      onToggleDiagnostics={() => undefined}
      onFoldAll={() => undefined}
      {...props}
    />,
  )
}

/** Makes every bar overflow, whatever its step: the narrowest column. */
function overflowEverywhere() {
  vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.dataset.testid === 'conversation-header' ? 500 : 0
  })
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.dataset.testid === 'conversation-header' ? 380 : 0
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()
})

describe('the thread bar answers to its own width', () => {
  it('stays at the full bar while it fits, with Checkpoint in the bar and not in ⋯', async () => {
    renderBar()
    const bar = screen.getByTestId('conversation-header')
    expect(bar).toHaveAttribute('data-compact', '0')
    expect(screen.getByTestId('conversation-handoff')).toHaveAccessibleName('Checkpoint')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'More thread actions' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByTestId('conversation-handoff-item')).toBeNull()
  })

  it('at its last step moves Checkpoint into ⋯ as an item, still reachable while unavailable', async () => {
    overflowEverywhere()
    const onCheckpoint = vi.fn()
    renderBar({ isRunning: true, onStop: () => undefined, checkpointDisabledReason: 'a turn is running', onCheckpoint })
    expect(screen.getByTestId('conversation-header')).toHaveAttribute('data-compact', '3')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'More thread actions' }))
    const menu = await screen.findByRole('menu')
    const item = within(menu).getByTestId('conversation-handoff-item')
    expect(item).toHaveTextContent('Checkpoint — a turn is running')
    // aria-disabled, not disabled: arrow keys still land on it, so its reason can be read.
    expect(item).toHaveAttribute('aria-disabled', 'true')
    expect(item).not.toHaveAttribute('data-disabled')
    await user.click(item)
    expect(onCheckpoint).not.toHaveBeenCalled()
  })

  it('a Checkpoint item that can be used runs it', async () => {
    overflowEverywhere()
    const onCheckpoint = vi.fn()
    renderBar({ onCheckpoint })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'More thread actions' }))
    await user.click(within(await screen.findByRole('menu')).getByTestId('conversation-handoff-item'))
    expect(onCheckpoint).toHaveBeenCalledTimes(1)
  })

  it('names the title in full, whatever of it shows', () => {
    renderBar()
    const title = screen.getByTestId('conversation-header').querySelector('.aw-convbar-title')!
    expect(title).toHaveAccessibleName(TITLE)
    expect(title.getAttribute('title')).toContain(TITLE)
  })

  it('renders the context reading in both forms, the compact one a whole percentage', () => {
    renderBar()
    const ctx = screen.getByTestId('context-usage')
    expect(ctx.querySelector('.context-usage-label')).toHaveTextContent('86,551 / 1,000,000 · 8.66%')
    expect(ctx.querySelector('.context-usage-short')).toHaveTextContent('9%')
  })
})

describe('the compact context label', () => {
  it('rounds, says <1% rather than 0% for a started window, and falls back to the token count', () => {
    const base = { status: 'measured', context_tokens: 5, limit_tokens: 1000 }
    expect(presentContextUsage({ ...base, percent: 0.5 })?.shortLabel).toBe('<1%')
    expect(presentContextUsage({ ...base, context_tokens: 250, percent: 25 })?.shortLabel).toBe('25%')
    expect(presentContextUsage({ status: 'measured', context_tokens: 1200 })?.shortLabel).not.toBe('')
  })
})

describe('the side panel closes itself', () => {
  function renderShell(onClose?: () => void) {
    usePanelTabsStore.setState({ projects: {} })
    return render(
      <PanelShell
        projectId="proj-close"
        availableTabs={[{ id: 'specs', label: 'Specs', icon: 'article' }]}
        describeTab={(id) => ({ id, label: String(id), icon: 'article' })}
        renderTabContent={() => null}
        onClose={onClose}
      />,
    )
  }

  it('offers "Close side panel" with no tab open, by click and by keyboard', async () => {
    const onClose = vi.fn()
    renderShell(onClose)
    const close = screen.getByRole('button', { name: 'Close side panel' })
    const user = userEvent.setup()
    await user.click(close)
    close.focus()
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it('shows no close control when the caller cannot close it', () => {
    renderShell()
    expect(screen.queryByRole('button', { name: 'Close side panel' })).toBeNull()
  })
})
