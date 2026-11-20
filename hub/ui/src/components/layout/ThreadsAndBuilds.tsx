import { useState } from 'react'
import type { AgentConversation } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import { ConversationRow } from './ConversationRow'

/** What a build needs from the operator, as `GET /builds` is to report it (D2 of
 *  profiles-threads-and-builds-everywhere): "stopped" first, otherwise its first task's need. */
export interface BuildNeed {
  kind: 'stopped' | 'stalled' | 'question' | 'gave-up'
  text: string
}

/** One build as the sidebar lists it: running, or needing the operator and not dismissed. */
export interface SidebarBuild {
  id: string
  document_title: string
  state: 'running' | 'stopped' | 'finished'
  tasks_total: number
  tasks_done: number
  needs_operator: BuildNeed | null
}

/** How many threads show before the rest go behind "Show more". The old recency view's cap,
 *  kept: the list is now only the operator's own threads, so fifteen covers a working day. */
export const THREADS_DISPLAY_CAP = 15

const NEED_LABEL: Record<BuildNeed['kind'], string> = {
  stopped: 'Stopped',
  stalled: 'Stalled',
  question: 'Has a question',
  'gave-up': 'Given up',
}

interface ThreadsAndBuildsProps {
  projectId: string
  profiles: ProjectAgentSummary[]
  /** The operator's threads, in the order the route returns them (newest activity first). */
  threads: AgentConversation[]
  archivedCount: number
  /** Fetched only once the operator asks for them; null until then. */
  archivedThreads: AgentConversation[] | null
  builds: SidebarBuild[]
  activeProject: boolean
  activeConversation: string | null
  activeBuild: string | null
  onOpenThread: (projectId: string, profile: string, conversationId: string) => void
  /** No profile is implied here; the new-thread surface asks which one. */
  onNewThread: (projectId: string) => void
  onOpenBuild: (projectId: string, buildId: string) => void
  onDismissBuild: (projectId: string, buildId: string) => void
  onShowArchived: (projectId: string, show: boolean) => void
}

/**
 * A project's part of the sidebar: its builds that are running or need the operator, then the
 * operator's own threads, newest first, each labelled with its profile.
 *
 * Replaces the agent tree and the recent-conversations view (profiles-threads-and-builds-everywhere
 * FR-1, FR-3). Task, review and mender runs are not here: they are reached through their build.
 */
export function ThreadsAndBuilds({
  projectId,
  profiles,
  threads,
  archivedCount,
  archivedThreads,
  builds,
  activeProject,
  activeConversation,
  activeBuild,
  onOpenThread,
  onNewThread,
  onOpenBuild,
  onDismissBuild,
  onShowArchived,
}: ThreadsAndBuildsProps) {
  const [showAll, setShowAll] = useState(false)
  const showArchived = archivedThreads !== null
  const colorFor = (name: string) =>
    agentColorVars(profiles.find((p) => p.name === name)?.color_index ?? null).accent
  const visible = showAll ? threads : threads.slice(0, THREADS_DISPLAY_CAP)
  const hidden = threads.length - visible.length

  const row = (conversation: AgentConversation, testId: string) => (
    <ConversationRow
      key={conversation.id}
      projectId={projectId}
      conversation={conversation}
      active={activeProject && activeConversation === conversation.id}
      onOpen={() => onOpenThread(projectId, conversation.agent, conversation.id)}
      agentColor={colorFor(conversation.agent)}
      agentName={conversation.agent}
      showProfile
      agentArchived={!profiles.some((p) => p.name === conversation.agent)}
      testId={testId}
    />
  )

  return (
    <div className="aw-rail-children aw-rail-tb" data-testid={`rail-threads-builds-${projectId}`}>
      {builds.length > 0 && (
        <section aria-label="Builds" data-testid={`rail-builds-${projectId}`}>
          <span className="aw-rail-section-label">Builds</span>
          {builds.map((build) => (
            <BuildRow
              key={build.id}
              build={build}
              active={activeProject && activeBuild === build.id}
              onOpen={() => onOpenBuild(projectId, build.id)}
              onDismiss={() => onDismissBuild(projectId, build.id)}
            />
          ))}
        </section>
      )}

      <section aria-label="Threads" data-testid={`rail-threads-${projectId}`}>
        <span className="aw-rail-section-label aw-rail-section-head">
          Threads
          {/* Empty, the list's own "Start a thread" row is the one way in; two would stack. */}
          {threads.length > 0 && (
            <button
              data-slot="icon-button"
              type="button"
              className="aw-icon-button"
              data-testid={`rail-new-thread-${projectId}`}
              aria-label="New thread"
              title="New thread"
              onClick={() => onNewThread(projectId)}
            >
              <Icon name="add" size={13} />
            </button>
          )}
        </span>

        {visible.map((conversation) => row(conversation, `rail-thread-${conversation.id}`))}

        {(hidden > 0 || showAll) && (
          <button
            data-slot="rail-more"
            type="button"
            className="aw-rail-more"
            data-testid={`rail-threads-more-${projectId}`}
            aria-expanded={showAll}
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? 'Show fewer' : `Show ${hidden} more`}
          </button>
        )}

        {threads.length === 0 && (
          <button
            data-slot="rail-empty"
            type="button"
            className="aw-rail-empty"
            data-testid={`rail-threads-empty-${projectId}`}
            onClick={() => onNewThread(projectId)}
          >
            <Icon name="add" size={13} />
            Start a thread
          </button>
        )}

        {archivedCount > 0 && (
          <button
            data-slot="rail-more"
            type="button"
            className="aw-rail-more"
            data-testid={`rail-threads-archived-${projectId}`}
            aria-expanded={showArchived}
            onClick={() => onShowArchived(projectId, !showArchived)}
          >
            {showArchived ? 'Hide archived' : `Show archived (${archivedCount})`}
          </button>
        )}
        {archivedThreads?.map((conversation) => row(conversation, `rail-thread-archived-${conversation.id}`))}
      </section>
    </div>
  )
}

/** One build: its document's title, and one signal for its state. A running build says how far
 *  it has got; a build that needs the operator says why, in amber, and can be dismissed. */
function BuildRow({
  build,
  active,
  onOpen,
  onDismiss,
}: {
  build: SidebarBuild
  active: boolean
  onOpen: () => void
  onDismiss: () => void
}) {
  const running = build.state === 'running'
  const need = build.needs_operator
  const progress = `${build.tasks_done} of ${build.tasks_total}`
  const status = need ? NEED_LABEL[need.kind] : progress
  const tooltip = need ? `${build.document_title}. ${need.text}` : `${build.document_title}: running, ${progress} tasks done`
  return (
    <div className="aw-rail-conversation-host aw-rail-build-host">
      <button
        data-slot="rail-row"
        type="button"
        className="aw-rail-row aw-rail-conversation aw-rail-build"
        data-testid={`rail-build-${build.id}`}
        data-active={active ? 'true' : 'false'}
        data-state={build.state}
        data-needs={need?.kind ?? 'none'}
        aria-current={active ? 'page' : undefined}
        title={tooltip}
        onClick={onOpen}
      >
        <Icon name="hammer" size={12} className="aw-rail-build-icon" aria-hidden="true" />
        {/* Two lines: a document title is long, and the status is the reason the row is here. */}
        <span className="min-w-0 flex-1">
          <span className="block truncate">{build.document_title}</span>
          <span className="aw-rail-build-status block truncate">
            {need ? `${status} · ${progress}` : `Running · ${progress}`}
          </span>
        </span>
        {need ? (
          <span className="aw-waiting-dot" role="img" aria-label="Needs you" />
        ) : running ? (
          <span className="aw-live-dot aw-pulse" role="img" aria-label="Running" />
        ) : null}
      </button>
      {/* A running build offers no dismiss: it leaves the list by itself once it ends with
          nothing open (FR-3). */}
      {!running && (
        <button
          data-slot="icon-button"
          type="button"
          className="aw-icon-button aw-rail-build-dismiss"
          data-testid={`rail-build-dismiss-${build.id}`}
          aria-label={`Dismiss ${build.document_title}`}
          title="Dismiss: it comes back if it needs you again"
          onClick={onDismiss}
        >
          <Icon name="close" size={12} />
        </button>
      )}
    </div>
  )
}
