import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Field, SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import type { TraceSettings, TraceSettingsInput } from '@/api/traces'
import { parseHeaderLines } from '@/components/environment/traceHeaders'
import { formatCount, formatDateTime } from '@/lib/format'
import { CommittedInput } from './CommittedInput'
import { wholeNumber } from './settingsOptions'

/**
 * Project settings → Traces (`settings-in-the-app-s-style-where-you-expect-them`; what each row
 * does is unchanged). Every setting applies on change; the header values, which are write-only,
 * are replaced through a dialog, and Download and Clear are actions on a chosen span of time.
 */

export type TraceRange = 'day' | 'week' | 'month' | 'all'

const RANGE_WORDS: Record<TraceRange, string> = {
  day: 'from the last 24 hours',
  week: 'from the last 7 days',
  month: 'from the last 30 days',
  all: 'this project holds, of every date',
}

function plural(n: number, word: string): string {
  return `${formatCount(n)} ${word}${n === 1 ? '' : 's'}`
}

function HeadersDialog({
  open,
  held,
  onOpenChange,
  onReplace,
}: {
  open: boolean
  held: string[]
  onOpenChange: (open: boolean) => void
  onReplace: (headers: Record<string, string>) => void
}) {
  const [text, setText] = React.useState('')
  React.useEffect(() => {
    if (open) setText('')
  }, [open])
  const parsed = text.trim() ? parseHeaderLines(text) : { headers: {} as Record<string, string> }
  const error = 'error' in parsed ? parsed.error : undefined
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={held.length ? 'Replace the headers' : 'Add headers'}
        description="One Name=value per line. Values are stored and never shown again."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={Boolean(error) || !text.trim()} onClick={() => 'headers' in parsed && onReplace(parsed.headers)}>
              {held.length ? 'Replace headers' : 'Add headers'}
            </Button>
          </>
        }
      >
        <Field label="Headers" htmlFor="otlp-headers" error={error}>
          <Textarea id="otlp-headers" className="font-mono aw-textarea-grow" rows={3} value={text} placeholder="Authorization=Bearer …" onChange={(e) => setText(e.target.value)} />
        </Field>
        <p className="aw-row-note">{held.length ? `Replaces every header held now (${held.join(', ')}).` : 'Sent with each trace to the collector.'}</p>
      </DialogContent>
    </Dialog>
  )
}

export function TracesSettings({
  settings,
  now,
  range,
  notices,
  downloading,
  onRangeChange,
  onChange,
  onOpenTraces,
  onDownload,
  onClear,
}: {
  settings: TraceSettings
  now: Date
  range: TraceRange
  notices?: React.ReactNode
  downloading?: boolean
  onRangeChange: (range: TraceRange) => void
  onChange: (input: TraceSettingsInput, said: string) => void
  onOpenTraces?: () => void
  onDownload: () => void
  /** Opens the confirm the container owns. */
  onClear: () => void
}) {
  const [headersOpen, setHeadersOpen] = React.useState(false)
  const held = settings.otlp_header_names
  return (
    <SettingsPage
      icon="timeline"
      title="Traces"
      description="Every run is recorded as a trace: its model calls, tool calls, permission decisions and waits, and what the Hub did around them."
      actions={
        onOpenTraces ? (
          <Button variant="outline" size="sm" data-testid="open-traces-view" onClick={onOpenTraces}>
            Browse traces <Icon name="arrow_forward" size={13} />
          </Button>
        ) : null
      }
    >
      {notices}
      <SettingsGroup title="Kept here">
        <SettingsRow
          label="Recorded"
          description={settings.oldest_trace_at ? `Oldest from ${formatDateTime(settings.oldest_trace_at, now)}.` : 'Nothing recorded yet.'}
          control={
            <span className="aw-row-value" data-testid="trace-counts">
              {plural(settings.trace_count, 'trace')} · {plural(settings.span_count, 'span')}
            </span>
          }
        >
          {settings.dropped_spans > 0 ? (
            <p className="aw-row-note" data-tone="error" data-testid="trace-dropped">
              {plural(settings.dropped_spans, 'span')} could not be written since the Hub started.
            </p>
          ) : null}
        </SettingsRow>
        <SettingsRow
          label="Keep traces for"
          htmlFor="trace-retention"
          description={`Older spans are deleted on their own. The Hub's default is ${settings.retention_days_default} days.`}
          changed={settings.retention_days_chosen}
          onReset={() => onChange({ retention_days: null }, `Traces kept for the default ${settings.retention_days_default} days`)}
          control={
            <CommittedInput
              id="trace-retention"
              numeric
              width={72}
              suffix="days"
              value={String(settings.retention_days)}
              validate={wholeNumber(1, 3650, 'days')}
              onCommit={(v) => onChange({ retention_days: Number(v) }, `Traces kept for ${v} days`)}
            />
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Send to a collector" description="Each finished trace is posted to an OTLP/HTTP endpoint as well as kept here.">
        <SettingsRow
          label="Send traces"
          description={settings.otlp_endpoint ? undefined : 'Needs an endpoint first.'}
          control={
            <Switch
              aria-label="Send traces to a collector"
              checked={settings.export_enabled}
              disabled={!settings.otlp_endpoint}
              onCheckedChange={(v) => onChange({ export_enabled: v }, v ? 'Traces are sent to the collector' : 'Traces are only kept here')}
            />
          }
        />
        <SettingsRow
          label="Endpoint"
          htmlFor="otlp-endpoint"
          description="For example http://localhost:4318/v1/traces."
          control={
            <CommittedInput
              id="otlp-endpoint"
              value={settings.otlp_endpoint ?? ''}
              placeholder="Not set"
              validate={(d) => (!d.trim() || /^https?:\/\//.test(d.trim()) ? null : 'An http:// or https:// address.')}
              onCommit={(v) => onChange({ otlp_endpoint: v || null, ...(v ? {} : { export_enabled: false }) }, v ? `Traces go to ${v}` : 'Endpoint cleared; traces are only kept here')}
            />
          }
        />
        <SettingsRow
          label="Headers"
          description="Sent with each trace, such as an API key. Values are never shown again."
          control={
            <span className="flex flex-wrap items-center justify-end gap-1.5">
              {held.map((name) => (
                <span key={name} className="aw-state-chip" title={`${name} is held; its value is never shown`}>
                  <Icon name="lock" size={11} /> {name}
                </span>
              ))}
              <Button variant="outline" size="sm" onClick={() => setHeadersOpen(true)}>
                {held.length ? 'Replace…' : 'Add…'}
              </Button>
              {held.length ? (
                <Button variant="ghost" size="sm" onClick={() => onChange({ otlp_headers: {} }, 'Headers removed')}>
                  Remove
                </Button>
              ) : null}
            </span>
          }
        />
        <SettingsRow
          label="Last sent"
          control={
            <span className="aw-row-value" data-testid="trace-export-status">
              {settings.last_export_at ? formatDateTime(settings.last_export_at, now) : 'Never'} · {plural(settings.exported_spans, 'span')}
            </span>
          }
        >
          {settings.last_error ? (
            <p role="alert" className="aw-row-note" data-tone="error">
              {settings.last_error}
            </p>
          ) : null}
        </SettingsRow>
      </SettingsGroup>

      <SettingsGroup title="Export and clear" description="Act on the traces recorded in a span of time.">
        <SettingsRow
          label="Traces"
          description={`The ones ${RANGE_WORDS[range]}.`}
          control={
            <Segmented
              label="Which traces"
              size="xs"
              value={range}
              onChange={onRangeChange}
              options={[
                { value: 'day', label: '24 hours' },
                { value: 'week', label: '7 days' },
                { value: 'month', label: '30 days' },
                { value: 'all', label: 'All' },
              ]}
            />
          }
        />
        <SettingsRow
          label="Download"
          description="One OTLP JSON file any OpenTelemetry tool can read."
          control={
            <Button variant="outline" size="sm" disabled={downloading} onClick={onDownload}>
              <Icon name="download" size={13} /> {downloading ? 'Preparing…' : 'Download'}
            </Button>
          }
        />
        <SettingsRow
          label="Clear"
          description="Deletes them from this Hub. Nothing already sent to a collector is touched."
          control={
            <Button variant="destructive" size="sm" onClick={onClear}>
              Clear traces…
            </Button>
          }
        />
      </SettingsGroup>

      <HeadersDialog
        open={headersOpen}
        held={held}
        onOpenChange={setHeadersOpen}
        onReplace={(headers) => {
          setHeadersOpen(false)
          onChange({ otlp_headers: headers }, held.length ? 'Headers replaced' : 'Headers added')
        }}
      />
    </SettingsPage>
  )
}
