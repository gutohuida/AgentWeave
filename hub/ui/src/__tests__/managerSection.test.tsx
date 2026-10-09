import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManagerPanel } from '@/components/environment/ManagerPanel'
import { useConfigStore } from '@/store/configStore'

/** `the-hubs-background-jobs-are-configured-on-a-manager-page`, task manager-section. The routes are
 *  stubbed at `fetch`, so the hooks, their 404 handling and the PATCH bodies are the real ones. */

const RUNNERS = [
  { id: 'runner-haiku', name: 'Haiku 4.5', cli: 'claude', model: null, model_unrecognised: false },
  { id: 'runner-titles', name: 'Titler', cli: 'claude', model: 'claude-opus-5', model_unrecognised: false },
]
const CATALOG = {
  providers: [{
    provider: 'claude',
    label: 'Claude',
    controls: [],
    models: [
      { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', aliases: ['haiku'], context_window: 200_000, default: false },
      { id: 'claude-opus-5', label: 'Opus 5', aliases: ['opus'], context_window: 1_000_000, default: true },
    ],
  }],
}
const JOB = {
  key: 'conversation-titles',
  title: 'Conversation titles',
  description: 'Names a conversation after its first exchange.',
  trigger: 'turn_completed',
  enabled: true,
  runner_id: 'runner-titles',
  model: 'claude-haiku-4-5-20251001',
}
// Newest first, the order `GET /manager/activity` returns.
const FIRINGS = [
  {
    id: 'evt-2', at: '2026-10-09T15:02:00+00:00', job: 'conversation-titles', trigger: 'turn_completed',
    subject: { conversation_id: 'conv-2' }, runner_id: 'runner-titles', cli: 'claude',
    model: 'claude-haiku-4-5-20251001', outcome: 'empty', detail: null, duration_ms: 900, usage: null,
  },
  {
    id: 'evt-1', at: '2026-10-09T15:01:00+00:00', job: 'conversation-titles', trigger: 'turn_completed',
    subject: { conversation_id: 'conv-1' }, runner_id: 'runner-titles', cli: 'claude',
    model: 'claude-haiku-4-5-20251001', outcome: 'written', detail: 'Bakery naming ideas',
    duration_ms: 4200, usage: null,
  },
]

type Route = (url: string, init?: RequestInit) => { status: number; body: unknown } | undefined
let manager: Route
const patches: Array<{ url: string; body: unknown }> = []

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  patches.length = 0
  useConfigStore.setState({
    apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a',
  })
  manager = () => undefined
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') patches.push({ url, body: JSON.parse(String(init.body)) })
    const routed = manager(url, init)
    if (routed) return respond(routed.status, routed.body)
    if (url.endsWith('/runners')) return respond(200, RUNNERS)
    if (url.endsWith('/model-catalog')) return respond(200, CATALOG)
    return respond(404, { detail: 'Not Found' })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Environment > Manager', () => {
  it('says this Hub has no manager yet when the routes answer 404', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ManagerPanel />, { wrapper })
    expect(await screen.findByText(/This Hub has no manager yet/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })

  it('lists each job with its switch, runner and model, and the firings newest first', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: FIRINGS } }
      return undefined
    }
    render(<ManagerPanel />, { wrapper })

    const job = await screen.findByTestId('manager-job-conversation-titles')
    expect(within(job).getByText('Conversation titles')).toBeInTheDocument()
    expect(screen.getByTestId('manager-job-conversation-titles-enabled')).toBeChecked()
    await waitFor(() =>
      expect(screen.getByTestId('manager-job-conversation-titles-runner')).toHaveValue('runner-titles'),
    )
    const runner = screen.getByTestId('manager-job-conversation-titles-runner')
    // Each runner named by its own model (F268), as every runner select is.
    expect(within(runner).getByRole('option', { name: 'Titler — Opus 5 (claude)' })).toBeInTheDocument()
    expect(screen.getByTestId('manager-job-conversation-titles-model')).toHaveValue('claude-haiku-4-5-20251001')

    const first = await screen.findByTestId('manager-firing-0')
    expect(within(first).getByText(/empty/i)).toBeInTheDocument()
    const second = screen.getByTestId('manager-firing-1')
    expect(within(second).getByText('Bakery naming ideas')).toBeInTheDocument()
    expect(within(second).getByText(/written/i)).toBeInTheDocument()
  })

  it('sends only what changed when a control is used', async () => {
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') {
        return { status: 200, body: { ...JOB, enabled: false } }
      }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      return undefined
    }
    render(<ManagerPanel />, { wrapper })

    fireEvent.click(await screen.findByTestId('manager-job-conversation-titles-enabled'))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].url).toBe('http://hub/api/v1/projects/proj-a/manager/jobs/conversation-titles')
    expect(patches[0].body).toEqual({ enabled: false })

    await waitFor(() =>
      expect(screen.getByTestId('manager-job-conversation-titles-model')).not.toBeDisabled(),
    )
    fireEvent.change(screen.getByTestId('manager-job-conversation-titles-model'), {
      target: { value: '' },
    })
    await waitFor(() => expect(patches).toHaveLength(2))
    expect(patches[1].body).toEqual({ model: null })
  })

  it('withholds the job controls when the runners cannot be read, rather than misstate the runner', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      if (url.endsWith('/runners')) return { status: 500, body: { detail: 'boom' } }
      return undefined
    }
    render(<ManagerPanel />, { wrapper })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByTestId('manager-job-conversation-titles-runner')).toBeNull()
  })

  it('says when nothing has fired yet', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [{ ...JOB, enabled: false }] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      return undefined
    }
    render(<ManagerPanel />, { wrapper })
    expect(await screen.findByText(/No job has spawned a model yet/)).toBeInTheDocument()
  })
})
