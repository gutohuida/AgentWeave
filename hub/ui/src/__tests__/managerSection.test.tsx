import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManagerSection } from '@/components/settings/sections/ManagerSection'
import { chooseMenuOption, menuSelect, openMenuSelect } from './support/menuSelect'
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
  needs_runner: false,
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

describe('Project settings → Manager', () => {
  it('says this Hub has no manager yet when the routes answer 404', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText(/This Hub has no manager yet/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })

  it('lists each job with its switch, runner and model, and the firings newest first', async () => {
    const user = userEvent.setup()
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: FIRINGS } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    await screen.findByTestId('manager-job-conversation-titles')
    expect(screen.getByRole('heading', { name: 'Conversation titles' })).toBeInTheDocument()
    expect(screen.getByTestId('manager-job-conversation-titles-enabled')).toHaveAttribute('aria-checked', 'true')
    await waitFor(() => expect(menuSelect('Conversation titles runner')).toHaveTextContent('Titler'))
    // Each runner named by its own model (F268), as every runner menu is.
    const options = await openMenuSelect(user, 'Conversation titles runner')
    expect(options.find((o) => o.textContent?.startsWith('Titler'))).toHaveTextContent('Opus 5 · claude')
    await user.keyboard('{Escape}')
    expect(menuSelect('Conversation titles model')).toHaveTextContent('Haiku 4.5')

    const first = await screen.findByTestId('manager-firing-0')
    expect(within(first).getByText('Nothing to do')).toBeInTheDocument()
    const second = screen.getByTestId('manager-firing-1')
    expect(within(second).getByText('Written')).toBeInTheDocument()
  })

  it('names a firing’s conversation by its title when the Hub knows it', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: FIRINGS } }
      if (url.includes('/conversations')) {
        return { status: 200, body: { conversations: [{ id: 'conv-1', agent: 'a', title: 'Bakery naming ideas', lifecycle: 'open', updated_at: '2026-10-09T15:01:00+00:00' }] } }
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByTestId('manager-firing-1-subject')).toHaveTextContent('Bakery naming ideas')
    expect(screen.getByTestId('manager-firing-0-subject')).toHaveTextContent('conversation conv-2')
  })

  it('badges an answered report and opens what the model answered (F641, F581)', async () => {
    const answered = {
      ...FIRINGS[1], id: 'evt-3', job: 'vault-reports', trigger: 'report_filed', subject: { report: 'r-1' },
      outcome: 'answered', detail: 'answered: the entry stands',
      answer: '{"outcome": "answered", "answer": "The source says 437 euros."}',
    }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [answered] } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    const row = await screen.findByTestId('manager-firing-0')
    expect(within(row).getByText('Answered')).toBeInTheDocument()
    // Closed, since it runs long; opened by the row.
    expect(within(row).queryByText(/The source says 437 euros/)).toBeNull()
    fireEvent.click(within(row).getByRole('row', { expanded: false }))
    expect(within(row).getByRole('row', { expanded: true })).toBeInTheDocument()
    expect(within(row).getByText(/The source says 437 euros/)).toBeInTheDocument()
    expect(within(row).getByText('answered: the entry stands')).toBeInTheDocument()
  })

  it('says what each firing worked on, a vault source by its name (F719)', async () => {
    const distilled = (id: string, source: string) => ({
      ...FIRINGS[1], id, job: 'vault-distillation', trigger: 'source_uploaded',
      subject: { source }, outcome: 'written', detail: '1 fact stored, 0 dropped',
    })
    const firings = [
      distilled('evt-5', 'src-aaa'),
      distilled('evt-4', 'src-bbb'),
      { ...FIRINGS[1], id: 'evt-3', job: 'spec-vault-check', subject: { document: 'spec/changes/x' } },
      { ...FIRINGS[1], id: 'evt-2', job: 'vault-reports', subject: { report: 'rpt-1', entry: 'src-aaa' } },
    ]
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings } }
      if (url.endsWith('/vault/map')) {
        return {
          status: 200,
          body: { entries: [{ id: 'src-aaa', name: 'On-call handbook' }, { id: 'src-bbb', name: 'Refunds' }] },
        }
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText('source "On-call handbook" (src-aaa)')).toBeInTheDocument()
    expect(screen.getByTestId('manager-firing-1-subject')).toHaveTextContent('source "Refunds" (src-bbb)')
    expect(screen.getByTestId('manager-firing-2-subject')).toHaveTextContent('document spec/changes/x')
    expect(screen.getByTestId('manager-firing-3-subject')).toHaveTextContent(
      'report rpt-1 on "On-call handbook" (src-aaa)',
    )
  })

  it('words the empty runner choice by what the job does with none (F590)', async () => {
    const user = userEvent.setup()
    const vault = {
      ...JOB, key: 'vault-distillation', title: 'Vault distillation', needs_runner: true,
      runner_id: null, model: null,
    }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, vault] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    await screen.findByTestId('manager-job-conversation-titles')
    const titles = (await openMenuSelect(user, 'Conversation titles runner')).map((o) => o.textContent)
    expect(titles[0]).toMatch(/^The agent’s own runner/)
    await user.keyboard('{Escape}')
    const distilChoices = (await openMenuSelect(user, 'Vault distillation runner')).map((o) => o.textContent)
    expect(distilChoices[0]).toMatch(/^No runner/)
    expect(distilChoices.some((t) => /agent’s own runner/.test(t ?? ''))).toBe(false)
    await user.keyboard('{Escape}')
    const distil = screen.getByTestId('manager-job-vault-distillation')
    expect(within(distil).getByText(/does nothing until a runner is chosen/i)).toBeInTheDocument()
    expect(within(distil).getByText(/On, but it has no runner, so it will not run/)).toBeInTheDocument()
  })

  it('sends only what changed when a control is used', async () => {
    const user = userEvent.setup()
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') {
        return { status: 200, body: { ...JOB, enabled: false } }
      }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    fireEvent.click(await screen.findByTestId('manager-job-conversation-titles-enabled'))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].url).toBe('http://hub/api/v1/projects/proj-a/manager/jobs/conversation-titles')
    expect(patches[0].body).toEqual({ enabled: false })

    await waitFor(() => expect(menuSelect('Conversation titles model')).not.toBeDisabled())
    await chooseMenuOption(user, 'Conversation titles model', /The runner’s model/)
    await waitFor(() => expect(patches).toHaveLength(2))
    expect(patches[1].body).toEqual({ model: null })
  })

  it('clears a model chosen for another CLI when the runner changes', async () => {
    const user = userEvent.setup()
    const runners = [...RUNNERS, { id: 'runner-codex', name: 'Codex', cli: 'codex', model: null, model_unrecognised: false }]
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') return { status: 200, body: JOB }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      if (url.endsWith('/runners')) return { status: 200, body: runners }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    await waitFor(() => expect(menuSelect('Conversation titles runner')).toHaveTextContent('Titler'))
    await chooseMenuOption(user, 'Conversation titles runner', /^Codex/)
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].body).toEqual({ runner_id: 'runner-codex', model: null })
  })

  it('withholds the job controls when the runners cannot be read, rather than misstate the runner', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      if (url.endsWith('/runners')) return { status: 500, body: { detail: 'boom' } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Conversation titles runner' })).toBeNull()
  })

  it('says when nothing has fired yet', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [{ ...JOB, enabled: false }] } }
      if (url.includes('/manager/activity')) return { status: 200, body: { firings: [] } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText(/No job has spawned a model yet/)).toBeInTheDocument()
  })
})
