import { useEffect, useState } from 'react'
import { useConfigStore } from '@/store/configStore'
import { SetupModal } from '@/components/layout/SetupModal'
import { StatusBar } from '@/components/layout/StatusBar'
import { Sidebar } from '@/components/layout/Sidebar'
import { MessagesFeed } from '@/components/messages/MessagesFeed'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { ActivityLog } from '@/components/activity/ActivityLog'
import { useSSE } from '@/hooks/useSSE'

type Page = 'messages' | 'tasks' | 'questions' | 'activity'

export default function App() {
  const { isConfigured } = useConfigStore()
  const [forceOpen, setForceOpen] = useState(false)
  const [page, setPage] = useState<Page>('messages')

  // Show modal when truly not configured, or when explicitly opened
  const showSetup = !isConfigured || forceOpen

  // Start SSE connection once configured
  useSSE()

  // Listen for 401 auth errors
  useEffect(() => {
    const handler = () => setForceOpen(true)
    window.addEventListener('auth-error', handler)
    return () => window.removeEventListener('auth-error', handler)
  }, [])

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <StatusBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activePage={page}
          onNavigate={setPage}
          onOpenSetup={() => setForceOpen(true)}
        />
        <main className="flex-1 overflow-auto">
          {page === 'messages' && <MessagesFeed />}
          {page === 'tasks' && <TasksBoard />}
          {page === 'questions' && <QuestionsPanel />}
          {page === 'activity' && <ActivityLog />}
        </main>
      </div>
      <SetupModal open={showSetup} onClose={() => setForceOpen(false)} />
    </div>
  )
}
