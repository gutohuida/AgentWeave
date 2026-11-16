import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { UpdateSettings } from '@/components/settings/UpdateSettings'

const status = {
  current: '2.1.0', latest: '2.1.1', available: true, applicable: true, auto: true,
  work: { running: true, description: '1 agent turn is running' }, message: null,
}

function bridge(over: Record<string, unknown> = {}) {
  const api = {
    update_status: vi.fn(async () => status),
    set_auto_update: vi.fn(async () => true),
    apply_update: vi.fn(async (confirmed: boolean) =>
      confirmed
        ? { state: 'applied', detail: '' }
        : { state: 'needs_confirm', detail: '1 agent turn is running' }),
    ...over,
  }
  ;(window as unknown as { pywebview: unknown }).pywebview = { api }
  return api
}

afterEach(() => {
  cleanup()
  delete (window as unknown as { pywebview?: unknown }).pywebview
})

describe('UpdateSettings', () => {
  it('shows nothing without the window bridge', () => {
    render(<UpdateSettings />)
    expect(screen.queryByTestId('auto-update')).toBeNull()
  })

  it('names the work and applies only after confirming; cancel changes nothing', async () => {
    const api = bridge()
    render(<UpdateSettings />)
    expect(await screen.findByText(/Version 2.1.1 is available/)).toBeTruthy()
    fireEvent.click(await screen.findByTestId('update-button'))
    expect(await screen.findByTestId('update-confirm')).toBeTruthy()
    expect(api.apply_update).toHaveBeenCalledWith(false)
    fireEvent.click(screen.getByTestId('update-cancel'))
    expect(api.apply_update).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId('update-button'))
    fireEvent.click(await screen.findByTestId('update-confirm'))
    await waitFor(() => expect(api.apply_update).toHaveBeenLastCalledWith(true))
  })

  it('states a failure and saves the switch', async () => {
    const api = bridge({ apply_update: vi.fn(async () => ({ state: 'failed', detail: 'migration broke' })) })
    render(<UpdateSettings />)
    fireEvent.click(await screen.findByTestId('auto-update'))
    expect(api.set_auto_update).toHaveBeenCalledWith(false)
    fireEvent.click(screen.getByTestId('update-button'))
    expect((await screen.findByTestId('update-failure')).textContent).toContain('migration broke')
  })

  it('offers no button when this install cannot update', async () => {
    bridge({ update_status: vi.fn(async () => ({ ...status, applicable: false })) })
    render(<UpdateSettings />)
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('update-button')).toBeNull()
  })
})
