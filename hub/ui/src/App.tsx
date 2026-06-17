import { useState, useEffect, type ComponentType } from 'react'
import { useConfigStore } from '@/store/configStore'
import { SetupModal } from '@/components/layout/SetupModal'
import { StatusBar } from '@/components/layout/StatusBar'
import { Sidebar } from '@/components/layout/Sidebar'
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
import { useSSE } from '@/hooks/useSSE'

export type Page = 'overview' | 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents' | 'jobs' | 'quality' | 'instructions'

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
}

const WRAPPER_CLASS: Record<PageWrapper, string> = {
  'scroll':   'h-full overflow-auto',
  'flex-col': 'h-full flex flex-col',
}

export default function App() {
  const { isConfigured, theme, mode, bootstrapState } = useConfigStore()
  const [setupOpen, setSetupOpen] = useState(false)
  const [page, setPage] = useState<Page>('overview')

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

  const active = PAGES[page]
  const ActivePage = active.Component

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="flex flex-col h-full">
        <StatusBar onOpenSetup={() => setSetupOpen(true)} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            activePage={page}
            onNavigate={setPage}
            onOpenSetup={() => setSetupOpen(true)}
          />
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
