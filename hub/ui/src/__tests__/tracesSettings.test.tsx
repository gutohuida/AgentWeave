/**
 * Project settings → Traces (`settings-in-the-app-s-style-where-you-expect-them`, FR-7 and
 * ac-traces), driven through `fetch`: each change is one PUT with no Save, a stored header value
 * is never on the page, and Download and Clear ask for the chosen span of time.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { TracesSection } from '@/components/settings/sections/TracesSection'
import { useConfigStore } from '@/store/configStore'

const fetchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const settings = {
  otlp_endpoint: 'http://collector.test/v1/traces',
  otlp_header_names: ['Authorization'],
  export_enabled: false,
  enabled_at: null,
  last_export_at: null,
  last_error: null,
  exported_spans: 0,
  span_count: 3,
  trace_count: 2,
  oldest_trace_at: null,
  record_reads: false,
  spans_by_operation: {},
  dropped_spans: 0,
  retention_days: 14,
  retention_days_default: 14,
  retention_days_chosen: false,
}

const puts = () =>
  fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === 'PUT')
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)))

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }))
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub.test', isConfigured: true, selectedProjectId: 'proj-a' })
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.includes('/traces/settings')) {
      if (init?.method === 'PUT') return { ok: true, status: 200, json: async () => ({ ...settings, ...JSON.parse(String(init.body)) }) }
      return { ok: true, status: 200, json: async () => settings }
    }
    if (url.includes('/traces/export')) return { ok: true, status: 200, blob: async () => new Blob(['{}']) }
    return { ok: true, status: 200, json: async () => ({ deleted_spans: 3, deleted_traces: 2 }) }
  })
})
afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('Traces settings', () => {
  it('has no Save button and no native checkbox, date input or select, and links to Activity → Traces', async () => {
    const onOpenTraces = vi.fn()
    render(<TracesSection onOpenTraces={onOpenTraces} />, { wrapper })
    fireEvent.click(await screen.findByTestId('open-traces-view'))
    expect(onOpenTraces).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /^save/i })).toBeNull()
    expect(document.querySelector('input[type=checkbox], input[type=date], select')).toBeNull()
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => /\/traces\?/.test(url))).toBe(false)
  })

  it('stores the retention when the field is left, and offers the default back once chosen', async () => {
    render(<TracesSection />, { wrapper })
    const input = await screen.findByLabelText(/Keep traces for/)
    fireEvent.change(input, { target: { value: '30' } })
    fireEvent.blur(input)
    await waitFor(() => expect(puts()).toEqual([{ retention_days: 30 }]))
    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.blur(input)
    expect(puts()).toHaveLength(1)
  })

  it('stores the collector switch on change', async () => {
    render(<TracesSection />, { wrapper })
    fireEvent.click(await screen.findByRole('switch', { name: 'Send traces to a collector' }))
    await waitFor(() => expect(puts()).toEqual([{ export_enabled: true }]))
  })

  it('replaces the headers through the dialog and never shows a stored value', async () => {
    render(<TracesSection />, { wrapper })
    fireEvent.click(await screen.findByRole('button', { name: 'Replace…' }))
    expect(screen.getAllByText(/Authorization/).length).toBeGreaterThan(0)
    fireEvent.change(await screen.findByLabelText('Headers'), { target: { value: 'X-Key=s3cret-value' } })
    fireEvent.click(screen.getByRole('button', { name: 'Replace headers' }))
    await waitFor(() => expect(puts()).toEqual([{ otlp_headers: { 'X-Key': 's3cret-value' } }]))
    expect(document.body.textContent).not.toContain('s3cret-value')
  })

  it('downloads the traces since seven days ago when 7 days is chosen', async () => {
    render(<TracesSection />, { wrapper })
    fireEvent.click(await screen.findByRole('radio', { name: '7 days' }))
    const before = Date.now()
    fireEvent.click(screen.getByRole('button', { name: /Download/ }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/traces/export'))).toBe(true))
    const url = new URL(String(fetchMock.mock.calls.find(([u]) => String(u).includes('/traces/export'))![0]))
    const since = Date.parse(url.searchParams.get('since')!)
    expect(Math.abs(before - 7 * 24 * 3600 * 1000 - since)).toBeLessThan(60_000)
    expect(url.searchParams.get('until')).toBeNull()
  })

  it('clears the chosen span only after a confirm', async () => {
    render(<TracesSection />, { wrapper })
    fireEvent.click(await screen.findByRole('radio', { name: '30 days' }))
    fireEvent.click(screen.getByRole('button', { name: /Clear traces…/ }))
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(false)
    fireEvent.click(screen.getByTestId('delete-confirm'))
    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')
      expect(del).toBeTruthy()
      expect(String(del![0])).toContain('since=')
    })
  })
})
