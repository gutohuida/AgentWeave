import { useEffect, useState } from 'react'
import { AccountingPanel } from '@/components/accounting/AccountingPanel'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { ConversationView } from '@/components/agents/ConversationView'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
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
import { CommandPalette } from '@/components/palette/CommandPalette'
import { ProjectManagerModal, type ProjectManagerMode } from '@/components/projects/ProjectManagerModal'
import { QualityHealthPanel } from '@/components/quality/QualityHealthPanel'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { RunnersPage } from '@/components/runners/RunnersPage'
import { useSpecDocuments } from '@/api/spec'
import { SpecPage } from '@/components/spec/SpecPage'
import { useTasks } from '@/api/tasks'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { Button } from '@/components/ui/button'
import { useSSE } from '@/hooks/useSSE'
import { useWorkspaceNavigation } from '@/hooks/useWorkspaceNavigation'
import {
  agentDestination,
  agentSettingsBackDestination,
  agentSettingsDestination,
  environmentDestination,
  isNewConversationDestination,
  newConversationDestination,
  projectDestination,
  resolveConversationSelection,
  withDocument,
  type EnvironmentSection,
} from '@/lib/navigation'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { useProjectConversations } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'

const SIDEBAR_WIDTH_KEY = 'aw.sidebarWidth'
const SIDEBAR_COLLAPSED_KEY = 'aw.sidebarCollapsed'

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
  /** The operator's own choice, and nothing else's. No destination may write this — a page that
   *  wants horizontal space does not get to take it from navigation. */
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
    } catch {
      // Persistence is optional.
    }
  }, [sidebarWidth])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed))
    } catch {
      // Persistence is optional.
    }
  }, [sidebarCollapsed])

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

  // The same query the rail draws from, so resolving a destination costs no extra request.
  const currentProjectId = destination.kind === 'zero' ? projectId || '' : destination.projectId
  const { data: projectConversations } = useProjectConversations(currentProjectId || null)
  // Read by the command palette (D3) — the same queries `SpecPage`/`TasksBoard` already use, not
  // a fetch the palette introduces of its own.
  const { data: specDocuments } = useSpecDocuments()
  const { data: allTasks } = useTasks()
  const resolvedConversationId = resolveConversationSelection(
    destination,
    projectConversations?.conversations ?? [],
  )

  // Auto-selection is destination resolution, not a navigation the operator performed: it is
  // written back with `replace` so Back does not return to the conversation they are already in.
  // It deliberately does nothing when the destination names a conversation, and nothing when the
  // destination *is* the new-conversation surface — `resolveConversationSelection` returns null
  // there, which is the whole reason that sentinel is distinct from "unspecified".
  useEffect(() => {
    if (destination.kind !== 'conversation') return
    if (destination.agent === null) return
    if (destination.conversationId !== null) return
    if (!resolvedConversationId) return
    navigateTo(
      agentDestination(
        destination.projectId,
        destination.agent,
        resolvedConversationId,
        destination.document,
      ),
      { replace: true },
    )
  }, [destination, resolvedConversationId, navigateTo])

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
  const currentProject = projects?.find((project) => project.id === currentProjectId)

  /**
   * The document open right now, carried onto every conversation the operator moves to.
   *
   * A document is what they are working on, not a property of the thread they are working on it
   * in — so changing agent while reading a specification keeps it open, and changing agent with
   * it closed keeps it closed (operator, 2026-08-10: *"a memory between agents"*). It is `null`
   * anywhere that is not a conversation, so arriving from a project tab opens nothing: the
   * memory is of what is on screen, not a preference that outlives leaving the surface.
   */
  const openDocument = destination.kind === 'conversation' ? destination.document : null

  const navigate = (value: string) => {
    if (value.startsWith('agent:')) {
      navigateTo(agentDestination(currentProjectId, value.slice('agent:'.length), null, openDocument))
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

  /**
   * An agent that has never held a conversation is starting one.
   *
   * Reaching such an agent from the rail produces a destination with an *unspecified*
   * conversation, which resolves to null because there is nothing to resolve to — and that used
   * to fall through to the conversation panel, giving a bare composer with no heading and no
   * indication of whose conversation it was about to be. The start surface is what belongs there.
   *
   * Gated on the query having answered: an empty list while it loads is "not known yet", not
   * "none", and treating the two alike would flash this surface at every agent.
   */
  const conversationsKnown = projectConversations !== undefined
  const agentHasNoConversations =
    destination.kind === 'conversation' &&
    destination.agent !== null &&
    destination.conversationId === null &&
    conversationsKnown &&
    !(projectConversations?.conversations ?? []).some(
      (conversation) => conversation.agent === destination.agent,
    )

  let content: React.ReactNode
  if (
    destination.kind === 'conversation' &&
    (isNewConversationDestination(destination) || agentHasNoConversations)
  ) {
    // Composer-primary and creating nothing until the first message is sent, so abandoning it
    // leaves no conversation record (spec: "An abandoned start leaves no record").
    content = (
      <NewConversationSurface
        projectId={destination.projectId}
        agent={destination.agent}
        // Replace, not push: retargeting an unsent message is a change of mind about one
        // message, not a place the operator navigated to and might want Back out of.
        onChooseAgent={(agent) =>
          navigateTo(newConversationDestination(destination.projectId, agent, openDocument), {
            replace: true,
          })
        }
        onStarted={(agent, conversationId, document) =>
          navigateTo(
            agentDestination(
              destination.projectId,
              agent,
              conversationId,
              document ?? openDocument,
            ),
          )
        }
        onBackToProject={() => navigateTo(projectDestination(destination.projectId))}
      />
    )
  } else if (destination.kind === 'conversation') {
    const agentName = destination.agent
    const conversationDestination = destination
    content = selectedAgent && agentName ? (
      <ConversationView
        agent={selectedAgent}
        conversationId={resolvedConversationId}
        document={destination.document}
        onSelectConversation={(conversationId) => {
          if (destination.conversationId !== conversationId) {
            navigateTo(
              agentDestination(
                destination.projectId,
                agentName,
                conversationId,
                // The document stays open across a conversation change: it is what the operator
                // is working on, not a property of the thread they are working on it in.
                destination.document,
              ),
            )
          }
        }}
        onOpenDocument={(path) => navigateTo(withDocument(conversationDestination, path))}
        onBackToProject={() => navigateTo(projectDestination(destination.projectId))}
        onOpenAgentSettings={() =>
          navigateTo(agentSettingsDestination(destination.projectId, agentName))
        }
      />
    ) : (
      <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
        Agent unavailable.
      </div>
    )
  } else if (destination.kind === 'agent-settings') {
    content = <AgentSettingsPage agent={destination.agent} section={destination.section} />
  } else if (destination.kind === 'project') {
    let projectContent: React.ReactNode
    if (destination.tab === 'overview') {
      projectContent = overviewQuestionsOpen
        ? <QuestionsPanel />
        : <OverviewPage onNavigate={navigate} />
    } else if (destination.tab === 'tasks') {
      projectContent = (
        <TasksBoard
          // A task's requirement chip, clicked: land on that requirement in its document,
          // scrolled into view — the other direction of F4's cross-tab navigation.
          onOpenRequirement={(documentPath, anchor) =>
            navigateTo(projectDestination(destination.projectId, 'spec', documentPath, anchor))
          }
        />
      )
    } else if (destination.tab === 'spec') {
      projectContent = (
        <SpecPage
          document={destination.document ?? null}
          anchor={destination.anchor ?? null}
          // Replace: which document the Spec screen resolved to is not a place the operator
          // navigated to, and Back should leave the screen rather than walk its documents.
          onOpenDocument={(path) =>
            navigateTo(projectDestination(destination.projectId, 'spec', path), { replace: true })
          }
          // A coverage row's task-count link, clicked: switch to the Tasks tab filtered to what
          // it names. The filter is set on the global store because the board it applies to is
          // not mounted yet — this navigation is what mounts it.
          onOpenTasks={(taskIds) => {
            useTaskFilterStore.getState().setActiveTaskIds(taskIds)
            navigateTo(projectDestination(destination.projectId, 'tasks'))
          }}
        />
      )
    } else if (destination.tab === 'jobs') {
      projectContent = (
        <JobsPage
          // A loop's queue/current-item link, clicked: same cross-tab filter mechanism as the
          // spec coverage bar's task-count link above — switch to Tasks, filtered.
          onOpenTasks={(taskIds) => {
            useTaskFilterStore.getState().setActiveTaskIds(taskIds)
            navigateTo(projectDestination(destination.projectId, 'tasks'))
          }}
        />
      )
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
        {/* The Spec screen lays out its own two panes edge to edge, so it opts out of
            `workspace-content`'s centred 1180px column and page padding — those are for a page of
            content, and this is a workspace. */}
        <div
          className={
            destination.tab === 'spec'
              ? 'min-h-0 flex-1 overflow-hidden'
              : 'workspace-content min-h-0 flex-1 overflow-auto'
          }
        >
          {projectContent}
        </div>
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
            activeAgent={
              destination.kind === 'conversation' || destination.kind === 'agent-settings'
                ? destination.agent
                : null
            }
            activeConversation={
              destination.kind === 'conversation' ? destination.conversationId : null
            }
            onOpenProject={(id) => navigateTo(projectDestination(id))}
            onOpenAgent={(id, agent) => navigateTo(agentDestination(id, agent, null, openDocument))}
            onOpenConversation={(id, agent, conversationId) =>
              navigateTo(agentDestination(id, agent, conversationId, openDocument))
            }
            onNewConversation={(id, agent) =>
              navigateTo(newConversationDestination(id, agent, openDocument))
            }
            onOpenEnvironment={(id, section) => navigateTo(environmentDestination(id, section))}
            onOpenAgentSettings={(id, agent, section) =>
              navigateTo(agentSettingsDestination(id, agent, section))
            }
            onBackFromAgentSettings={(id, agent) =>
              navigateTo(agentSettingsBackDestination(agentSettingsDestination(id, agent)))
            }
            // The rail stands in for the project tree while the Spec screen is open, so choosing
            // a document is a rail action there.
            onOpenSpecDocument={(id, path) =>
              navigateTo(projectDestination(id, 'spec', path), { replace: true })
            }
            onAddAgent={(id) => setAgentCreateProjectId(id)}
            // One action. `open_existing` resolves a known path, a marked directory, or a plain
            // folder it initialises, so "create" never needed a separate entry point.
            onAddProject={() => setProjectManagerMode('open')}
            compact={sidebarCollapsed}
            onCompactChange={setSidebarCollapsed}
            width={sidebarWidth}
          />
          {/* A collapsed rail has one width, so there is nothing to drag. */}
          {!sidebarCollapsed && (
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
            navigateTo(agentDestination(createdProjectId, name, null, openDocument))
          }}
        />
      )}
      <CommandPalette
        agents={agents}
        conversations={projectConversations?.conversations ?? []}
        documents={specDocuments?.documents ?? []}
        tasks={allTasks ?? []}
        onOpenConversation={(agent, conversationId) =>
          navigateTo(agentDestination(currentProjectId, agent, conversationId, openDocument))
        }
        onOpenAgent={(agent) =>
          navigateTo(agentDestination(currentProjectId, agent, null, openDocument))
        }
        onOpenDocument={(path) =>
          navigateTo(projectDestination(currentProjectId, 'spec', path), { replace: true })
        }
        onOpenTask={(taskId) => {
          useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
          navigateTo(projectDestination(currentProjectId, 'tasks'))
        }}
      />
    </div>
  )
}
