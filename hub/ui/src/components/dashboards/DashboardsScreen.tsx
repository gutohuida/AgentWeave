import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useDashboardRun, useDashboards, useDeleteDashboard } from '@/api/dashboards'
import { toast } from '@/lib/toast'
import { DashboardsView } from './DashboardsView'

/** The Dashboards tab, fed from the Hub. Opening a dashboard runs its queries (`GET .../run`);
 *  Refresh runs them again. The list refreshes on `dashboard_saved` and `dashboard_deleted`. */
export function DashboardsScreen() {
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const list = useDashboards()
  const run = useDashboardRun(selectedId)
  const remove = useDeleteDashboard()
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
