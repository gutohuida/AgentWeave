import { useState, useEffect, type ComponentType } from 'react'
import { useConfigStore } from '@/store/configStore'
import { SetupModal } from '@/components/layout/SetupModal'
import { StatusBar } from '@/components/layout/StatusBar'
import {
  Sidebar,
  SIDEBAR_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_MAX_WIDTH,
} from '@/components/layout/Sidebar'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { MessagesFeed } from '@/components/messages/MessagesFeed'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { ActivityLog } from '@/components/activity/ActivityLog'
import { LogsView } from '@/components/logs/LogsView'
import { AgentsPage } from '@/components/agents/AgentsPage'
import { JobsPage } from '@/components/jobs/JobsPage'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'
import { QualityHealthPanel } from '@/components/quality/QualityHealthPanel'
import { OverviewPage } from '@/components/overview/OverviewPage'
import { SpecPage } from '@/components/spec/SpecPage'
import { useSSE } from '@/hooks/useSSE'

export type Page = 'overview' | 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents' | 'jobs' | 'quality' | 'instructions' | 'spec'

const SIDEBAR_WIDTH_KEY = 'aw.sidebarWidth'

type PageWrapper = 'scroll' | 'flex-col'

interface PageMeta {
  Component: ComponentType<{ onNavigate?: (page: string) => void }>
  wrapper: PageWrapper
}

const PAGES: Record<Page, PageMeta> = {
  overview:     { Component: OverviewPage as ComponentType<{ onNavigate?: (page: string) => void }>,     wrapper: 'scroll' },
  messages:     { Component: MessagesFeed as ComponentType<{ onNavigate?: (page: string) => void }>,     wrapper: 'scroll' },
  tasks:        { Component: TasksBoard as ComponentType<{ onNavigate?: (page: string) => void }>,       wrapper: 'scroll' },
  questions:    { Component: QuestionsPanel as ComponentType<{ onNavigate?: (page: string) => void }>,   wrapper: 'scroll' },
  activity:     { Component: ActivityLog as ComponentType<{ onNavigate?: (page: string) => void }>,     wrapper: 'scroll' },
  quality:      { Component: QualityHealthPanel as ComponentType<{ onNavigate?: (page: string) => void }>, wrapper: 'scroll' },
  logs:         { Component: LogsView as ComponentType<{ onNavigate?: (page: string) => void }>,         wrapper: 'flex-col' },
  agents:       { Component: AgentsPage as ComponentType<{ onNavigate?: (page: string) => void }>,       wrapper: 'flex-col' },
  jobs:         { Component: JobsPage as ComponentType<{ onNavigate?: (page: string) => void }>,         wrapper: 'flex-col' },
  instructions: { Component: InstructionsPage as ComponentType<{ onNavigate?: (page: string) => void }>,  wrapper: 'flex-col' },
  spec:         { Component: SpecPage as ComponentType<{ onNavigate?: (page: string) => void }>,         wrapper: 'flex-col' },
}

const WRAPPER_CLASS: Record<PageWrapper, string> = {
  'scroll':   'h-full overflow-auto',
  'flex-col': 'h-full flex flex-col',
}

export default function App() {
  const { isConfigured, theme, mode, bootstrapState } = useConfigStore()
  const [setupOpen, setSetupOpen] = useState(false)
  const [page, setPage] = useState<Page>('overview')

  // The rail width is the operator's choice and persists across sessions.
  // Read lazily so the first paint is already at the chosen width — restoring
  // it in an effect would make the rail visibly jump on every load.
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    try {
      const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY))
      if (Number.isFinite(stored) && stored >= SIDEBAR_MIN_WIDTH && stored <= SIDEBAR_MAX_WIDTH) {
        return stored
      }
    } catch {
      // Storage unavailable (private mode, disabled). Fall through to default.
    }
    return SIDEBAR_WIDTH
  })

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
    } catch {
      // Persistence is a convenience; never let it break the layout.
    }
  }, [sidebarWidth])

  useEffect(() => {
    useConfigStore.getState().bootstrap()
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.mode  = mode
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
          <div className="text-sm" style={{ color: 'var(--text)' }}>
            Can&apos;t reach the Hub
          </div>
          <div className="text-xs opacity-70" style={{ maxWidth: 320 }}>
            The dashboard couldn&apos;t connect to the Hub server. Make sure it&apos;s running,
            then retry.
          </div>
          <button
            type="button"
            onClick={() => useConfigStore.getState().bootstrap()}
            className="mt-1"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
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

  const active = PAGES[page]
  const ActivePage = active.Component
  // The rail is icon-only on the Spec page, where there is nothing to resize.
  const railResizable = page !== 'spec'

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="flex flex-col h-full">
        <StatusBar onOpenSetup={() => setSetupOpen(true)} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            activePage={page}
            onNavigate={setPage}
            onOpenSetup={() => setSetupOpen(true)}
            // The Spec workspace needs the horizontal room for its own
            // navigation pane, so the Hub rail collapses to icons there.
            compact={page === 'spec'}
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
            <div className={WRAPPER_CLASS[active.wrapper]} data-testid="active-page-wrapper">
              <ActivePage onNavigate={(p) => setPage(p as Page)} />
            </div>
          </main>
        </div>
      </div>

      <SetupModal open={!isConfigured || setupOpen} onClose={() => setSetupOpen(false)} />
    </div>
  )
}
