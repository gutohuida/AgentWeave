import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

// Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`, FR-7 and FR-11: the page says
// where the instructions come from, offers AGENTS.md only when the Hub says the folder has one, and
// switching it on is the source route, not a save.
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, getJson: vi.fn(), putJson: vi.fn() }
})

import { getJson, putJson } from '@/api/client'
import { InstructionsSection } from '@/components/settings/sections/InstructionsSection'

const PROJECT = 'proj-alpha'
const BASE = `/api/v1/projects/${PROJECT}/project/instructions`

let state: Record<string, unknown>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <InstructionsSection />
    </QueryClientProvider>
  )
}

describe('AGENTS.md as the instructions, where chosen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConfigStore.setState({ isConfigured: true, selectedProjectId: PROJECT })
    vi.mocked(getJson).mockImplementation(async () => state)
  })

  it('offers AGENTS.md when the folder has one, and switching it on calls the source route', async () => {
    state = { content: 'Hub rules', max_chars: 40000, source: 'hub', agents_md_offered: true, main_branch: 'main' }
    vi.mocked(putJson).mockImplementation(async (path: string) => {
      expect(path).toBe(`${BASE}/source`)
      state = { content: '# Ours\n\nHub rules\n', max_chars: 40000, source: 'agents_md', agents_md_offered: false, main_branch: 'main' }
      return { ...state, committed: true, notice: null }
    })
    renderPage()

    expect(await screen.findByDisplayValue('Hub rules')).toBeInTheDocument()
    expect(screen.getByTestId('instructions-source-offer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: "Use AGENTS.md as this project's instructions" }))

    expect(vi.mocked(putJson)).toHaveBeenCalledWith(`${BASE}/source`, { agents_md: true })
    expect(await screen.findByTestId('instructions-source-agents-md')).toBeInTheDocument()
    await waitFor(() => expect((screen.getByLabelText('Project instructions') as HTMLTextAreaElement).value).toBe('# Ours\n\nHub rules\n'))
  })

  it('offers nothing when the folder has no AGENTS.md', async () => {
    state = { content: 'Hub rules', max_chars: 40000, source: 'hub', agents_md_offered: false }
    renderPage()
    expect(await screen.findByDisplayValue('Hub rules')).toBeInTheDocument()
    expect(screen.queryByTestId('instructions-source-offer')).toBeNull()
    expect(screen.queryByTestId('instructions-source-agents-md')).toBeNull()
  })

  it('names the refusal when a save to AGENTS.md is refused', async () => {
    state = { content: '# Ours\n', max_chars: 40000, source: 'agents_md', agents_md_offered: false, main_branch: 'main' }
    const { ApiError } = await import('@/api/client')
    vi.mocked(putJson).mockRejectedValue(
      new ApiError(409, JSON.stringify({ detail: { code: 'agents_md_uncommitted', message: 'AGENTS.md has uncommitted changes in the project checkout.' } }))
    )
    renderPage()
    const box = (await screen.findByLabelText('Project instructions')) as HTMLTextAreaElement
    await userEvent.type(box, 'more')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('AGENTS.md has uncommitted changes in the project checkout.')
    expect(vi.mocked(putJson)).toHaveBeenCalledWith(BASE, { content: '# Ours\nmore' })
  })
})
