import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { UpdateButton } from '@/components/app/UpdateButton'

const status = {
  current: '2.1.0', latest: '2.1.1', available: true, applicable: true, auto: true,
  work: { running: true, description: '1 agent turn is running' }, message: null,
}

function bridge(over: Record<string, unknown> = {}) {
  const api = {
    update_status: vi.fn(async () => status),
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

describe('UpdateButton', () => {
  it('shows nothing without the window bridge', () => {
    render(<UpdateButton />)
    expect(screen.queryByTestId('update-banner')).toBeNull()
  })

  it('is shown while work runs, names it, and applies only on confirm', async () => {
    const api = bridge()
    render(<UpdateButton />)
    fireEvent.click(await screen.findByTestId('update-banner-button'))
    expect(await screen.findByText(/1 agent turn is running/)).toBeTruthy()
    fireEvent.click(screen.getByTestId('update-banner-cancel'))
    expect(api.apply_update).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId('update-banner-button'))
    fireEvent.click(await screen.findByTestId('update-banner-confirm'))
    await waitFor(() => expect(api.apply_update).toHaveBeenLastCalledWith(true))
  })

  it('states the last update failure after a reload', async () => {
    bridge({
      update_status: vi.fn(async () => ({
        ...status, available: false, message: { state: 'failed', detail: 'migration broke' },
      })),
    })
    render(<UpdateButton />)
    expect((await screen.findByTestId('update-banner-failure')).textContent).toContain('migration broke')
  })
})
