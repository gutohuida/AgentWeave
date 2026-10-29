import * as React from 'react'
import type { EventLogEntry } from '@/api/logs'
import type { AccountingSnapshot } from '@/api/accounting'
import type { Grouping } from '@/api/stats'
import { ActivityDigest } from '@/components/activity/ActivityDigest'
import { WorkView } from '@/components/activity/ProjectWork'
import { Segmented } from '@/components/ui/segmented'
import { buildDigest } from '@/lib/activityDigest'
import logsJson from '../fixtures/logs.json'
import accountingJson from '../fixtures/accounting.json'
import { agents, conversations, tasks } from '../fixtures'
import { NIGHT_TALLY } from '../workFixture'
import type { ScreenProps } from '../routes'
import '@/styles/activity.css'

const logs = logsJson as unknown as EventLogEntry[]
const accounting = accountingJson as unknown as AccountingSnapshot

/** Activity tab. The Ledger/Activity/Logs switch becomes the shared Segmented (it was the one
 *  sub-view control drawn its own way); Ledger and Logs are unchanged in this mock. */
export default function Activity({ go, now }: ScreenProps) {
  const [view, setView] = React.useState<'ledger' | 'activity' | 'logs'>('activity')
  const [grouping, setGrouping] = React.useState<Grouping>('spec')
  const [since, setSince] = React.useState('')
  const days = React.useMemo(
    () =>
      buildDigest(logs, {
        turns: accounting.recent_turns,
        conversationTitle: (id) => conversations.find((c) => c.id === id)?.title ?? null,
        taskTitle: (id) => tasks.find((t) => t.id === id)?.title ?? null,
      }),
    [],
  )
  return (
    <div className="aw-activity-page">
      <div className="aw-activity-head">
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
        <span className="aw-activity-note">The last 200 events</span>
      </div>
      {view === 'ledger' ? (
        <div className="aw-evidence-page">
          <WorkView tally={NIGHT_TALLY} grouping={grouping} onGrouping={setGrouping} since={since} onSince={setSince} />
        </div>
      ) : view === 'activity' ? (
        <ActivityDigest
          days={days}
          agents={agents.map((a) => a.name)}
          colorIndexOf={(name) => agents.find((a) => a.name === name)?.color_index}
          onOpenConversation={(agent, conversationId) => go({ kind: 'conversation', agent, conversationId })}
          now={now}
        />
      ) : (
        <p className="aw-activity-note" style={{ padding: '48px 0', textAlign: 'center' }}>
          The Logs view is unchanged in this mock.
        </p>
      )}
    </div>
  )
}
