import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ClosePrompt } from '@/components/app/ClosePrompt'
import { CloseSettings } from '@/components/settings/AppSettingsScreen'
import { describeWork } from '@/lib/closePrompt'

// Change `agentweave-is-its-own-app-on-windows`, D4/D5: the launcher cancels a close that finds
// work running and calls `window.awClosePrompt(work)` with the Hub's `GET /api/v1/work/running`
// answer; the page answers through the window's bridge.

const ONE_TURN = {
  running: true,
  turns: 1,
  check_runs: 0,
  landings: 0,
  builds: 0,
  turn_agents: [{ agent: 'Builder', project: 'AgentWeave' }],
  build_list: [],
}

function withBridge(api: Record<string, unknown>) {
  ;(window as unknown as { pywebview?: unknown }).pywebview = { api }
}

afterEach(() => {
  delete (window as unknown as { pywebview?: unknown }).pywebview
})

describe('describeWork', () => {
  it('names what is running, as the launcher does', () => {
    expect(describeWork(ONE_TURN)).toBe('1 agent turn is running')
    expect(
      describeWork({ ...ONE_TURN, turns: 2, check_runs: 1, builds: 1, build_list: [{ id: 'b', title: 'Close means stop', project: 'p' }] }),
    ).toBe('2 agent turns, 1 check run and the build Close means stop are running')
    expect(describeWork({ running: true, builds: 1, build_list: [{ id: 'b', title: 'Close means stop', project: 'p' }] })).toBe(
      'The build Close means stop is running',
    )
    expect(describeWork({ unknown: true })).toBe('AgentWeave could not say what is running')
  })
})

describe('ClosePrompt', () => {
  it('shows nothing until the launcher asks', () => {
    render(<ClosePrompt />)
    expect(screen.queryByText('AgentWeave is still working')).toBeNull()
    expect(typeof window.awClosePrompt).toBe('function')
  })

  it.each([
    ['Cancel', 'cancel'],
    ['Keep running in the background', 'keep'],
    ['Stop it all and close', 'stop'],
  ])('names one agent turn, and %s answers %s through the bridge', async (label, choice) => {
    const close_choice = vi.fn(() => Promise.resolve(true))
    withBridge({ close_choice })
    render(<ClosePrompt />)
    act(() => window.awClosePrompt!(ONE_TURN))
    expect(await screen.findByText('1 agent turn is running. Closing the window stops AgentWeave.')).toBeTruthy()
    expect(screen.getByTestId('close-prompt-turns').textContent).toContain('Builder in AgentWeave')
    fireEvent.click(screen.getByRole('button', { name: label }))
    expect(close_choice).toHaveBeenCalledWith(choice)
    expect(close_choice).toHaveBeenCalledTimes(1)
  })

  it('dismissing the dialog is a cancel, so the launcher is never left waiting', async () => {
    const close_choice = vi.fn(() => Promise.resolve(true))
    withBridge({ close_choice })
    render(<ClosePrompt />)
    act(() => window.awClosePrompt!(ONE_TURN))
    await screen.findByText('AgentWeave is still working')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(close_choice).toHaveBeenCalledWith('cancel')
    await waitFor(() => expect(screen.queryByText('AgentWeave is still working')).toBeNull())
  })
})

describe('CloseSettings', () => {
  it('is hidden outside the app window', () => {
    const { container } = render(<CloseSettings />)
    expect(container.textContent).toBe('')
  })

  it('reads the launcher-kept setting and writes it back', async () => {
    const set_close_keeps_running = vi.fn(() => Promise.resolve(true))
    withBridge({ close_keeps_running: () => Promise.resolve(false), set_close_keeps_running })
    render(<CloseSettings />)
    const toggle = await screen.findByTestId('close-keeps-running')
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(toggle)
    expect(set_close_keeps_running).toHaveBeenCalledWith(true)
    await waitFor(() => expect(toggle.getAttribute('aria-checked')).toBe('true'))
  })
})
