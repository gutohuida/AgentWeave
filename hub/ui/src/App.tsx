import { useEffect, useState, type ComponentType } from 'react'
import { useAgents } from '@/api/agents'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { ActivityLog } from '@/components/activity/ActivityLog'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'
import { JobsPage } from '@/components/jobs/JobsPage'
import { LogsView } from '@/components/logs/LogsView'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { SetupModal } from '@/components/layout/SetupModal'
import {
  Sidebar,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_WIDTH,
  type SidebarPage,
} from '@/components/layout/Sidebar'
import { StatusBar } from '@/components/layout/StatusBar'
import { OverviewPage } from '@/components/overview/OverviewPage'
import { QualityHealthPanel } from '@/components/quality/QualityHealthPanel'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { SpecPage } from '@/components/spec/SpecPage'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { useSSE } from '@/hooks/useSSE'
import {
  agentDestination,
  projectDestination,
  type WorkspaceDestination,
} from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'

export type Page = 'overview' | SidebarPage

const SIDEBAR_WIDTH_KEY = 'aw.sidebarWidth'

type PageWrapper = 'scroll' | 'flex-col'

interface PageMeta {
  Component: ComponentType<{ onNavigate: (destination: string) => void }>
  wrapper: PageWrapper
}

const PAGES: Record<Page, PageMeta> = {
  overview: { Component: OverviewPage, wrapper: 'scroll' },
  tasks: { Component: TasksBoard, wrapper: 'scroll' },
  questions: { Component: QuestionsPanel, wrapper: 'scroll' },
  activity: { Component: ActivityLog, wrapper: 'scroll' },
  quality: { Component: QualityHealthPanel, wrapper: 'scroll' },
  logs: { Component: LogsView, wrapper: 'flex-col' },
  jobs: { Component: JobsPage, wrapper: 'flex-col' },
  instructions: { Component: InstructionsPage, wrapper: 'flex-col' },
  spec: { Component: SpecPage, wrapper: 'flex-col' },
}

const WRAPPER_CLASS: Record<PageWrapper, string> = {
  scroll: 'h-full overflow-auto',
  'flex-col': 'h-full flex flex-col',
}

export default function App() {
  const { isConfigured, theme, mode, bootstrapState, projectId } = useConfigStore()
  const { data: agents = [] } = useAgents()
  const [setupOpen, setSetupOpen] = useState(false)
  const [destination, setDestination] = useState<WorkspaceDestination>(() =>
    projectDestination(projectId || ''),
  )
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    try {
      const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY))
      if (Number.isFinite(stored) && stored >= SIDEBAR_MIN_WIDTH && stored <= SIDEBAR_MAX_WIDTH) {
        return stored
      }
    } catch {
      // Persistence is optional.
    }
    return SIDEBAR_WIDTH
  })

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
    } catch {
      // Persistence is optional.
    }
  }, [sidebarWidth])

  useEffect(() => {
    useConfigStore.getState().bootstrap()
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.mode = mode
  }, [theme, mode])

  useSSE()

  if (bootstrapState === 'pending') {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: 'var(--bg)' }}>
        <div className="text-sm opacity-70">Connecting…</div>
      </div>
    )
  }

  if (bootstrapState === 'unreachable') {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: 'var(--bg)' }}>
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="text-sm" style={{ color: 'var(--text)' }}>Can&apos;t reach the Hub</div>
          <div className="text-xs opacity-70" style={{ maxWidth: 320 }}>
            The dashboard couldn&apos;t connect to the Hub server. Make sure it&apos;s running, then retry.
          </div>
          <button
            type="button"
            onClick={() => useConfigStore.getState().bootstrap()}
            className="mt-1"
            style={{
              height: 32,
              borderRadius: 'var(--radius)',
              padding: '0 16px',
              background: 'var(--blue)',
              color: '#fff',
              border: 'none',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const activePage: Page | null = destination.kind === 'project'
    ? 'overview'
    : destination.kind === 'page'
      ? destination.page as SidebarPage
      : null
  const selectedAgent = destination.kind === 'conversation'
    ? agents.find((agent) => agent.name === destination.agent) ?? null
    : null
  const currentProjectId = destination.kind === 'page'
    ? projectId || ''
    : destination.projectId
  const railResizable = activePage !== 'spec'

  const navigate = (value: string) => {
    if (value.startsWith('agent:')) {
      setDestination(agentDestination(currentProjectId, value.slice('agent:'.length)))
      return
    }
    if (value === 'overview') {
      setDestination(projectDestination(currentProjectId))
      return
    }
    setDestination({ kind: 'page', page: value })
  }

  let content: React.ReactNode
  if (destination.kind === 'conversation') {
    content = selectedAgent ? (
      <AgentOutputPanel
        agent={selectedAgent}
        initialConversationId={destination.conversationId}
        onConversationChange={(conversationId) => setDestination((current) => {
          if (current.kind !== 'conversation' || current.conversationId === conversationId) {
            return current
          }
          return { ...current, conversationId }
        })}
        onAgentConversationChange={(agent, conversationId) =>
          setDestination(agentDestination(destination.projectId, agent, conversationId))
        }
        onBackToProject={() => setDestination(projectDestination(destination.projectId))}
      />
    ) : (
      <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
        Agent unavailable.
      </div>
    )
  } else {
    const page = activePage ?? 'overview'
    const active = PAGES[page]
    const ActivePage = active.Component
    content = (
      <div className={WRAPPER_CLASS[active.wrapper]} data-testid="active-page-wrapper">
        <ActivePage onNavigate={navigate} />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="flex flex-col h-full">
        <StatusBar onOpenSetup={() => setSetupOpen(true)} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            activePage={activePage}
            activeAgent={destination.kind === 'conversation' ? destination.agent : null}
            onNavigate={(page) => setDestination({ kind: 'page', page })}
            onOpenProject={(id) => setDestination(projectDestination(id))}
            onOpenAgent={(id, agent) => setDestination(agentDestination(id, agent))}
            onOpenSetup={() => setSetupOpen(true)}
            compact={activePage === 'spec'}
            width={sidebarWidth}
          />
          {railResizable && (
            <PaneResizer
              width={sidebarWidth}
              onChange={setSidebarWidth}
              defaultWidth={SIDEBAR_WIDTH}
              min={SIDEBAR_MIN_WIDTH}
              max={SIDEBAR_MAX_WIDTH}
            />
          )}
          <main className="flex-1 overflow-hidden" style={{ background: 'var(--bg)' }}>
            {content}
          </main>
        </div>
      </div>
      <SetupModal open={!isConfigured || setupOpen} onClose={() => setSetupOpen(false)} />
    </div>
  )
}
