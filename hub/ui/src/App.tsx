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
import { useSSE } from '@/hooks/useSSE'

type Page = 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents'

export default function App() {
  const { isConfigured, theme } = useConfigStore()
  const [setupOpen, setSetupOpen] = useState(false)
  const [page, setPage] = useState<Page>('messages')

  // Sync theme to <html data-theme="..."> whenever it changes
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  // Start SSE connection once configured
  useSSE()

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Animated orb background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
        <div className="orb orb-4" />
      </div>

      {/* Content layer */}
      <div className="relative z-10 flex flex-col h-full">
        <StatusBar />
        <div className="flex flex-1 overflow-hidden gap-2 p-2 pt-1.5">
          <Sidebar
            activePage={page}
            onNavigate={setPage}
            onOpenSetup={() => setSetupOpen(true)}
          />
          <main className="flex-1 overflow-hidden rounded-xl glass">
            {page === 'messages'  && <div className="h-full overflow-auto"><MessagesFeed /></div>}
            {page === 'tasks'     && <div className="h-full overflow-auto"><TasksBoard /></div>}
            {page === 'questions' && <div className="h-full overflow-auto"><QuestionsPanel /></div>}
            {page === 'activity'  && <div className="h-full overflow-auto"><ActivityLog /></div>}
            {page === 'logs'      && <div className="h-full flex flex-col"><LogsView /></div>}
            {page === 'agents'    && <div className="h-full flex flex-col"><AgentsPage /></div>}
          </main>
        </div>
      </div>

      <SetupModal open={!isConfigured || setupOpen} onClose={() => setSetupOpen(false)} />
    </div>
  )
}
