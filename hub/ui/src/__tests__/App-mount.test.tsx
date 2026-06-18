import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

// Stub useSSE so it doesn't try to connect. The module is mocked globally for
// the test file — we just need to confirm the App's tree wiring is right.
vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

// Stub every page component with a marker div that includes the page id in its
// testid. This lets us assert which page is mounted without depending on the
// real components' data fetching.
vi.mock('@/components/overview/OverviewPage', () => ({
  OverviewPage: ({ onNavigate }: { onNavigate?: (p: string) => void }) => (
    <div data-testid="page-overview">
      <button onClick={() => onNavigate?.('agents')}>go to agents</button>
    </div>
  ),
}))
vi.mock('@/components/messages/MessagesFeed', () => ({
  MessagesFeed: () => <div data-testid="page-messages" />,
}))
vi.mock('@/components/tasks/TasksBoard', () => ({
  TasksBoard: () => <div data-testid="page-tasks" />,
}))
vi.mock('@/components/questions/QuestionsPanel', () => ({
  QuestionsPanel: () => <div data-testid="page-questions" />,
}))
vi.mock('@/components/activity/ActivityLog', () => ({
  ActivityLog: () => <div data-testid="page-activity" />,
}))
vi.mock('@/components/quality/QualityHealthPanel', () => ({
  QualityHealthPanel: () => <div data-testid="page-quality" />,
}))
vi.mock('@/components/logs/LogsView', () => ({
  LogsView: () => <div data-testid="page-logs" />,
}))
vi.mock('@/components/agents/AgentsPage', () => ({
  AgentsPage: () => <div data-testid="page-agents" />,
}))
vi.mock('@/components/jobs/JobsPage', () => ({
  JobsPage: () => <div data-testid="page-jobs" />,
}))
vi.mock('@/components/instructions/InstructionsPage', () => ({
  InstructionsPage: () => <div data-testid="page-instructions" />,
}))

// Stub the layout chrome too so the test focuses on routing.
vi.mock('@/components/layout/StatusBar', () => ({
  StatusBar: () => <div data-testid="status-bar" />,
}))
vi.mock('@/components/layout/SetupModal', () => ({
  SetupModal: () => null,
}))

import App from '@/App'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

describe('Q15 — App.tsx: only the active page is mounted (data-driven routing)', () => {
  beforeEach(() => {
    cleanup()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
      theme: 'cosmic',
      mode: 'light',
    })
  })

  it('renders the default page (overview) on initial mount', () => {
    render(withQueryClient(<App />))
    expect(screen.getByTestId('page-overview')).toBeInTheDocument()
  })

  it('does NOT mount any of the other pages on initial mount', () => {
    render(withQueryClient(<App />))
    for (const id of [
      'page-messages',
      'page-tasks',
      'page-questions',
      'page-activity',
      'page-quality',
      'page-logs',
      'page-agents',
      'page-jobs',
      'page-instructions',
    ]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })

  it('unmounts the previous page when the active page changes (via onNavigate)', () => {
    render(withQueryClient(<App />))
    expect(screen.getByTestId('page-overview')).toBeInTheDocument()

    // Click the stub OverviewPage's "go to agents" button — this exercises
    // the onNavigate callback App wires into every page.
    fireEvent.click(screen.getByText('go to agents'))

    // OverviewPage is gone; AgentsPage is mounted.
    expect(screen.queryByTestId('page-overview')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-agents')).toBeInTheDocument()
  })

  it('navigating twice mounts the third page and unmounts the second', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByText('go to agents'))
    expect(screen.getByTestId('page-agents')).toBeInTheDocument()

    // The Sidebar's nav button click should swap to messages.
    fireEvent.click(screen.getByTestId('nav-messages'))
    expect(screen.queryByTestId('page-agents')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-messages')).toBeInTheDocument()
  })

  it('uses the scroll wrapper class for scroll pages and flex-col for flex pages', () => {
    render(withQueryClient(<App />))
    // overview -> scroll wrapper
    const overviewWrapper = screen.getByTestId('page-overview').parentElement
    expect(overviewWrapper?.className).toContain('overflow-auto')
    expect(overviewWrapper?.className).not.toContain('flex flex-col')

    // agents -> flex-col wrapper
    fireEvent.click(screen.getByTestId('nav-agents'))
    const agentsWrapper = screen.getByTestId('page-agents').parentElement
    expect(agentsWrapper?.className).toContain('flex flex-col')
    expect(agentsWrapper?.className).not.toContain('overflow-auto')

    // messages -> scroll wrapper
    fireEvent.click(screen.getByTestId('nav-messages'))
    const messagesWrapper = screen.getByTestId('page-messages').parentElement
    expect(messagesWrapper?.className).toContain('overflow-auto')
  })
})
