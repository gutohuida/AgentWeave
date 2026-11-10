import { useState } from 'react'
import { readableApiError } from '@/api/client'
import { downloadTraceExport, useClearTraces, useTraceSettings, useUpdateTraceSettings } from '@/api/traces'
import { DeleteConfirmDialog } from '@/components/common/DeleteConfirmDialog'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { TracesSettings, type TraceRange } from '../TracesSettings'

const HEADING = { icon: 'timeline', title: 'Traces', description: 'Every run is recorded as a trace: its model calls, tool calls, permission decisions and waits, and what the Hub did around them.' }

const DAY_MS = 24 * 60 * 60 * 1000
const SPAN_MS: Record<TraceRange, number | null> = { day: DAY_MS, week: 7 * DAY_MS, month: 30 * DAY_MS, all: null }
const RANGE_WORDS: Record<TraceRange, string> = {
  day: 'from the last 24 hours',
  week: 'from the last 7 days',
  month: 'from the last 30 days',
  all: 'of every date',
}

/** The instant a range starts at, as the Hub's `since` (an ISO datetime); none for all of them. */
function sinceFor(range: TraceRange): string | undefined {
  const span = SPAN_MS[range]
  return span === null ? undefined : new Date(Date.now() - span).toISOString()
}

/** Project settings → Traces, on the Hub. Retention, the collector switch and the endpoint apply
 *  on change; headers are replaced through the dialog; download and clear act on the chosen span,
 *  and clearing is confirmed first. */
export function TracesSection({ onOpenTraces }: { onOpenTraces?: () => void } = {}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: settings, error, refetch } = useTraceSettings()
  const update = useUpdateTraceSettings()
  const clear = useClearTraces()
  const [range, setRange] = useState<TraceRange>('week')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  if (error && !settings) {
    return (
      <SettingsPage {...HEADING}>
        <SettingsNotice tone="error" title="Trace settings could not be loaded." action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (!settings || !projectId) {
    return (
      <SettingsPage {...HEADING}>
        <SettingsLoading label="Loading trace settings" rows={4} />
      </SettingsPage>
    )
  }

  const download = async () => {
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadTraceExport(projectId, sinceFor(range))
    } catch (err) {
      setDownloadError(readableApiError(err, 'The export could not be downloaded.'))
    } finally {
      setDownloading(false)
    }
  }

  const notices = (
    <>
      {update.isError ? (
        <SettingsNotice tone="error" title="That change was not saved." testId="trace-settings-refusal">
          <p>{readableApiError(update.error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      ) : null}
      {downloadError ? (
        <SettingsNotice tone="error" title="The export could not be downloaded.">
          <p>{downloadError}</p>
        </SettingsNotice>
      ) : null}
    </>
  )

  return (
    <>
      <TracesSettings
        settings={settings}
        now={new Date()}
        range={range}
        notices={notices}
        downloading={downloading}
        onRangeChange={setRange}
        onOpenTraces={onOpenTraces}
        onDownload={() => void download()}
        onClear={() => {
          clear.reset()
          setConfirmClear(true)
        }}
        onChange={(input, said) => {
          update.reset()
          update.mutate(input, {
            onSuccess: () => toast({ title: said, tone: 'success' }),
            onError: (err) => toast({ title: 'Not saved', description: readableApiError(err, 'The settings could not be saved.'), tone: 'error' }),
          })
        }}
      />
      {confirmClear ? (
        <DeleteConfirmDialog
          heading="Clear traces?"
          body={`Every trace ${RANGE_WORDS[range]} is deleted${range === 'all' ? ` — ${settings.trace_count.toLocaleString()} traces, ${settings.span_count.toLocaleString()} spans` : ''}.`}
          confirmLabel="Clear traces"
          isPending={clear.isPending}
          error={clear.error ? readableApiError(clear.error, 'The traces could not be cleared.') : null}
          onCancel={() => setConfirmClear(false)}
          onConfirm={() =>
            clear.mutate(
              { since: sinceFor(range) },
              {
                onSuccess: (done) => {
                  setConfirmClear(false)
                  toast({ title: `Cleared ${done.deleted_traces.toLocaleString()} traces`, description: `${done.deleted_spans.toLocaleString()} spans`, tone: 'success' })
                },
              },
            )
          }
        />
      ) : null}
    </>
  )
}
