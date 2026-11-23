import { Suspense, useEffect, useRef, useState } from 'react'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
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
import { settingDestination } from '@/lib/settingsIndex'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { setupTitle } from '@/components/overview/setupItems'
import { CommandPalette } from '@/components/palette/CommandPalette'
import { ProjectManagerModal, type ProjectManagerMode } from '@/components/projects/ProjectManagerModal'
import { useSpecDocuments } from '@/api/spec'
import { useTasks } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useSSE } from '@/hooks/useSSE'
import { useNotifications } from '@/hooks/useNotifications'
import { useWorkspaceNavigation } from '@/hooks/useWorkspaceNavigation'
import {
  TOP_BAR_TABS,
  type GoToName,
  type ProjectTab,
  agentDestination,
  managerRunDestination,
  agentSettingsDestination,
  resolveAgentSettingsSection,
  appSettingsDestination,
  buildDestination,
  destinationProjectId,
  environmentDestination,
  isNewConversationDestination,
  newConversationDestination,
  projectDestination,
  evidenceDestination,
  projectAddress,
  resolveConversationSelection,
  threadCheckpointsDestination,
  threadDestination,
  topBarTabFor,
  withDocument,
  type WorkspaceDestination,
} from '@/lib/navigation'
import { findCheckpointOwner } from '@/api/checkpoints'
import { toast } from '@/lib/toast'
import { applyColorMode } from '@/lib/colorMode'
import { linkTarget } from '@/lib/threadKnots'
import { useProjectConversations } from '@/api/agentChat'
import { useConversationSpecDocuments, useSetConversationDocumentFor } from '@/api/conversationSpec'
import { useConfigStore } from '@/store/configStore'
import { useBoardScopeStore } from '@/store/boardScopeStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { usePanelTabsStore, loopTabId } from '@/store/panelTabsStore'
import { ManagerIndicator } from '@/components/manager/ManagerIndicator'
import { MENDER_JOB } from '@/components/manager/managerRuns'
import { CheckpointStatusBanner } from '@/components/checkpoints/CheckpointStatusBanner'
import { LoadingThread } from '@/components/common/LoadingThread'
import {
  AgentCreateDialog,
  AppSettingsScreen,
  ArchivedAgentNotice,
  BuildViewContainer,
  ConversationView,
  EvidenceBrowser,
  DashboardsScreen,
  NewConversationSurface,
  ProfilesScreen,
  ProjectSettingsScreen,
  QuestionsPanel,
  RequirementStory,
  SpecPage,
  TasksScreen,
  ThreadScreen,
  VaultScreen,
  prefetchScreens,
} from '@/lib/lazyScreens'

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

/** A conversation destination's pending `checkpoint`, carried across the address rewrites that only
 *  settle which thread or document is open, so the link is not lost before the view consumes it. */
function keptCheckpoint(destination: WorkspaceDestination): { checkpoint?: string } {
  return destination.kind === 'conversation' && destination.checkpoint ? { checkpoint: destination.checkpoint } : {}
}

export default function App() {
  const { isConfigured, mode, bootstrapState, selectedProjectId: projectId } = useConfigStore()
  const { data: projects } = useProjects()
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  // A folded agent is off the open roster but its conversations still open, read-only.
  const { data: allAgents = [], error: allAgentsError } = useAgents('all')
  const [setupOpen, setSetupOpen] = useState(false)
  const [projectManagerMode, setProjectManagerMode] = useState<ProjectManagerMode | null>(null)
  const [agentCreateProjectId, setAgentCreateProjectId] = useState<string | null>(null)
  const [overviewQuestionsOpen, setOverviewQuestionsOpen] = useState(false)
  const { destination, navigate: navigateTo } = useWorkspaceNavigation({
    availableProjectIds: projects ? projects.map((project) => project.id) : null,
    lastOpenedProjectId: projectId,
  })
  // A spec view's task link, clicked (the Spec tab's page and the conversation panel's spec tab):
  // switch to the Tasks board. A spec page's own link (it names the document) sets the board's
  // remembered spec scope; a coverage row's list of ids stays a separate, overriding narrowing.
  // The stores are global because the board they apply to is not mounted yet.
  const openTasksFor = (targetProjectId: string, taskIds: string[], specDocumentId?: string) => {
    if (specDocumentId) {
      useBoardScopeStore.getState().setScope(targetProjectId, { kind: 'spec', id: specDocumentId })
      useTaskFilterStore.getState().clearActiveTaskIds()
    } else {
      useTaskFilterStore.getState().setActiveTaskIds(taskIds)
    }
    navigateTo(projectDestination(targetProjectId, 'tasks'))
  }
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

  // Once the project list has drawn, the screens not in the first script load while the page is
  // idle, so the first click on a tab or a conversation does not wait for its chunk.
  const projectsLoaded = projects !== undefined
  useEffect(() => {
    if (projectsLoaded) prefetchScreens()
  }, [projectsLoaded])

  useEffect(() => {
    useConfigStore.getState().bootstrap()
  }, [])

  useEffect(() => {
    document.documentElement.dataset.mode = mode
  }, [mode])

  useEffect(() => {
    const openProjectId = destinationProjectId(destination)
    if (openProjectId !== projectId) {
      useConfigStore.getState().setSelectedProject(openProjectId)
    }
  }, [destination, projectId])

  // The same query the rail draws from, so resolving a destination costs no extra request.
  const currentProjectId = destinationProjectId(destination) ?? (projectId || '')
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

  // The conversation's own document (FR-11, FR-12): what the Hub holds for it is what it opens
  // with, and a document the destination names that the Hub does not hold is written to it.
  const syncedConversationId = destination.kind === 'conversation' ? resolvedConversationId ?? null : null
  const conversationDocuments = useConversationSpecDocuments(currentProjectId || null, syncedConversationId)
  const setConversationDocument = useSetConversationDocumentFor(currentProjectId || null)
  const documentWrite = useRef(false)
  useEffect(() => {
    if (destination.kind !== 'conversation' || !syncedConversationId) return
    if (documentWrite.current || setConversationDocument.isPending) return
    if (conversationDocuments.error || !conversationDocuments.data || conversationDocuments.isFetching) return
    const held = conversationDocuments.data.attached?.path ?? null
    if (destination.document === held) return
    if (destination.document === null) {
      navigateTo(
        { ...agentDestination(destination.projectId, destination.agent ?? '', syncedConversationId, held), ...keptCheckpoint(destination) },
        { replace: true },
      )
    } else {
      // A URL's document can be stale (the agent renames a placeholder path at intake): when the
      // Hub refuses it, the document it holds for the conversation wins and the URL follows.
      const conversationId = syncedConversationId
      setConversationDocument.mutate(
        { conversationId, path: destination.document },
        {
          onError: () =>
            navigateTo(
              { ...agentDestination(destination.projectId, destination.agent ?? '', conversationId, held), ...keptCheckpoint(destination) },
              { replace: true },
            ),
        },
      )
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `setConversationDocument` is a fresh object each render
  }, [destination, syncedConversationId, conversationDocuments.data, conversationDocuments.isFetching, conversationDocuments.error,
    navigateTo, setConversationDocument.isPending])

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
      {
        ...agentDestination(destination.projectId, destination.agent, resolvedConversationId, destination.document),
        ...keptCheckpoint(destination),
      },
      { replace: true },
    )
  }, [destination, resolvedConversationId, navigateTo])

  // A checkpoint address that does not name its thread (the retired Checkpoints tab's): look the
  // owner up, then replace the address with that thread and its Checkpoints panel tab. A lookup
  // that finds nothing, or fails, lands on the Overview and says so, never on a blank page (D2).
  useEffect(() => {
    if (destination.kind !== 'checkpoint-lookup') return
    let cancelled = false
    const { projectId: pid, checkpoint, conversation } = destination
    const notFound = () => {
      toast({ title: checkpoint ? 'That checkpoint could not be found' : 'That thread could not be found', tone: 'error' })
      navigateTo(projectDestination(pid), { replace: true })
    }
    findCheckpointOwner(pid, { checkpoint, conversation }).then(
      (owner) => {
        if (cancelled) return
        if (!owner) return notFound()
        navigateTo(
          threadCheckpointsDestination(pid, owner.agent, owner.conversationId, checkpoint ?? undefined),
          { replace: true },
        )
      },
      () => {
        if (!cancelled) notFound()
      },
    )
    return () => {
      cancelled = true
    }
  }, [destination, navigateTo])

  useSSE()
  // A notification's Open goes to the project's overview, where its questions and stalls are; a
  // reply's goes to its conversation. A reply in the conversation on screen calls nobody.
  const viewingConversation = useRef<string | null>(null)
  viewingConversation.current = destination.kind === 'conversation' ? resolvedConversationId ?? null : null
  useNotifications(
    (projectId, conversation) => {
      useConfigStore.getState().setSelectedProject(projectId)
      navigateTo(
        conversation
          ? agentDestination(projectId, conversation.agent, conversation.conversationId)
          : projectDestination(projectId, 'overview'),
      )
    },
    (conversationId) => conversationId === viewingConversation.current,
  )

  if (bootstrapState === 'pending') {
    return <HubConnectionState state="pending" />
  }

  if (bootstrapState === 'unreachable') {
    return <HubConnectionState state="unreachable" onRetry={() => useConfigStore.getState().bootstrap()} />
  }

  const selectedAgent = destination.kind === 'conversation'
    ? agents.find((agent) => agent.name === destination.agent)
      ?? allAgents.find((agent) => agent.name === destination.agent && agent.folded_into)
      ?? null
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
  // Tasks the operator has to look at: finished work waiting on review.
  const awaitingReview = (allTasks ?? []).filter(
    (task) => task.status === 'completed' || task.status === 'under_review',
  ).length

  /** A theme flip repaints every surface at once; transitions are suspended for that frame so it
   *  is one change rather than a hundred staggered fades. */
  const toggleMode = () => applyColorMode(mode === 'light' ? 'dark' : 'light')

  const navigate = (value: string) => {
    // `agent-settings:<name>:<section>` -- the Overview's agent cards link a flag to the section that
    // fixes it (a missing charter to Charter). Agent names cannot hold a colon (AGENT_NAME_RE).
    if (value.startsWith('agent-settings:')) {
      const [, agentName, section] = value.split(':')
      navigateTo(agentSettingsDestination(
        currentProjectId, agentName, resolveAgentSettingsSection(section) ?? undefined,
      ))
      return
    }
    if (value.startsWith('agent:')) {
      navigateTo(agentDestination(currentProjectId, value.slice('agent:'.length)))
      return
    }
    if (value === 'overview') {
      navigateTo(projectDestination(currentProjectId))
      return
    }
    // A tab by name, retired ones included (Activity, Jobs, Logs, Traces open where they now live).
    if (['thread', 'tasks', 'spec', 'jobs', 'activity', 'ledger', 'logs', 'traces'].includes(value)) {
      navigateTo(projectAddress(currentProjectId, value))
      return
    }
    if (value === 'questions') {
      setOverviewQuestionsOpen(true)
      navigateTo(projectDestination(currentProjectId, 'overview'))
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
          navigateTo(newConversationDestination(destination.projectId, agent), {
            replace: true,
          })
        }
        onStarted={(agent, conversationId, document) =>
          navigateTo(
            agentDestination(destination.projectId, agent, conversationId, document),
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
        checkpoint={destination.checkpoint ?? null}
        onCheckpointConsumed={() => {
          const { checkpoint: _consumed, ...rest } = conversationDestination
          void _consumed
          navigateTo(rest, { replace: true })
        }}
        onSelectConversation={(conversationId) => {
          if (destination.conversationId !== conversationId) {
            // A conversation owns its document: the one switched to shows its own, or none,
            // which `useConversationDocumentSync` reads from the Hub (FR-12).
            navigateTo(agentDestination(destination.projectId, agentName, conversationId))
          }
        }}
        onOpenAgentConversation={(agent, conversationId) =>
          navigateTo(agentDestination(destination.projectId, agent, conversationId))
        }
        onOpenDocument={(path) => {
          // Written to the conversation first, so reopening or reloading shows it (FR-11).
          const target = resolvedConversationId
          const open = () => navigateTo(withDocument(conversationDestination, path))
          if (!target) return open()
          documentWrite.current = true
          setConversationDocument
            .mutateAsync({ conversationId: target, path })
            .then(open, open)
            .finally(() => {
              documentWrite.current = false
            })
        }}
        onBackToProject={() => navigateTo(projectDestination(destination.projectId))}
        onOpenAgentSettings={() =>
          navigateTo(agentSettingsDestination(destination.projectId, agentName))
        }
        onOpenTasks={(taskIds, specDocumentId) =>
          openTasksFor(destination.projectId, taskIds, specDocumentId)
        }
        onOpenJobs={(jobId) => navigateTo(environmentDestination(destination.projectId, 'jobs', null, jobId))}
        onOpenQuestions={() => {
          setOverviewQuestionsOpen(true)
          navigateTo(projectDestination(destination.projectId, 'overview'))
        }}
      />
    ) : (
      // Not while the open roster is still loading: every agent is absent from `[]`, and the notice
      // would describe an open agent as missing (the Round's review).
      agentsLoading ? null : agentName ? (
        <ArchivedAgentNotice agentName={agentName} />
      ) : (
        <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
          {allAgentsError ? 'Profile unavailable: the full roster could not be read.' : 'Profile unavailable.'}
        </div>
      )
    )
  } else if (destination.kind === 'app-settings') {
    const appSettingsDest = destination
    content = (
      <AppSettingsScreen
        section={appSettingsDest.section}
        setting={appSettingsDest.setting}
        onSelectSection={(section) => navigateTo(appSettingsDestination(appSettingsDest.projectId, section))}
        onOpenSetup={() => setSetupOpen(true)}
        back={
          appSettingsDest.projectId && currentProject
            ? {
                label: `Back to ${currentProject.name}`,
                onClick: () => navigateTo(projectDestination(appSettingsDest.projectId!)),
              }
            : undefined
        }
      />
    )
  } else if (destination.kind === 'project' || destination.kind === 'agent-settings') {
    const openTask = (taskId: string) => {
      useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
      navigateTo(projectDestination(destination.projectId, 'tasks'))
    }
    const openConversation = (agent: string, conversationId: string) =>
      navigateTo(agentDestination(destination.projectId, agent, conversationId))
    let projectContent: React.ReactNode
    // The Profiles tab: its index, and one profile's page (the `agent-settings` destination). One
    // screen for both, so going back to the index can hand focus to the row just left (FR-13).
    if (destination.kind === 'agent-settings' || destination.tab === 'profiles') {
      const pid = destination.projectId
      projectContent = (
        <ProfilesScreen
          projectId={pid}
          selected={destination.kind === 'agent-settings' ? destination.agent : null}
          section={destination.kind === 'agent-settings' ? destination.section : 'agent'}
          setting={destination.kind === 'agent-settings' ? destination.setting : null}
          onOpenIndex={() => navigateTo(projectDestination(pid, 'profiles'))}
          onOpenProfile={(agent, section) => navigateTo(agentSettingsDestination(pid, agent, section))}
          onOpenTask={openTask}
          onOpenBuild={(buildId) => navigateTo(buildDestination(pid, buildId))}
          onOpenConversation={openConversation}
          onNewThread={(agent) => navigateTo(newConversationDestination(pid, agent))}
          onAddProfile={() => setAgentCreateProjectId(pid)}
        />
      )
    } else if (destination.tab === 'overview') {
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
              navigateTo(agentDestination(pid, target.agent, target.conversation))
            } else if (target.to === 'evidence') navigateTo(evidenceDestination(pid, target.focus))
            else navigateTo(projectAddress(pid, target.tab))
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
        ) : destination.view === 'build' && destination.focus ? (
          <BuildViewContainer
            key={destination.focus}
            projectId={destination.projectId}
            buildId={destination.focus}
            address={{
              task: destination.buildTask ?? null,
              run: destination.buildRun ?? null,
              filter: destination.buildFilter ?? 'all',
            }}
            onNavigate={navigateTo}
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
          onOpenDocument={(path, anchor) =>
            navigateTo(projectDestination(destination.projectId, 'spec', path, anchor ?? null), { replace: true })
          }
          // A coverage row's task-count link, clicked: switch to the Tasks tab filtered to what
          // it names. The filter is set on the global store because the board it applies to is
          // not mounted yet — this navigation is what mounts it.
          onOpenTasks={(taskIds, specDocumentId) =>
            openTasksFor(destination.projectId, taskIds, specDocumentId)
          }
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
          onAddAgent={() => setAgentCreateProjectId(destination.projectId)}
        >
          {specView}
        </SpecPage>
      )
    } else if (destination.tab === 'vault') {
      projectContent = <VaultScreen />
    } else if (destination.tab === 'dashboards') {
      projectContent = <DashboardsScreen />
    } else if (destination.tab === 'environment') {
      projectContent = (
        <ProjectSettingsScreen
          section={destination.environmentSection}
          setting={destination.setting}
          focus={destination.focus}
          run={destination.run}
          onOpenRun={(runId) =>
            navigateTo(runId ? managerRunDestination(destination.projectId, runId) : environmentDestination(destination.projectId, 'manager'))
          }
          onOpenConversation={(conversationId) => navigateTo(agentDestination(destination.projectId, MENDER_JOB, conversationId))}
          onOpenTask={(taskId) => openTasksFor(destination.projectId, [taskId])}
          onSelectSection={(section) => navigateTo(environmentDestination(destination.projectId, section))}
          onNavigate={navigate}
          onOpenAppSettings={() => navigateTo(appSettingsDestination(destination.projectId))}
        />
      )
    }
    // Workspaces (Tasks, Spec, Vault) and screens that lay out and scroll themselves (Project
    // settings) take the whole area. Reading pages sit in `workspace-content`'s centred
    // column. Putting the board in that column once made each card narrow before the board had
    // even reached the viewport edge.
    const fills =
      destination.kind === 'project' && (
      destination.tab === 'spec' ||
      destination.tab === 'tasks' ||
      destination.tab === 'vault' ||
      destination.tab === 'environment')
    content = (
      <div className="flex h-full flex-col" data-testid="active-page-wrapper">
        <div
          className={fills ? 'min-h-0 flex-1 overflow-hidden' : 'workspace-content min-h-0 flex-1 overflow-auto'}
        >
          {projectContent}
        </div>
      </div>
    )
  } else if (destination.kind === 'checkpoint-lookup') {
    // Brief: the effect above replaces this with the checkpoint's thread, or the Overview.
    content = <LoadingThread label="Opening checkpoint" minHeight={240} />
  } else {
    content = (
      <div className="flex h-full items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
        Open or create a project to begin.
      </div>
    )
  }


  /** A project tab, from the top bar or the palette's Go to group: one way in, so both land alike.
   *  The palette also names retired tabs, which resolve to where they now live. */
  const openProjectTab = (projectId: string, tab: ProjectTab | GoToName) => {
    setOverviewQuestionsOpen(false)
    navigateTo(projectAddress(projectId, tab))
  }
  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div className="workspace-shell aw-app">
          <Sidebar
            activeConversation={
              destination.kind === 'conversation' ? destination.conversationId : null
            }
            activeBuild={
              destination.kind === 'project' && destination.tab === 'spec' && destination.view === 'build'
                ? (destination.focus ?? null)
                : null
            }
            onOpenProject={(id) => navigateTo(projectDestination(id))}
            onOpenConversation={(id, agent, conversationId) =>
              navigateTo(agentDestination(id, agent, conversationId))
            }
            onNewConversation={(id, agent) =>
              navigateTo(newConversationDestination(id, agent))
            }
            onOpenBuild={(id, buildId) => navigateTo(buildDestination(id, buildId))}
            onOpenEnvironment={(id, section) => navigateTo(environmentDestination(id, section))}
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
            onOpenAppSettings={() => navigateTo(appSettingsDestination(currentProjectId || null))}
            setupFor={(id) => (projects ?? []).find((p) => p.id === id)?.setup?.items.map(setupTitle) ?? []}
            appSettingsActive={destination.kind === 'app-settings'}
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
                tabs={TOP_BAR_TABS}
                active={
                  destination.kind === 'agent-settings'
                    ? 'profiles'
                    : destination.kind === 'project' && destination.tab !== 'environment'
                      ? topBarTabFor(destination.tab)
                      : null
                }
                counts={{ tasks: awaitingReview }}
                directoryAvailable={currentProject.directory_state === 'available'}
                onSelectTab={(tab) => openProjectTab(currentProject.id, tab)}
                onSelectProject={(id) => navigateTo(projectDestination(id))}
                onAddProject={() => setProjectManagerMode('open')}
                onOpenSetup={() => setSetupOpen(true)}
                onOpenPalette={openCommandPalette}
                onOpenSettings={() => navigateTo(environmentDestination(currentProject.id, 'general'))}
                settingsActive={destination.kind === 'project' && destination.tab === 'environment'}
                mode={mode === 'light' ? 'light' : 'dark'}
                onToggleMode={toggleMode}
                manager={
                  // Only once the store names the project shown: its reads are keyed on the store,
                  // and for the one commit a switch or a delete leaves them apart they would ask
                  // about the project being left (F729).
                  currentProject.id === projectId && <ManagerIndicator
                    onOpenRun={(runId) => navigateTo(managerRunDestination(currentProject.id, runId))}
                    onOpenConversation={(conversationId) => navigateTo(agentDestination(currentProject.id, MENDER_JOB, conversationId))}
                  />
                }
              />
            )}
            <div className="min-h-0 flex-1 overflow-hidden">
              {/* A screen not yet loaded (`lazyScreens`) shows how AgentWeave shows loading. */}
              <Suspense fallback={<LoadingThread label="Loading" minHeight={240} />}>{content}</Suspense>
            </div>
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
        <Suspense fallback={null}>
          <AgentCreateDialog
            open
            onClose={() => setAgentCreateProjectId(null)}
            onCreated={(name) => {
              const createdProjectId = agentCreateProjectId
              setAgentCreateProjectId(null)
              navigateTo(agentDestination(createdProjectId, name, null))
            }}
          />
        </Suspense>
      )}
      <CommandPalette
        agents={agents}
        conversations={projectConversations?.conversations ?? []}
        documents={specDocuments?.documents ?? []}
        tasks={allTasks ?? []}
        onOpenConversation={(agent, conversationId) =>
          navigateTo(agentDestination(currentProjectId, agent, conversationId))
        }
        onOpenAgent={(agent) =>
          navigateTo(agentDestination(currentProjectId, agent, null))
        }
        onOpenDocument={(path) =>
          navigateTo(projectDestination(currentProjectId, 'spec', path), { replace: true })
        }
        onOpenTask={(taskId) => {
          useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
          navigateTo(projectDestination(currentProjectId, 'tasks'))
        }}
        onOpenSetting={(entry, agent) => {
          const target = settingDestination(entry, currentProjectId || null, agent)
          if (target) navigateTo(target)
        }}
        onOpenProjectSettings={
          currentProject ? () => navigateTo(environmentDestination(currentProject.id, 'general')) : undefined
        }
        onOpenAgentSettings={
          currentProject ? (agent) => navigateTo(agentSettingsDestination(currentProject.id, agent)) : undefined
        }
        onOpenTab={currentProject ? (tab) => openProjectTab(currentProject.id, tab) : undefined}
      />
      <CheckpointStatusBanner />
      <Toaster />
    </div>
  )
}
