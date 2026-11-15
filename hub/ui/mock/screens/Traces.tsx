import { TracesPage } from '@/components/traces/TracesPage'
import { Segmented } from '@/components/ui/segmented'
import type { ScreenProps } from '../routes'
import '@/styles/activity.css'

/** The page fetches through the app's own hooks (`useTraces`, `useTraceTotals`), so with no Hub behind
 *  the mock it shows what the app shows with nothing recorded. The recorded-rows version drove a
 *  presentational page that no longer exists; seed the hooks' query keys here to bring rows back. */
export default function Traces({ go }: ScreenProps) {
  return (
    <div className="aw-activity-page">
      <div className="aw-activity-head">
        <Segmented
          label="Activity view"
          value={'traces' as string}
          onChange={(v) => (v === 'traces' ? undefined : go({ kind: 'tab', tab: 'activity' }))}
          options={[
            { value: 'ledger', label: 'Ledger' },
            { value: 'activity', label: 'Activity' },
            { value: 'logs', label: 'Logs' },
            { value: 'traces', label: 'Traces' },
          ]}
        />
      </div>
      <TracesPage />
    </div>
  )
}
