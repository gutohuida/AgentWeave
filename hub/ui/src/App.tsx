import { useEffect, useRef, useState } from 'react'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { ConversationView } from '@/components/agents/ConversationView'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { JobsScreen } from '@/components/jobs/JobsScreen'
import { ActivityScreen } from '@/components/activity/ActivityScreen'
import { ThreadScreen } from '@/components/thread/ThreadScreen'
import { ProjectSettingsScreen } from '@/components/settings/ProjectSettingsScreen'
import { VaultScreen } from '@/components/vault/VaultScreen'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { TopBar } from '@/components/layout/TopBar'
import { SetupModal } from '@/components/layout/SetupModal'
import {
  Sidebar,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_WIDTH,
} from '@/components/layout/Sidebar'
import { Toaster } from '@/components/ui/toast'
import { openCommandPalette } from '@/lib/palette'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { CommandPalette } from '@/components/palette/CommandPalette'
import { ProjectManagerModal, type ProjectManagerMode } from '@/components/projects/ProjectManagerModal'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import { useSpecDocuments } from '@/api/spec'
import { SpecPage } from '@/components/spec/SpecPage'
import { EvidenceBrowser } from '@/components/evidence/EvidenceBrowser'
import { RequirementStory } from '@/components/spec/RequirementStory'
import { useTasks } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useSSE } from '@/hooks/useSSE'
import { useNotifications } from '@/hooks/useNotifications'
import { useWorkspaceNavigation } from '@/hooks/useWorkspaceNavigation'
import {
  PROJECT_TABS,
  agentDestination,
  agentSettingsBackDestination,
  agentSettingsDestination,
  environmentDestination,
  isNewConversationDestination,
  newConversationDestination,
  projectDestination,
  evidenceDestination,
  resolveConversationSelection,
  threadDestination,
  withDocument,
} from '@/lib/navigation'
import { linkTarget } from '@/lib/threadKnots'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { ArchivedAgentNotice } from '@/components/agents/ArchivedAgentNotice'
import { useProjectConversations } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { usePanelTabsStore, loopTabId } from '@/store/panelTabsStore'
import { CheckpointStatusBanner } from '@/components/checkpoints/CheckpointStatusBanner'
import { LoadingThread } from '@/components/common/LoadingThread'

export function HubConnectionState({ state, onRetry }: { state: 'pending' | 'unreachable'; onRetry?: () => void }) {
  const pending = state === 'pending'
  return (
    <div className="flex h-screen items-center justify-center" style={{ background: 'var(--bg)' }}>
      <div className="trust-state" role={pending ? undefined : 'alert'}>
        <span className={`trust-state-icon${pending ? '' : ' is-error'}`}><Icon name={pending ? 'sync' : 'error_outline'} size={22} /></span>
        <h1 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{pending ? 'Connecting to the Hub' : "Can't reach the Hub"}</h1>
        {pending ? (
          <LoadingThread label="Connecting to the Hub" minHeight={96} className="mt-2" />
        ) : (
          <>
            <p className="mx-auto mt-2 text-xs" style={{ maxWidth: 320, color: 'var(--text-3)' }}>
              The dashboard couldn&apos;t connect to the Hub server. Make sure it&apos;s running, then retry.
            </p>
            <Button variant="primary" size="md" onClick={onRetry} className="mt-4">
              <Icon name="refresh" size={15} /> Retry
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

const SIDEBAR_WIDTH_KEY = 'aw.sidebarWidth'
const SIDEBAR_COLLAPSED_KEY = 'aw.sidebarCollapsed'

export default function App() {
  const { isConfigured, mode, bootstrapState, selectedProjectId: projectId } = useConfigStore()
  const { data: projects } = useProjects()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const [setupOpen, setSetupOpen] = useState(false)
  const [projectManagerMode, setProjectManagerMode] = useState<ProjectManagerMode | null>(null)
  const [agentCreateProjectId, setAgentCreateProjectId] = useState<string | null>(null)
  const [overviewQuestionsOpen, setOverviewQuestionsOpen] = useState(false)
  // The ledger leads (slice project-ledger): what the project did, before the live stream of it.
  const [activitySubview, setActivitySubview] = useState<'ledger' | 'activity' | 'logs'>('ledger')
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
  const { data: taskPage } = useTasks()
  const allTasks = taskPage?.tasks
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

  /**
   * The last document state the operator had while on a conversation, kept across destinations
   * that are not conversations.
   *
   * Recorded per project, because a document path belongs to one project's corpus and must not
   * follow the operator into another. Records `null` too: closing the document is a state worth
   * remembering, and is what keeps "changing agent with it closed keeps it closed" true.
   *
   * Declared here, above the bootstrap early-returns below, because it is a hook and the returns
   * are conditional.
   */
  const lastConversationDocument = useRef<{ projectId: string | null; document: string | null }>({
    projectId: null,
    document: null,
  })
  useEffect(() => {
    if (destination.kind === 'conversation') {
      lastConversationDocument.current = {
        projectId: destination.projectId,
        document: destination.document,
      }
    }
  }, [destination])

  useSSE()
  // A notification's Open goes to the project's overview, where its questions and stalls are.
  useNotifications((projectId) => {
    useConfigStore.getState().setSelectedProject(projectId)
    navigateTo(projectDestination(projectId, 'overview'))
  })

  if (bootstrapState === 'pending') {
    return <HubConnectionState state="pending" />
  }

  if (bootstrapState === 'unreachable') {
    return <HubConnectionState state="unreachable" onRetry={() => useConfigStore.getState().bootstrap()} />
  }

  const selectedAgent = destination.kind === 'conversation'
    ? agents.find((agent) => agent.name === destination.agent) ?? null
    : null
  const currentProject = projects?.find((project) => project.id === currentProjectId)

  /**
   * The document open right now, carried onto every conversation the operator moves to.
   *
   * A document is what they are working on, not a property of the thread they are working on it
   * in — so changing agent while reading a specification keeps it open, and changing agent with
   * it closed keeps it closed (operator, 2026-08-10: *"a memory between agents"*).
   *
   * It reads `null` on a project tab, deliberately and still: arriving at a conversation from
   * project-level work opens nothing, because the memory is of what is on screen rather than a
   * preference outliving the surface.
   *
   * **Agent settings is the exception**, because it is not somewhere the operator goes — it is a
   * detour about the very conversation they are in, entered and left by a Back button that lands
   * them where they started. Dropping the attachment across that round trip is a straightforward
   * loss (operator, 2026-08-20: *"leaving a conversation detaches the spec open"*), and not only
   * of a reading panel: the attachment is what the next turn is written against and what
   * restricts the agent's file writes, so it changed how the following run behaved with nothing
   * on screen to say so.
   */
  const rememberedDocument =
    destination.kind === 'agent-settings' &&
    lastConversationDocument.current.projectId === currentProjectId
      ? lastConversationDocument.current.document
      : null
  const openDocument =
    destination.kind === 'conversation' ? destination.document : rememberedDocument

  // Tasks the operator has to look at: finished work waiting on review.
  const awaitingReview = (allTasks ?? []).filter(
    (task) => task.status === 'completed' || task.status === 'under_review',
  ).length

  /** A theme flip repaints every surface at once; transitions are suspended for that frame so it
   *  is one change rather than a hundred staggered fades. */
  const toggleMode = () => {
    const next = mode === 'light' ? 'dark' : 'light'
    const root = document.documentElement
    root.classList.add('no-transitions')
    useConfigStore.getState().setMode(next)
    root.dataset.mode = next
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('no-transitions')))
  }

  const navigate = (value: string) => {
    // `agent-settings:<name>:<section>` -- the Overview's agent cards link a flag to the section that
    // fixes it (a missing charter to Charter). Agent names cannot hold a colon (AGENT_NAME_RE).
    if (value.startsWith('agent-settings:')) {
      const [, agentName, section] = value.split(':')
      navigateTo(agentSettingsDestination(
        currentProjectId, agentName, section as Parameters<typeof agentSettingsDestination>[2],
      ))
      return
    }
    if (value.startsWith('agent:')) {
      navigateTo(agentDestination(currentProjectId, value.slice('agent:'.length), null, openDocument))
      return
    }
    if (value === 'overview') {
      navigateTo(projectDestination(currentProjectId))
      return
    }
    if (value === 'thread' || value === 'tasks' || value === 'spec' || value === 'jobs' || value === 'activity') {
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
        projectName={currentProject?.name ?? destination.projectId}
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
        projectId={destination.projectId}
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
      // Not while the open roster is still loading: every agent is absent from `[]`, and the notice
      // would describe an open agent as missing (the Round's review).
      agentsLoading ? null : agentName ? (
        <ArchivedAgentNotice agentName={agentName} />
      ) : (
        <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
          Agent unavailable.
        </div>
      )
    )
  } else if (destination.kind === 'agent-settings') {
    const settingsDestination = destination
    content = (
      <AgentSettingsPage
        agent={settingsDestination.agent}
        section={settingsDestination.section}
        onSelectSection={(section) =>
          navigateTo(agentSettingsDestination(settingsDestination.projectId, settingsDestination.agent, section))
        }
        onBack={() =>
          navigateTo(
            agentSettingsBackDestination(
              agentSettingsDestination(settingsDestination.projectId, settingsDestination.agent),
              openDocument,
            ),
          )
        }
      />
    )
  } else if (destination.kind === 'project') {
    const openTask = (taskId: string) => {
      useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
      navigateTo(projectDestination(destination.projectId, 'tasks'))
    }
    const openConversation = (agent: string, conversationId: string) =>
      navigateTo(agentDestination(destination.projectId, agent, conversationId, openDocument))
    let projectContent: React.ReactNode
    if (destination.tab === 'overview') {
      projectContent = overviewQuestionsOpen
        ? <QuestionsPanel />
        : <OverviewScreen onNavigate={navigate} onOpenConversation={openConversation}
            onAddAgent={() => setAgentCreateProjectId(destination.projectId)}
          />
    } else if (destination.tab === 'thread') {
      projectContent = (
        <ThreadScreen
          key={destination.projectId}
          projectId={destination.projectId}
          knot={destination.knot ?? null}
          // Replace: which knot the reader last touched is where they are, not a place to go Back to.
          onAddress={(key) => navigateTo(threadDestination(destination.projectId, key), { replace: true })}
          onOpenLink={(link) => {
            const target = linkTarget(link)
            if (!target) return
            const pid = destination.projectId
            if (target.to === 'spec') navigateTo(projectDestination(pid, 'spec', target.path))
            else if (target.to === 'task') openTask(target.id)
            else if (target.to === 'conversation') {
              navigateTo(agentDestination(pid, target.agent, target.conversation, openDocument))
            } else if (target.to === 'evidence') navigateTo(evidenceDestination(pid, target.focus))
            else navigateTo(projectDestination(pid, target.tab))
          }}
        />
      )
    } else if (destination.tab === 'tasks') {
      // A task's requirement chip, clicked: land on that requirement in its document, scrolled
      // into view — the other direction of F4's cross-tab navigation.
      projectContent = (
        <TasksScreen
          onOpenRequirement={(documentPath, anchor) =>
            navigateTo(projectDestination(destination.projectId, 'spec', documentPath, anchor))
          }
          onOpenDocument={(path) => navigateTo(projectDestination(destination.projectId, 'spec', path))}
        />
      )
    } else if (destination.tab === 'spec') {
      // One screen with the document list beside it; the requirement story (slice
      // requirement-story) and the evidence view (slice evidence-browser) take the document's
      // place, each linkable and focused by the URL.
      const specView =
        destination.view === 'requirement' && destination.document && destination.focus ? (
          <RequirementStory
            key={`${destination.document}#${destination.focus}`}
            document={destination.document}
            identifier={destination.focus}
            onOpenDocument={(path) => navigateTo(projectDestination(destination.projectId, 'spec', path))}
            onOpenTask={openTask}
          />
        ) : destination.view === 'evidence' ? (
          <EvidenceBrowser
            focus={destination.focus ?? null}
            onFocus={(focus) =>
              navigateTo(evidenceDestination(destination.projectId, focus), { replace: true })
            }
            onOpenTask={openTask}
          />
        ) : undefined
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
          // A flow's tab lives in the conversation panel, which this screen does not mount. Open
          // the tab, then go to the flow's agent with NO document: the conversation view's mount
          // effect opens the attached document's tab, which would sit in front of the loop.
          onOpenLoop={(loop) => {
            if (!loop.agent) return
            usePanelTabsStore.getState().openTab(destination.projectId, loopTabId(loop.id))
            navigateTo(agentDestination(destination.projectId, loop.agent, null, null))
          }}
          onOpenEvidence={() => navigateTo(evidenceDestination(destination.projectId), { replace: true })}
          evidenceOpen={destination.view === 'evidence'}
        >
          {specView}
        </SpecPage>
      )
    } else if (destination.tab === 'vault') {
      projectContent = <VaultScreen />
    } else if (destination.tab === 'jobs') {
      projectContent = (
        <JobsScreen
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
        <ActivityScreen
          // The palette's `logs` route and the tab's reset to the ledger (F718) arrive through
          // this; the screen follows a changed value while mounted.
          initialView={activitySubview}
          onOpenTask={openTask}
          onOpenConversation={openConversation}
        />
      )
    } else if (destination.tab === 'environment') {
      projectContent = (
        <ProjectSettingsScreen
          section={destination.environmentSection}
          onSelectSection={(section) => navigateTo(environmentDestination(destination.projectId, section))}
          onNavigate={navigate}
        />
      )
    }
    // Workspaces (Tasks, Spec, Vault) and screens that lay out and scroll themselves (Activity,
    // Project settings) take the whole area. Reading pages sit in `workspace-content`'s centred
    // column. Putting the board in that column once made each card narrow before the board had
    // even reached the viewport edge.
    const fills =
      destination.tab === 'spec' ||
      destination.tab === 'tasks' ||
      destination.tab === 'vault' ||
      destination.tab === 'activity' ||
      destination.tab === 'environment'
    content = (
      <div className="flex h-full flex-col" data-testid="active-page-wrapper">
        <div
          className={fills ? 'min-h-0 flex-1 overflow-hidden' : 'workspace-content min-h-0 flex-1 overflow-auto'}
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
      <div className="workspace-shell aw-app">
          <Sidebar
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
            // Navigating is not decoration here, it is what scopes the dialog. Everything the
            // dialog reads — `useCreateAgent`, `useCharters`, `useProviderLaunchability` — resolves
            // the *selected* project, and selection is derived from the destination by the effect
            // above. So opening the dialog without navigating first pointed all three at whichever
            // project happened to be selected: the agent was created there, and then the operator
            // was navigated to the project they clicked, to an agent that was not in it. Every
            // other rail action already navigates; this was the one that did not.
            onAddAgent={(id) => {
              navigateTo(projectDestination(id))
              setAgentCreateProjectId(id)
            }}
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
          <main className="aw-main" style={{ background: 'var(--bg)' }}>
            {currentProject && (
              <TopBar
                project={{ id: currentProject.id, name: currentProject.name, path: currentProject.path_display ?? '' }}
                projects={(projects ?? []).map((project) => ({ id: project.id, name: project.name, path: project.path_display ?? '' }))}
                tabs={PROJECT_TABS}
                active={destination.kind === 'project' && destination.tab !== 'environment' ? destination.tab : null}
                counts={{ tasks: awaitingReview }}
                directoryAvailable={currentProject.directory_state === 'available'}
                onSelectTab={(tab) => {
                  setOverviewQuestionsOpen(false)
                  // The tab opens on the ledger, which leads (F718: this reset to the live stream, so
                  // the ledger was never what a click on Activity showed).
                  if (tab === 'activity') setActivitySubview('ledger')
                  navigateTo(projectDestination(currentProject.id, tab))
                }}
                onSelectProject={(id) => navigateTo(projectDestination(id))}
                onAddProject={() => setProjectManagerMode('open')}
                onOpenSetup={() => setSetupOpen(true)}
                onOpenPalette={openCommandPalette}
                onOpenSettings={() => navigateTo(environmentDestination(currentProject.id, 'settings'))}
                settingsActive={destination.kind === 'project' && destination.tab === 'environment'}
                mode={mode === 'light' ? 'light' : 'dark'}
                onToggleMode={toggleMode}
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
      <CheckpointStatusBanner />
      <Toaster />
    </div>
  )
}
