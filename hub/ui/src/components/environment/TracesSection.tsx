import { useEffect, useState, type FormEvent } from 'react'
import { format } from 'date-fns'
import { readableApiError } from '@/api/client'
import {
  downloadTraceExport,
  useClearTraces,
  useTraceSettings,
  useTraces,
  useUpdateTraceSettings,
  type TraceSettings,
} from '@/api/traces'
import { Badge } from '@/components/common/Badge'
import { DeleteConfirmDialog } from '@/components/common/DeleteConfirmDialog'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { parseHeaderLines } from '@/components/environment/traceHeaders'
import { TraceButton } from '@/components/traces/TraceDrawer'
import { formatDuration } from '@/components/traces/traceModel'
import { Button } from '@/components/ui/button'
import { hubDate } from '@/lib/hubTime'
import { useConfigStore } from '@/store/configStore'

const DESCRIPTION =
  'Every run is recorded as a trace: its model calls, tool calls, permission decisions and waits. Export them as OTLP, or send them to a collector as they finish.'

const DAY_MS = 24 * 60 * 60 * 1000
const RECENT_LIMIT = 10

function when(value: string | null): string {
  return value ? format(hubDate(value), 'MMM d, yyyy HH:mm') : '—'
}

function rangeSentence(since: string, until: string): string {
  if (since && until) return `recorded from ${since} up to (not including) ${until}`
  if (since) return `recorded from ${since} onward`
  if (until) return `recorded before ${until}`
  return 'this project holds, of every date'
}

function RecentTraces() {
  const [before, setBefore] = useState<string | undefined>(undefined)
  const { data, isLoading, error } = useTraces({ limit: RECENT_LIMIT, before })
  if (isLoading) {
    return <div className="space-y-1.5">{[0, 1, 2].map((row) => <div key={row} className="skeleton h-5 w-80" />)}</div>
  }
  if (error) {
    return (
      <p role="alert" className="text-xs" style={{ color: 'var(--red)' }}>
        {readableApiError(error, 'The traces could not be listed.')}
      </p>
    )
  }
  const traces = data?.traces ?? []
  if (traces.length === 0) {
    return <p className="text-xs" style={{ color: 'var(--text-3)' }}>{before ? 'No older traces.' : 'No traces yet.'}</p>
  }
  return (
    <div className="w-full max-w-[520px]" data-testid="recent-traces">
      <ul className="space-y-0.5">
        {traces.map((trace) => {
          const duration = trace.end_time
            ? formatDuration(Math.max(0, hubDate(trace.end_time).getTime() - hubDate(trace.start_time).getTime()))
            : 'running'
          return (
            <li key={trace.trace_id} className="flex items-center gap-2 text-[11.5px]">
              <span className="w-[104px] shrink-0 tabular-nums" style={{ color: 'var(--text-3)' }}>
                {format(hubDate(trace.start_time), 'MMM d HH:mm:ss')}
              </span>
              <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--text)' }} title={trace.name}>
                {trace.agent ?? trace.name}
                {trace.kind === 'worker' ? <span style={{ color: 'var(--text-3)' }}> · worker</span> : null}
              </span>
              {trace.status === 'error' && <Badge variant="danger">error</Badge>}
              <span className="shrink-0 tabular-nums" style={{ color: 'var(--text-2)' }}>
                {duration} · {trace.span_count}
              </span>
              <TraceButton traceId={trace.trace_id} label="Open" title="Open this trace" testId={`recent-trace-${trace.trace_id}`} />
            </li>
          )
        })}
      </ul>
      <div className="mt-2 flex gap-2">
        {before && (
          <Button type="button" variant="outline" size="xs" onClick={() => setBefore(undefined)}>
            Newest
          </Button>
        )}
        {data?.next_before && (
          <Button type="button" variant="outline" size="xs" onClick={() => setBefore(data.next_before ?? undefined)}>
            Older
          </Button>
        )}
      </div>
    </div>
  )
}

export function TracesSection() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: settings, error: loadError, isLoading } = useTraceSettings()
  const update = useUpdateTraceSettings()
  const clear = useClearTraces()

  const [endpoint, setEndpoint] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [headerText, setHeaderText] = useState('')
  const [headersEdited, setHeadersEdited] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  const resetForm = (from: TraceSettings) => {
    setEndpoint(from.otlp_endpoint ?? '')
    setEnabled(from.export_enabled)
    setHeaderText('')
    setHeadersEdited(false)
  }

  // Seeded once per project, not on every refetch: a background refetch must not wipe an
  // endpoint the operator is halfway through typing. A save re-seeds from what was stored.
  const [seededFor, setSeededFor] = useState<string | null>(null)
  useEffect(() => {
    if (!settings || seededFor === projectId) return
    setEndpoint(settings.otlp_endpoint ?? '')
    setEnabled(settings.export_enabled)
    setHeaderText('')
    setHeadersEdited(false)
    setSeededFor(projectId)
  }, [settings, projectId, seededFor])

  if (loadError && !settings) {
    return (
      <SettingsSection title="Traces" description={DESCRIPTION}>
        <div role="alert" className="py-4 text-xs" style={{ color: 'var(--red)' }}>
          <strong>Trace settings could not be loaded.</strong>
          <p className="mt-1">{readableApiError(loadError, 'The Hub did not return a reason.')}</p>
        </div>
      </SettingsSection>
    )
  }
  if (isLoading || !settings || !projectId) {
    return (
      <SettingsSection title="Traces" description={DESCRIPTION}>
        <div aria-label="Loading trace settings" className="space-y-3 py-4">
          {[0, 1, 2].map((row) => <div key={row} className="skeleton h-[58px] w-full" />)}
        </div>
      </SettingsSection>
    )
  }

  const handleSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormError(null)
    const input: { otlp_endpoint: string | null; export_enabled: boolean; otlp_headers?: Record<string, string> } = {
      otlp_endpoint: endpoint.trim() || null,
      export_enabled: enabled,
    }
    if (headersEdited) {
      const parsed = parseHeaderLines(headerText)
      if ('error' in parsed) {
        setFormError(parsed.error)
        return
      }
      input.otlp_headers = parsed.headers
    }
    update.mutate(input, { onSuccess: (saved) => resetForm(saved) })
  }

  const handleExport = async () => {
    setExporting(true)
    setExportError(null)
    try {
      await downloadTraceExport(projectId, since || undefined, until || undefined)
    } catch (error) {
      setExportError(readableApiError(error, 'The export could not be downloaded.'))
    } finally {
      setExporting(false)
    }
  }

  const lastSevenDays = () => {
    setSince(format(hubDate(Date.now() - 7 * DAY_MS), 'yyyy-MM-dd'))
    setUntil('')
  }

  const rangeInvalid = !!since && !!until && until <= since

  return (
    <SettingsSection
      title="Traces"
      description={DESCRIPTION}
      actions={(
        <Button type="submit" form="trace-settings-form" variant="primary" size="sm" disabled={update.isPending}>
          Save export settings
        </Button>
      )}
    >
      <SettingsRow label="Recorded" description="What this project holds now.">
        <div className="text-xs" style={{ color: 'var(--text-2)' }} data-testid="trace-counts">
          {settings.trace_count.toLocaleString()} trace{settings.trace_count === 1 ? '' : 's'} ·{' '}
          {settings.span_count.toLocaleString()} span{settings.span_count === 1 ? '' : 's'}
          {settings.oldest_trace_at && (
            <div className="mt-0.5" style={{ color: 'var(--text-3)' }}>Oldest {when(settings.oldest_trace_at)}</div>
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="Recent traces" description="The newest runs and background calls. Open one to see its spans.">
        <RecentTraces />
      </SettingsRow>

      <form id="trace-settings-form" onSubmit={handleSave}>
        <SettingsRow
          label="Send to a collector"
          description="Each finished trace is posted to this OTLP/HTTP endpoint. Off, traces are only kept here."
        >
          <input
            className="control-choice"
            aria-label="Send traces to a collector"
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
        </SettingsRow>
        <SettingsRow label="OTLP endpoint" description="For example http://localhost:4318/v1/traces.">
          <input
            aria-label="OTLP endpoint"
            value={endpoint}
            placeholder="Not set"
            onChange={(event) => setEndpoint(event.target.value)}
            className="control-field block w-72 px-2 py-1.5 text-xs"
          />
        </SettingsRow>
        <SettingsRow
          label="Headers"
          description={
            settings.otlp_header_names.length
              ? `Held: ${settings.otlp_header_names.join(', ')}. Values are never shown. Type a new set, one Name=value per line, to replace them all; leave untouched to keep them.`
              : 'One Name=value per line, such as an API key header. Values are stored and never shown again.'
          }
        >
          <textarea
            aria-label="OTLP headers"
            value={headerText}
            rows={3}
            placeholder={
              settings.otlp_header_names.length
                ? settings.otlp_header_names.map((name) => `${name}=••••`).join('\n')
                : 'Authorization=Bearer …'
            }
            onChange={(event) => {
              setHeaderText(event.target.value)
              setHeadersEdited(true)
            }}
            className="control-field block w-72 px-2 py-1.5 text-xs"
            style={{ fontFamily: 'var(--mono)' }}
          />
          {headersEdited && (
            <p className="mt-1 text-[11px]" style={{ color: 'var(--amber)' }}>
              {headerText.trim() ? 'Saving replaces every held header with these.' : 'Saving empty removes every held header.'}{' '}
              <button
                type="button"
                className="aw-link aw-link-inline"
                onClick={() => {
                  setHeaderText('')
                  setHeadersEdited(false)
                }}
              >
                Keep the current ones
              </button>
            </p>
          )}
        </SettingsRow>
        <SettingsRow label="Last export" description="How sending to the collector has gone.">
          <div className="text-xs" style={{ color: 'var(--text-2)' }} data-testid="trace-export-status">
            {settings.last_export_at ? when(settings.last_export_at) : 'Never'} ·{' '}
            {settings.exported_spans.toLocaleString()} span{settings.exported_spans === 1 ? '' : 's'} sent
            {settings.last_error && (
              <p role="alert" className="mt-1 max-w-72" style={{ color: 'var(--red)' }}>{settings.last_error}</p>
            )}
          </div>
        </SettingsRow>
        {update.isSuccess && <div role="status" className="py-3 text-xs" style={{ color: 'var(--green)' }}>Export settings saved.</div>}
        {(formError || update.error) && (
          <div role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
            {formError ?? readableApiError(update.error, 'The export settings could not be saved.')}
          </div>
        )}
      </form>

      <SettingsRow
        label="Date range"
        description="Used by Download and Clear. Leave both empty for everything; the second date is not included."
      >
        <div className="flex flex-wrap items-center gap-2">
          <input
            aria-label="Traces from"
            type="date"
            value={since}
            onChange={(event) => setSince(event.target.value)}
            className="control-field block px-2 py-1.5 text-xs"
          />
          <span className="text-xs" style={{ color: 'var(--text-3)' }}>to before</span>
          <input
            aria-label="Traces before"
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            className="control-field block px-2 py-1.5 text-xs"
          />
          <Button type="button" variant="ghost" size="xs" onClick={lastSevenDays}>Last 7 days</Button>
          {(since || until) && (
            <Button type="button" variant="ghost" size="xs" onClick={() => { setSince(''); setUntil('') }}>All</Button>
          )}
        </div>
        {rangeInvalid && (
          <p className="mt-1 text-[11px]" style={{ color: 'var(--amber)' }}>The second date must be after the first.</p>
        )}
      </SettingsRow>
      <SettingsRow label="Download" description="The traces in the range, as one OTLP JSON file any OpenTelemetry tool can read.">
        <div>
          <Button type="button" variant="outline" size="sm" disabled={exporting || rangeInvalid} onClick={() => { void handleExport() }}>
            {exporting ? 'Preparing…' : 'Download OTLP JSON'}
          </Button>
          {exportError && <p role="alert" className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>{exportError}</p>}
        </div>
      </SettingsRow>
      <SettingsRow label="Clear" description="Deletes the traces in the range from this Hub. Nothing already sent to a collector is touched.">
        <div>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={rangeInvalid || clear.isPending}
            onClick={() => {
              clear.reset()
              setConfirmClear(true)
            }}
          >
            Clear traces…
          </Button>
          {clear.isSuccess && !confirmClear && (
            <p role="status" className="mt-1 text-[11px]" style={{ color: 'var(--green)' }}>
              Cleared {clear.data.deleted_traces.toLocaleString()} trace{clear.data.deleted_traces === 1 ? '' : 's'} (
              {clear.data.deleted_spans.toLocaleString()} span{clear.data.deleted_spans === 1 ? '' : 's'}).
            </p>
          )}
        </div>
      </SettingsRow>

      {confirmClear && (
        <DeleteConfirmDialog
          heading="Clear traces?"
          body={`Every trace ${rangeSentence(since, until)} is deleted${
            !since && !until ? ` — ${settings.trace_count.toLocaleString()} traces, ${settings.span_count.toLocaleString()} spans` : ''
          }.`}
          confirmLabel="Clear traces"
          isPending={clear.isPending}
          error={clear.error ? readableApiError(clear.error, 'The traces could not be cleared.') : null}
          onCancel={() => setConfirmClear(false)}
          onConfirm={() =>
            clear.mutate(
              { since: since || undefined, until: until || undefined },
              { onSuccess: () => setConfirmClear(false) },
            )
          }
        />
      )}
    </SettingsSection>
  )
}
