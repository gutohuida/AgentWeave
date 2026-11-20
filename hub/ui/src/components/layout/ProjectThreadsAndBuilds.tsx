import { useState } from 'react'
import { useOperatorThreads } from '@/api/agentChat'
import type { ProjectSummary } from '@/api/projects'
import { useBuildsOfProject, useDismissProjectBuild } from '@/api/projectBuilds'
import { ThreadsAndBuilds } from './ThreadsAndBuilds'
import { sidebarBuilds, type ListState } from './threadsAndBuildsModel'

/** A query's place in the list: rows once it has any, an error only when it has none to show, and
 *  loading otherwise. A failed refetch keeps the rows it already had rather than blanking them. */
function listState(query: { data: unknown; isError: boolean }): ListState {
  if (query.data !== undefined) return 'ready'
  return query.isError ? 'error' : 'loading'
}

interface ProjectThreadsAndBuildsProps {
  project: ProjectSummary
  activeProject: boolean
  activeConversation: string | null
  activeBuild: string | null
  onOpenThread: (projectId: string, profile: string, conversationId: string) => void
  onNewThread: (projectId: string) => void
  onOpenBuild: (projectId: string, buildId: string) => void
}

/**
 * One project's threads and builds, fed from the Hub: the operator's threads from
 * `operator_threads=true` (D1) and the builds from `GET /builds` with `needs_operator` and
 * `attention_dismissed` (D2), dismissed through D3's route.
 */
export function ProjectThreadsAndBuilds({
  project,
  activeProject,
  activeConversation,
  activeBuild,
  onOpenThread,
  onNewThread,
  onOpenBuild,
}: ProjectThreadsAndBuildsProps) {
  const [showArchived, setShowArchived] = useState(false)
  const threads = useOperatorThreads(project.id)
  const archived = useOperatorThreads(project.id, 'archived', showArchived)
  const builds = useBuildsOfProject(project.id)
  const dismiss = useDismissProjectBuild()

  return (
    <ThreadsAndBuilds
      projectId={project.id}
      profiles={project.agents}
      threads={threads.data?.conversations ?? []}
      threadsState={listState(threads)}
      archivedCount={threads.data?.archived_count ?? 0}
      archivedThreads={showArchived ? (archived.data?.conversations ?? []) : null}
      builds={sidebarBuilds(builds.data ?? [])}
      buildsState={listState(builds)}
      activeProject={activeProject}
      activeConversation={activeConversation}
      activeBuild={activeBuild}
      onOpenThread={onOpenThread}
      onNewThread={onNewThread}
      onOpenBuild={onOpenBuild}
      onDismissBuild={(projectId, buildId) =>
        // A refusal (the build started running again) leaves the list to the refetch it triggers.
        dismiss.mutate({ projectId, buildId }, { onError: () => void builds.refetch() })
      }
      onShowArchived={(_, show) => setShowArchived(show)}
      onRetry={(_, list) => void (list === 'threads' ? threads.refetch() : builds.refetch())}
    />
  )
}
