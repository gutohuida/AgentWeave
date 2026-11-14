import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { useDashboardRun, useDashboards, useDeleteDashboard, useUndoDashboard } from '@/api/dashboards'
import { askToChangeLine } from '@/lib/askToChange'
import { setComposerDraft } from '@/lib/composerDrafts'
import { goTo, newConversationDestination } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { toast } from '@/lib/toast'
import { DashboardsView } from './DashboardsView'

/** The Dashboards tab, fed from the Hub. Opening a dashboard runs its queries (`GET .../run`);
 *  Refresh runs them again. The list and an open dashboard refresh on `dashboard_saved`,
 *  `dashboard_edited` and `dashboard_deleted`. */
export function DashboardsScreen() {
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const list = useDashboards()
  const run = useDashboardRun(selectedId)
  const remove = useDeleteDashboard()
  const undo = useUndoDashboard()
  const agents = useAgents()
  const { selectedProjectId: projectId } = useConfigStore()
  const dashboards = list.data ?? []

  // A dashboard deleted elsewhere while it is open: back to the list.
  React.useEffect(() => {
    if (selectedId && list.data && !list.data.some((d) => d.id === selectedId)) setSelectedId(null)
  }, [selectedId, list.data])

  const error = list.error
    ? readableApiError(list.error, 'The dashboards could not be read.')
    : run.error
      ? readableApiError(run.error, 'The dashboard could not be run.')
      : null

  return (
    <DashboardsView
      dashboards={dashboards}
      selectedId={selectedId}
      run={run.data ?? null}
      refreshing={run.isFetching}
      error={error}
      onSelect={setSelectedId}
      onRefresh={() => void run.refetch()}
      undoing={undo.isPending}
      onUndo={(d) =>
        undo.mutate(d.id, {
          onSuccess: () => toast({ title: `Restored the earlier version of ${d.name}`, tone: 'success' }),
          onError: (e) => toast({ title: 'Could not undo', description: readableApiError(e, 'Try again.'), tone: 'error' }),
        })
      }
      agents={(agents.data ?? []).map((a) => a.name)}
      onAskToChange={(d, agent) => {
        if (!projectId) return
        // A draft, not a send: the composer opens holding the line, and only the operator sends it.
        setComposerDraft(projectId, agent, null, askToChangeLine(d.name, d.id))
        goTo(newConversationDestination(projectId, agent))
      }}
      onDelete={(d) =>
        remove.mutate(d.id, {
          onSuccess: () => {
            setSelectedId(null)
            toast({ title: `Deleted ${d.name}`, tone: 'success' })
          },
          onError: (e) => toast({ title: 'Could not delete', description: readableApiError(e, 'Try again.'), tone: 'error' }),
        })
      }
    />
  )
}
