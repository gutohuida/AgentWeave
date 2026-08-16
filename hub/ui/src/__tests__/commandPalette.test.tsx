import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CommandPalette } from '@/components/palette/CommandPalette'
import type { AgentConversation } from '@/api/agentChat'
import type { SpecDocumentRecord } from '@/api/spec'
import type { Task } from '@/api/tasks'

/**
 * D3 — command palette (`Cmd+K`/`Ctrl+K`). `CommandPalette` reads its four action lists as props
 * rather than fetching them itself (`App.tsx` supplies data other screens already loaded), so
 * these tests supply fixtures directly and mock only the navigation callbacks — same pattern as
 * `2026-08-16-spec-surface-legibility`'s F4 chip-click tests.
 */

const conversationFixture: AgentConversation = {
  id: 'conv-old',
  agent: 'claude',
  provider_session_id: 'provider-secret-session',
  lifecycle: 'open',
  title: 'A conversation',
  title_set_by_operator: false,
  origin: 'operator',
  attention: 'idle',
  created_at: '2026-08-02T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
}

const documentFixture: SpecDocumentRecord = {
  id: 'spdoc-1',
  path: 'spec/example.md',
  title: 'Example Document',
  kind: 'baseline',
  phase: 'approved',
  rigor: 'sketch',
  content_digest: null,
  explore_closed: false,
  updated_at: '2026-08-16T00:00:00Z',
}

const taskFixture: Task = {
  id: 'task-1',
  project_id: 'proj-test',
  title: 'Ship the thing',
  status: 'in_progress',
  priority: 'medium',
  created_at: '2026-08-10T10:00:00Z',
  updated: '2026-08-10T10:00:00Z',
  divergence_policy: 'surface',
  has_open_divergence: false,
}

function renderPalette(overrides: Partial<Parameters<typeof CommandPalette>[0]> = {}) {
  const callbacks = {
    onOpenConversation: vi.fn(),
    onOpenAgent: vi.fn(),
    onOpenDocument: vi.fn(),
    onOpenTask: vi.fn(),
  }
  render(
    <CommandPalette
      agents={[{ name: 'claude' }]}
      conversations={[conversationFixture]}
      documents={[documentFixture]}
      tasks={[taskFixture]}
      {...callbacks}
      {...overrides}
    />,
  )
  return callbacks
}

const PLACEHOLDER = /search conversations, agents, documents, tasks/i

afterEach(cleanup)

describe('command palette — open and close', () => {
  it('is closed until Ctrl+K, then opens and closes on Escape', async () => {
    renderPalette()
    expect(screen.queryByPlaceholderText(PLACEHOLDER)).not.toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    await waitFor(() => expect(screen.getByPlaceholderText(PLACEHOLDER)).toBeInTheDocument())

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByPlaceholderText(PLACEHOLDER)).not.toBeInTheDocument())
  })

  it('also opens on Cmd+K (metaKey)', async () => {
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    await waitFor(() => expect(screen.getByPlaceholderText(PLACEHOLDER)).toBeInTheDocument())
  })

  it('does not open when a text input has focus and a literal "k" is typed without the modifier', async () => {
    renderPalette()
    render(<input aria-label="scratch" />)
    const scratchInput = screen.getByLabelText('scratch')
    await userEvent.click(scratchInput)
    await userEvent.type(scratchInput, 'k')
    expect(screen.queryByPlaceholderText(PLACEHOLDER)).not.toBeInTheDocument()
  })
})

describe('command palette — the four action kinds', () => {
  it('opens a conversation on selection', async () => {
    const callbacks = renderPalette()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    await screen.findByText('claude — A conversation')
    await userEvent.click(screen.getByText('claude — A conversation'))
    expect(callbacks.onOpenConversation).toHaveBeenCalledWith('claude', 'conv-old')
    await waitFor(() => expect(screen.queryByPlaceholderText(PLACEHOLDER)).not.toBeInTheDocument())
  })

  it('opens an agent on selection', async () => {
    const callbacks = renderPalette()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    await screen.findByText('claude')
    await userEvent.click(screen.getByText('claude'))
    expect(callbacks.onOpenAgent).toHaveBeenCalledWith('claude')
  })

  it('opens a spec document on selection', async () => {
    const callbacks = renderPalette()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    await screen.findByText('Example Document')
    await userEvent.click(screen.getByText('Example Document'))
    expect(callbacks.onOpenDocument).toHaveBeenCalledWith('spec/example.md')
  })

  it('opens a task on selection', async () => {
    const callbacks = renderPalette()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    await screen.findByText('Ship the thing')
    await userEvent.click(screen.getByText('Ship the thing'))
    expect(callbacks.onOpenTask).toHaveBeenCalledWith('task-1')
  })
})
