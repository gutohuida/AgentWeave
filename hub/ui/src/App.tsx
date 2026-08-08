import { useEffect, useState } from 'react'
import { AccountingPanel } from '@/components/accounting/AccountingPanel'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'
import { ActivityLog } from '@/components/activity/ActivityLog'
import { ChartersPage } from '@/components/charters/ChartersPage'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'
import { JobsPage } from '@/components/jobs/JobsPage'
import { LogsView } from '@/components/logs/LogsView'
import { DiagnosticsPanel } from '@/components/environment/DiagnosticsPanel'
import { ProjectSettingsPanel } from '@/components/environment/ProjectSettingsPanel'
import { WorktreesPanel } from '@/components/environment/WorktreesPanel'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { ProjectHeader } from '@/components/layout/ProjectHeader'
import { ProjectTabs } from '@/components/layout/ProjectTabs'
import { SetupModal } from '@/components/layout/SetupModal'
import {
  Sidebar,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_WIDTH,
  type SidebarPage,
} from '@/components/layout/Sidebar'
import { OverviewPage } from '@/components/overview/OverviewPage'
import { ProjectManagerModal, type ProjectManagerMode } from '@/components/projects/ProjectManagerModal'
import { QualityHealthPanel } from '@/components/quality/QualityHealthPanel'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { RunnersPage } from '@/components/runners/RunnersPage'
import { SpecPage } from '@/components/spec/SpecPage'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { Button } from '@/components/ui/button'
import { useSSE } from '@/hooks/useSSE'
import { useWorkspaceNavigation } from '@/hooks/useWorkspaceNavigation'
import {
  agentDestination,
  environmentDestination,
  projectDestination,
  type EnvironmentSection,
} from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'

const SIDEBAR_WIDTH_KEY = 'aw.sidebarWidth'

export default function App() {
  const { isConfigured, mode, bootstrapState, selectedProjectId: projectId } = useConfigStore()
  const { data: projects } = useProjects()
  const { data: agents = [] } = useAgents()
  const [setupOpen, setSetupOpen] = useState(false)
  const [projectManagerMode, setProjectManagerMode] = useState<ProjectManagerMode | null>(null)
  const [agentCreateProjectId, setAgentCreateProjectId] = useState<string | null>(null)
  const [overviewQuestionsOpen, setOverviewQuestionsOpen] = useState(false)
  const [activitySubview, setActivitySubview] = useState<'activity' | 'logs'>('activity')
  const { destination, navigate: navigateTo } = useWorkspaceNavigation({
    availableProjectIds: projects ? projects.map((project) => project.id) : null,
    lastOpenedProjectId: projectId,
  })
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
    document.documentElement.dataset.mode = mode
  }, [mode])

  useEffect(() => {
    const destinationProjectId = destination.kind === 'zero' ? null : destination.projectId
    if (destinationProjectId !== projectId) {
      useConfigStore.getState().setSelectedProject(destinationProjectId)
    }
  }, [destination, projectId])

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
          <Button
            variant="primary"
            size="md"
            onClick={() => useConfigStore.getState().bootstrap()}
            className="mt-1"
          >
            Retry
          </Button>
        </div>
      </div>
    )
  }

  const activePage: SidebarPage | 'overview' | null = destination.kind === 'project'
    ? destination.tab === 'environment'
      ? (destination.environmentSection as SidebarPage)
      : destination.tab
    : null
  const selectedAgent = destination.kind === 'conversation'
    ? agents.find((agent) => agent.name === destination.agent) ?? null
    : null
  const currentProjectId = destination.kind === 'zero' ? projectId || '' : destination.projectId
  const currentProject = projects?.find((project) => project.id === currentProjectId)
  const railResizable = activePage !== 'spec'

  const navigate = (value: string) => {
    if (value.startsWith('agent:')) {
      navigateTo(agentDestination(currentProjectId, value.slice('agent:'.length)))
      return
    }
    if (value === 'overview') {
      navigateTo(projectDestination(currentProjectId))
      return
    }
    if (value === 'tasks' || value === 'spec' || value === 'jobs' || value === 'activity') {
      navigateTo(projectDestination(currentProjectId, value))
      return
    }
    if (value === 'questions') {
      setOverviewQuestionsOpen(true)
      navigateTo(projectDestination(currentProjectId, 'overview'))
      return
    }
    if (value === 'logs') {
      setActivitySubview('logs')
      navigateTo(projectDestination(currentProjectId, 'activity'))
      return
    }
    navigateTo(environmentDestination(currentProjectId, value as Parameters<typeof environmentDestination>[1]))
  }

  let content: React.ReactNode
  if (destination.kind === 'conversation') {
    content = selectedAgent ? (
      <AgentOutputPanel
        agent={selectedAgent}
        initialConversationId={destination.conversationId}
        onConversationChange={(conversationId) => {
          if (destination.conversationId !== conversationId) {
            navigateTo(agentDestination(destination.projectId, destination.agent, conversationId))
          }
        }}
        onBackToProject={() => navigateTo(projectDestination(destination.projectId))}
      />
    ) : (
      <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
        Agent unavailable.
      </div>
    )
  } else if (destination.kind === 'project') {
    let projectContent: React.ReactNode
    if (destination.tab === 'overview') {
      projectContent = overviewQuestionsOpen
        ? <QuestionsPanel />
        : <OverviewPage onNavigate={navigate} />
    } else if (destination.tab === 'tasks') {
      projectContent = <TasksBoard />
    } else if (destination.tab === 'spec') {
      projectContent = <SpecPage />
    } else if (destination.tab === 'jobs') {
      projectContent = <JobsPage />
    } else if (destination.tab === 'activity') {
      projectContent = (
        <div className="flex h-full flex-col">
          <div className="flex gap-1 px-4 pt-3">
            {(['activity', 'logs'] as const).map((view) => (
              <button
                key={view}
                type="button"
                data-testid={`activity-subview-${view}`}
                onClick={() => setActivitySubview(view)}
                className="px-3 py-1.5 text-xs capitalize"
                aria-pressed={activitySubview === view}
              >
                {view}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {activitySubview === 'activity' ? <ActivityLog /> : <LogsView />}
          </div>
        </div>
      )
    } else if (destination.tab === 'environment') {
      const section = destination.environmentSection
      const environmentPages: Record<EnvironmentSection, React.ReactNode> = {
        quality: <QualityHealthPanel />,
        instructions: <InstructionsPage />,
        runners: <RunnersPage />,
        charters: <ChartersPage />,
        worktrees: <WorktreesPanel />,
        diagnostics: <DiagnosticsPanel />,
        budgets: <AccountingPanel />,
        settings: <ProjectSettingsPanel />,
      }
      projectContent = <div className="min-w-0 h-full overflow-auto">{environmentPages[section]}</div>
    }
    content = (
      <div className="flex h-full flex-col" data-testid="active-page-wrapper">
        {destination.tab !== 'environment' && (
          <ProjectTabs
            active={destination.tab}
            onSelect={(tab) => {
              setOverviewQuestionsOpen(false)
              if (tab === 'activity') setActivitySubview('activity')
              navigateTo(projectDestination(destination.projectId, tab))
            }}
          />
        )}
        <div className={destination.tab === 'spec' ? 'min-h-0 flex-1 overflow-auto' : 'workspace-content min-h-0 flex-1 overflow-auto'}>{projectContent}</div>
      </div>
    )
  } else {
    content = (
      <div className="flex h-full items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
        Open or create a project to begin.
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="workspace-shell flex h-full overflow-hidden">
          <Sidebar
            destination={destination}
            activePage={activePage}
            activeAgent={destination.kind === 'conversation' ? destination.agent : null}
            activeConversation={
              destination.kind === 'conversation' ? destination.conversationId : null
            }
            onOpenProject={(id) => navigateTo(projectDestination(id))}
            onOpenAgent={(id, agent) => navigateTo(agentDestination(id, agent))}
            onOpenConversation={(id, agent, conversationId) =>
              navigateTo(agentDestination(id, agent, conversationId))
            }
            onOpenEnvironment={(id, section) => navigateTo(environmentDestination(id, section))}
            onAddAgent={(id) => setAgentCreateProjectId(id)}
            onOpenExisting={() => setProjectManagerMode('open')}
            onCreateProject={() => setProjectManagerMode('create')}
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
          <main className="flex min-w-0 flex-1 flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
            {currentProject && (
              <ProjectHeader
                projectName={currentProject.name}
                pathDisplay={currentProject.path_display}
                agentCount={currentProject.agents.length}
                directoryAvailable={currentProject.directory_state === 'available'}
                onOpenSetup={() => setSetupOpen(true)}
              />
            )}
            <div className="min-h-0 flex-1 overflow-hidden">{content}</div>
          </main>
      </div>
      <SetupModal open={!isConfigured || setupOpen} onClose={() => setSetupOpen(false)} />
      <ProjectManagerModal
        mode={projectManagerMode}
        onClose={() => setProjectManagerMode(null)}
        onComplete={(project) => {
          useConfigStore.getState().setSelectedProject(project.id)
          navigateTo(projectDestination(project.id))
          setProjectManagerMode(null)
        }}
      />
      {agentCreateProjectId && (
        <AgentCreateDialog
          open
          onClose={() => setAgentCreateProjectId(null)}
          onCreated={(name) => {
            const createdProjectId = agentCreateProjectId
            setAgentCreateProjectId(null)
            navigateTo(agentDestination(createdProjectId, name))
          }}
        />
      )}
    </div>
  )
}
