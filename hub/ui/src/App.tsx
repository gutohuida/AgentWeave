import { useState, useEffect } from 'react'
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
import { MissionControlPage } from '@/components/agents/MissionControlPage'
import { JobsPage } from '@/components/jobs/JobsPage'
import { useSSE } from '@/hooks/useSSE'

type Page = 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents' | 'mission-control' | 'jobs'

export default function App() {
  const { isConfigured, theme, mode } = useConfigStore()
  const [setupOpen, setSetupOpen] = useState(false)
  const [page, setPage] = useState<Page>('messages')

  // Sync theme + mode to <html data-theme="..." data-mode="...">
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.mode  = mode
  }, [theme, mode])

  useSSE()

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Content layer — flat Material surface, no orbs */}
      <div className="flex flex-col h-full">
        <StatusBar onOpenSetup={() => setSetupOpen(true)} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            activePage={page}
            onNavigate={setPage}
            onOpenSetup={() => setSetupOpen(true)}
          />
          <main className="flex-1 overflow-hidden m3-surface border-l-0" style={{ borderRadius: 0 }}>
            {page === 'messages'  && <div className="h-full overflow-auto"><MessagesFeed /></div>}
            {page === 'tasks'     && <div className="h-full overflow-auto"><TasksBoard /></div>}
            {page === 'questions' && <div className="h-full overflow-auto"><QuestionsPanel /></div>}
            {page === 'activity'  && <div className="h-full overflow-auto"><ActivityLog /></div>}
            {page === 'logs'      && <div className="h-full flex flex-col"><LogsView /></div>}
            {page === 'agents'    && <div className="h-full flex flex-col"><AgentsPage /></div>}
            {page === 'mission-control' && <div className="h-full flex flex-col"><MissionControlPage /></div>}
            {page === 'jobs'       && <div className="h-full flex flex-col"><JobsPage /></div>}
          </main>
        </div>
      </div>

      <SetupModal open={!isConfigured || setupOpen} onClose={() => setSetupOpen(false)} />
    </div>
  )
}
