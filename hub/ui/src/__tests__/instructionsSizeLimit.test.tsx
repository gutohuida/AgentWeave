import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, getJson: vi.fn(), putJson: vi.fn() }
})

import { getJson, putJson } from '@/api/client'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'

// F686: instructions ride every agent turn, and 300,000 characters were accepted with nothing on
// screen. The page now shows the size against the Hub's limit and will not send a save over it.
describe('project instructions show their size against the limit (F686)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getJson).mockResolvedValue({ content: 'short rules', max_chars: 20 })
    vi.mocked(putJson).mockImplementation(async (_path: string, body?: unknown) => body)
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-alpha',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  function renderPage() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <InstructionsPage />
      </QueryClientProvider>,
    )
  }

  it('states the size and that it is sent with every turn', async () => {
    renderPage()
    const size = await screen.findByTestId('instructions-size')
    expect(size).toHaveTextContent('11 of 20 characters')
    expect(size).toHaveTextContent(/every agent turn/)
  })

  it('refuses to send instructions over the limit, saying why', async () => {
    renderPage()
    const box = await screen.findByRole('textbox', { name: 'Project instructions' })
    fireEvent.change(box, { target: { value: 'x'.repeat(21) } })

    expect(screen.getByTestId('instructions-size')).toHaveAttribute('role', 'alert')
    expect(screen.getByTestId('instructions-size')).toHaveTextContent(/too long to save/i)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(putJson).not.toHaveBeenCalled()
  })
})
