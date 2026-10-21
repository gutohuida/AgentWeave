import { readableApiError } from '@/api/client'
import { useStatus } from '@/api/status'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { formatCount } from '@/lib/format'
import { toast } from '@/lib/toast'
import { DiagnosticsSettings } from '../OtherSettings'

const TASK_STATE_WORDS: Record<string, string> = {
  pending: 'waiting to be assigned',
  assigned: 'assigned',
  in_progress: 'in progress',
  completed: 'completed, awaiting review',
  under_review: 'under review',
  approved: 'approved',
  revision_needed: 'sent back for revision',
  rejected: 'rejected',
}

/** Project settings → Diagnostics: the Hub's live status, in words, with the raw answer beneath
 *  for an issue report. Read defensively: an older Hub may omit a count, and diagnostics is the
 *  last page that should fail to render. */
export function DiagnosticsSection() {
  const { data, isLoading, error, refetch } = useStatus()
  // A failed read is said, with a Retry: never a skeleton that waits for an answer that is not
  // coming, and never rows that could be saved over settings that were never read.
  if (error && !data) {
    return (
      <SettingsPage icon="monitoring" title="Diagnostics" description="What the Hub reports about this project right now, for troubleshooting.">
        <SettingsNotice tone="error" title="The Hub's status could not be read." action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (isLoading || !data) {
    return (
      <SettingsPage icon="monitoring" title="Diagnostics" description="What the Hub reports about this project right now, for troubleshooting.">
        <SettingsLoading label="Loading diagnostics" rows={3} />
      </SettingsPage>
    )
  }
  const raw = JSON.stringify(data, null, 2)
  return (
    <DiagnosticsSettings
      rawStatus={raw}
      onCopy={(text) => {
        void navigator.clipboard?.writeText(text)
        toast({ title: 'Status copied', tone: 'success' })
      }}
      groups={[
        {
          title: 'Project',
          lines: [
            { label: 'Name', value: data.project_name },
            { label: 'Project id', value: <span className="font-mono text-[12px]">{data.project_id}</span> },
            { label: 'Agents working now', value: data.agents_active?.length ? data.agents_active.join(', ') : 'None' },
          ],
        },
        {
          title: 'Work',
          lines: [
            ...Object.entries(data.task_counts ?? {}).map(([state, n]) => ({
              label: `Tasks ${TASK_STATE_WORDS[state] ?? state.replace(/_/g, ' ')}`,
              value: formatCount(n),
            })),
            { label: 'Messages waiting to be delivered', value: formatCount(data.message_counts?.pending ?? 0) },
            { label: 'Messages, all time', value: formatCount(data.message_counts?.total ?? 0) },
            { label: 'Questions waiting for you', value: formatCount(data.question_counts?.unanswered ?? 0) },
          ],
        },
      ]}
    />
  )
}
