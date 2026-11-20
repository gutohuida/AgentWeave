import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import type { AgentConversation } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Input } from '@/components/ui/input'
import { agentColorVars } from '@/lib/agentColors'
import { formatCount } from '@/lib/format'
import { ConversationRow } from './ConversationRow'
import {
  THREADS_DISPLAY_CAP,
  buildAccessibleName,
  buildStatusWord,
  filterThreads,
  holdOrder,
  orderBuilds,
  orderThreads,
  type ListState,
  type SidebarBuild,
} from './threadsAndBuildsModel'

interface ThreadsAndBuildsProps {
  projectId: string
  profiles: ProjectAgentSummary[]
  /** The operator's threads, in the order the route returns them (newest activity first). */
  threads: AgentConversation[]
  threadsState: ListState
  archivedCount: number
  /** Fetched only once the operator asks for them; null until then. */
  archivedThreads: AgentConversation[] | null
  /** Running builds and those needing the operator, not dismissed, in the route's order. */
  builds: SidebarBuild[]
  buildsState: ListState
  activeProject: boolean
  activeConversation: string | null
  activeBuild: string | null
  onOpenThread: (projectId: string, profile: string, conversationId: string) => void
  /** No profile is implied here; the new-thread surface asks which one. */
  onNewThread: (projectId: string) => void
  onOpenBuild: (projectId: string, buildId: string) => void
  onDismissBuild: (projectId: string, buildId: string) => void
  onShowArchived: (projectId: string, show: boolean) => void
  onRetry: (projectId: string, list: 'threads' | 'builds') => void
}

type Section = 'builds' | 'threads'
const SECTIONS_KEY = 'aw.railSectionsCollapsed'

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(SECTIONS_KEY) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

/**
 * A project's part of the sidebar: the builds that are running or need the operator, then the
 * operator's own threads, each labelled with its profile.
 *
 * Replaces the agent tree and the recent-conversations view (profiles-threads-and-builds-everywhere
 * FR-1, FR-3). Task, review and mender runs are not here: they are reached through their build. Built
 * against the vault's UI note (src-0b85ea5a1d1d): what needs the operator rises, status is a word or
 * a shape as well as a colour, rows hold still under the pointer, and arrow keys move between rows.
 */
export function ThreadsAndBuilds({
  projectId,
  profiles,
  threads,
  threadsState,
  archivedCount,
  archivedThreads,
  builds,
  buildsState,
  activeProject,
  activeConversation,
  activeBuild,
  onOpenThread,
  onNewThread,
  onOpenBuild,
  onDismissBuild,
  onShowArchived,
  onRetry,
}: ThreadsAndBuildsProps) {
  const [showAll, setShowAll] = useState(false)
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed)
  const rootRef = useRef<HTMLDivElement>(null)

  // Rows hold their places while the pointer is over the list; the new order lands when it leaves.
  const [hovered, setHovered] = useState(false)
  const shownThreads = useRef<string[]>([])
  const shownBuilds = useRef<string[]>([])
  const orderedThreads = useMemo(() => orderThreads(threads), [threads])
  const orderedBuilds = useMemo(() => orderBuilds(builds), [builds])
  const threadList = hovered ? holdOrder(shownThreads.current, orderedThreads) : orderedThreads
  const buildList = hovered ? holdOrder(shownBuilds.current, orderedBuilds) : orderedBuilds
  useEffect(() => {
    shownThreads.current = threadList.map((t) => t.id)
    shownBuilds.current = buildList.map((b) => b.id)
  })

  useEffect(() => {
    try {
      localStorage.setItem(SECTIONS_KEY, JSON.stringify(collapsed))
    } catch {
      // Persistence is optional.
    }
  }, [collapsed])

  const isCollapsed = (section: Section) => Boolean(collapsed[`${projectId}/${section}`])
  const toggle = (section: Section) =>
    setCollapsed((state) => ({ ...state, [`${projectId}/${section}`]: !state[`${projectId}/${section}`] }))

  const filterable = threads.length > THREADS_DISPLAY_CAP
  const matched = filterThreads(threadList, filterable ? query : '')
  const filtering = filterable && query.trim() !== ''
  const visible = showAll || filtering ? matched : matched.slice(0, THREADS_DISPLAY_CAP)
  const hidden = matched.length - visible.length

  const colorFor = (name: string) =>
    agentColorVars(profiles.find((p) => p.name === name)?.color_index ?? null).accent

  /** Up and down move between the rows of this project's list; Home and End jump to its ends. */
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const rows = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[data-rail-nav], button.aw-rail-conversation') ?? [])
    const at = rows.indexOf(document.activeElement as HTMLElement)
    if (at === -1 && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : Math.min(rows.length - 1, Math.max(0, at + (event.key === 'ArrowDown' ? 1 : -1)))
    rows[next]?.focus()
  }

  const dismiss = (build: SidebarBuild) => {
    onDismissBuild(projectId, build.id)
    // Focus stays in the list instead of falling to the page: the Builds header is always there.
    requestAnimationFrame(() => rootRef.current?.querySelector<HTMLElement>(`[data-section-head="builds"]`)?.focus())
  }

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

  const needCount = builds.filter((b) => b.needs_operator).length
  const showBuilds = buildsState !== 'ready' || builds.length > 0

  return (
    <div
      ref={rootRef}
      className="aw-rail-children aw-rail-tb"
      data-testid={`rail-threads-builds-${projectId}`}
      onKeyDown={onKeyDown}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      {showBuilds && (
        <section aria-label="Builds" data-testid={`rail-builds-${projectId}`}>
          <SectionHead
            section="builds"
            label="Builds"
            count={buildsState === 'ready' ? builds.length : null}
            note={needCount > 0 ? `${formatCount(needCount)} need${needCount === 1 ? 's' : ''} you` : null}
            collapsed={isCollapsed('builds')}
            onToggle={() => toggle('builds')}
          />
          {!isCollapsed('builds') && (
            <>
              {buildsState === 'loading' && <LoadingThread size="inline" label="Loading builds" />}
              {buildsState === 'error' && (
                <ListError what="builds" onRetry={() => onRetry(projectId, 'builds')} testId={`rail-builds-error-${projectId}`} />
              )}
              {buildsState === 'ready' &&
                buildList.map((build) => (
                  <BuildRow
                    key={build.id}
                    build={build}
                    active={activeProject && activeBuild === build.id}
                    onOpen={() => onOpenBuild(projectId, build.id)}
                    onDismiss={() => dismiss(build)}
                  />
                ))}
            </>
          )}
        </section>
      )}

      <section aria-label="Threads" data-testid={`rail-threads-${projectId}`}>
        <SectionHead
          section="threads"
          label="Threads"
          count={threadsState === 'ready' ? threads.length : null}
          note={null}
          collapsed={isCollapsed('threads')}
          onToggle={() => toggle('threads')}
          action={
            threadsState === 'ready' && threads.length > 0 ? (
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
            ) : null
          }
        />

        {!isCollapsed('threads') && (
          <>
            {threadsState === 'loading' && <LoadingThread size="inline" label="Loading threads" />}
            {threadsState === 'error' && (
              <ListError what="threads" onRetry={() => onRetry(projectId, 'threads')} testId={`rail-threads-error-${projectId}`} />
            )}

            {threadsState === 'ready' && filterable && (
              <div className="aw-rail-filter">
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') setQuery('')
                  }}
                  placeholder="Filter threads"
                  aria-label="Filter threads"
                  data-testid={`rail-threads-filter-${projectId}`}
                />
              </div>
            )}

            {threadsState === 'ready' && visible.map((conversation) => row(conversation, `rail-thread-${conversation.id}`))}

            {threadsState === 'ready' && filtering && matched.length === 0 && (
              <p className="aw-rail-note" data-testid={`rail-threads-no-match-${projectId}`}>
                No thread matches “{query.trim()}”.{' '}
                <button data-slot="rail-link" type="button" className="aw-rail-link" onClick={() => setQuery('')}>
                  Clear the filter
                </button>
              </p>
            )}

            {threadsState === 'ready' && !filtering && (hidden > 0 || showAll) && (
              <button
                data-slot="rail-more"
                type="button"
                className="aw-rail-more"
                data-testid={`rail-threads-more-${projectId}`}
                aria-expanded={showAll}
                onClick={() => setShowAll((value) => !value)}
              >
                {showAll ? 'Show fewer' : `Show ${formatCount(hidden)} more`}
              </button>
            )}

            {threadsState === 'ready' && threads.length === 0 && (
              <button
                data-slot="rail-empty"
                type="button"
                className="aw-rail-empty"
                data-testid={`rail-threads-empty-${projectId}`}
                data-rail-nav=""
                onClick={() => onNewThread(projectId)}
              >
                <Icon name="add" size={13} />
                Start a thread
              </button>
            )}

            {threadsState === 'ready' && archivedCount > 0 && (
              <button
                data-slot="rail-more"
                type="button"
                className="aw-rail-more"
                data-testid={`rail-threads-archived-${projectId}`}
                aria-expanded={archivedThreads !== null}
                onClick={() => onShowArchived(projectId, archivedThreads === null)}
              >
                {archivedThreads !== null ? 'Hide archived' : `Show archived (${formatCount(archivedCount)})`}
              </button>
            )}
            {archivedThreads?.map((conversation) => row(conversation, `rail-thread-archived-${conversation.id}`))}
          </>
        )}
      </section>
    </div>
  )
}

/** A section's header: a disclosure naming the section and its count, plus one optional action. */
function SectionHead({
  section,
  label,
  count,
  note,
  collapsed,
  onToggle,
  action,
}: {
  section: Section
  label: string
  /** Null while the list is loading or failed: an unknown count is not shown as zero. */
  count: number | null
  note: string | null
  collapsed: boolean
  onToggle: () => void
  action?: ReactNode
}) {
  return (
    <div className="aw-rail-section-head">
      <button
        data-slot="rail-section"
        type="button"
        className="aw-rail-section-toggle"
        data-section-head={section}
        data-rail-nav=""
        aria-expanded={!collapsed}
        onClick={onToggle}
      >
        <span className="aw-rail-chevron" data-open={collapsed ? 'false' : 'true'}>
          <Icon name="chevron_right" size={11} />
        </span>
        <span>{label}</span>
        {count !== null && <span className="aw-rail-section-count tabular">{formatCount(count)}</span>}
        {note && (
          <span className="aw-rail-section-note">
            <Icon name="hand" size={10} aria-hidden="true" />
            {note}
          </span>
        )}
      </button>
      {action}
    </div>
  )
}

/** One build on one line: its document's title and one status word. A build that needs the
 *  operator says why in amber, with a hand; a running one shows its progress beside a pulse. */
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
  return (
    <div className="aw-rail-conversation-host aw-rail-build-host">
      <button
        data-slot="rail-row"
        type="button"
        className="aw-rail-row aw-rail-conversation aw-rail-build"
        data-testid={`rail-build-${build.id}`}
        data-rail-nav=""
        data-active={active ? 'true' : 'false'}
        data-state={build.state}
        data-needs={need?.kind ?? 'none'}
        aria-current={active ? 'page' : undefined}
        aria-label={buildAccessibleName(build)}
        title={need ? `${build.document_title}\n${need.text}` : `${build.document_title}\n${build.tasks_done} of ${build.tasks_total} tasks done`}
        onClick={onOpen}
      >
        <Icon name={need ? 'hand' : 'hammer'} size={12} className="aw-rail-build-icon" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">{build.document_title}</span>
        <span className="aw-rail-build-status tabular">{buildStatusWord(build)}</span>
        {!need && running ? <span className="aw-live-dot aw-pulse" aria-hidden="true" /> : null}
      </button>
      {/* A running build offers no dismiss: it leaves the list by itself once it ends with
          nothing open (FR-3). A dismissed build comes back when it needs the operator anew. */}
      {!running && (
        <button
          data-slot="icon-button"
          type="button"
          className="aw-icon-button aw-rail-build-dismiss"
          data-testid={`rail-build-dismiss-${build.id}`}
          aria-label={`Dismiss build: ${build.document_title}`}
          title="Dismiss. It comes back if it needs you again."
          onClick={onDismiss}
        >
          <Icon name="close" size={12} />
        </button>
      )}
    </div>
  )
}

function ListError({ what, onRetry, testId }: { what: string; onRetry: () => void; testId: string }) {
  return (
    <p className="aw-rail-note aw-rail-note-error" role="alert" data-testid={testId}>
      <Icon name="error_outline" size={12} aria-hidden="true" />
      Couldn’t load {what}.{' '}
      <button data-slot="rail-link" type="button" className="aw-rail-link" data-rail-nav="" onClick={onRetry}>
        Try again
      </button>
    </p>
  )
}
