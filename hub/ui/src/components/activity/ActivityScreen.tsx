import * as React from 'react'
import { useAccounting } from '@/api/accounting'
import { conversationLabel, useProjectConversations } from '@/api/agentChat'
import { useAgents } from '@/api/agents'
import { useLogs } from '@/api/logs'
import { useTasks } from '@/api/tasks'
import { Icon } from '@/components/common/Icon'
import { QueryErrorNotice } from '@/components/common/QueryErrorNotice'
import { LogsView } from '@/components/logs/LogsView'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { buildDigest } from '@/lib/activityDigest'
import { formatCount } from '@/lib/format'
import { useConfigStore } from '@/store/configStore'
import { ActivityDigest } from './ActivityDigest'
import { ProjectLedger } from './ProjectLedger'
import '@/styles/activity.css'

export type ActivityView = 'ledger' | 'activity' | 'logs'

/** How many log entries the digest reads per page; "Show earlier" asks for the page before. */
const DIGEST_PAGE = 200

/** The Activity tab, wired: Ledger (what the project did), Activity (the digest: one sentence per
 *  thing that happened, live) and Logs (the raw, filterable, pausable stream). One Segmented, as
 *  every other view switch. The Ledger leads (F718); `initialView` lets the palette open Logs. */
export function ActivityScreen({
  onOpenTask,
  onOpenConversation,
  initialView = 'ledger',
}: {
  onOpenTask: (taskId: string) => void
  onOpenConversation?: (agent: string, conversationId: string) => void
  initialView?: ActivityView
}) {
  const [view, setView] = React.useState<ActivityView>(initialView)
  // A new `initialView` (the palette's "logs") is a request to show it, even while mounted.
  const [requested, setRequested] = React.useState(initialView)
  if (requested !== initialView) {
    setRequested(initialView)
    setView(initialView)
  }

  return (
    <div className="aw-activity-screen">
      <div className="aw-activity-head aw-activity-bar">
        <Segmented
          label="Activity view"
          value={view}
          onChange={setView}
          options={[
            { value: 'ledger', label: 'Ledger' },
            { value: 'activity', label: 'Activity' },
            { value: 'logs', label: 'Logs' },
          ]}
        />
      </div>
      <div className="aw-activity-body" data-view={view}>
        {view === 'ledger' ? (
          <ProjectLedger onOpenTask={onOpenTask} />
        ) : view === 'activity' ? (
          <LiveDigest onOpenConversation={onOpenConversation} />
        ) : (
          <LogsView />
        )}
      </div>
    </div>
  )
}

/** The digest over the project's own log (`useLogs` is project-scoped by the route, so another
 *  project's events cannot reach it — F419), refreshed as events arrive. */
function LiveDigest({ onOpenConversation }: { onOpenConversation?: (agent: string, conversationId: string) => void }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const logs = useLogs({ limit: DIGEST_PAGE, live: true })
  const { data: accounting, error: accountingError } = useAccounting()
  const { data: agents = [], error: agentsError } = useAgents()
  const { data: conversationPage, error: conversationsError } = useProjectConversations(projectId || null)
  const { data: taskPage, error: tasksError } = useTasks()
  const now = new Date()

  const days = React.useMemo(() => {
    const conversations = conversationPage?.conversations ?? []
    const tasks = taskPage?.tasks ?? []
    return buildDigest(logs.data ?? [], {
      turns: accounting?.recent_turns,
      conversationTitle: (id) => {
        const c = conversations.find((x) => x.id === id)
        return c ? conversationLabel(c) : null
      },
      taskTitle: (id) => tasks.find((t) => t.id === id)?.title ?? null,
    })
  }, [logs.data, accounting, conversationPage, taskPage])

  if (logs.isLoading) {
    return (
      <div className="aw-activity-col aw-delayed" aria-label="Loading activity">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton mb-3 h-8 w-full" aria-hidden="true" />
        ))}
      </div>
    )
  }
  if (logs.error) {
    return (
      <div className="aw-activity-col">
        <p className="aw-activity-error" role="alert">
          <Icon name="error_outline" size={14} /> The project's log could not be read: {logs.error instanceof Error ? logs.error.message : 'the Hub did not answer.'}
        </p>
      </div>
    )
  }
  return (
    <div className="aw-activity-col">
      {/* The digest names turns, conversations and tasks from these; a failed one would leave its
          sentences unnamed with nothing saying why. */}
      <QueryErrorNotice
        failures={[
          ['the turns', accountingError],
          ['the agents', agentsError],
          ['the conversations', conversationsError],
          ['the tasks', tasksError],
        ]}
      />
      <p className="aw-activity-note aw-activity-count">
        The last {formatCount(logs.data?.length ?? 0)} events · updates as they happen
      </p>
      <ActivityDigest
        days={days}
        agents={agents.map((a) => a.name)}
        colorIndexOf={(name) => agents.find((a) => a.name === name)?.color_index}
        onOpenConversation={onOpenConversation}
        now={now}
      />
      {logs.hasOlder ? (
        <div className="aw-activity-older">
          <Button variant="outline" size="sm" disabled={logs.isLoadingOlder} onClick={() => void logs.loadOlder()}>
            {logs.isLoadingOlder ? 'Loading…' : 'Show earlier events'}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
