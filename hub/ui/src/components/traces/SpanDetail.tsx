import { useState } from 'react'
import { format } from 'date-fns'
import { Badge } from '@/components/common/Badge'
import { Expander } from '@/components/common/Expander'
import { Icon } from '@/components/common/Icon'
import type { Span } from '@/api/traces'
import { hubDate } from '@/lib/hubTime'
import {
  CONTENT_ATTRIBUTES,
  formatDuration,
  operationLabel,
  spanToken,
} from '@/components/traces/traceModel'

const MONO = { fontFamily: 'var(--mono)' }

function at(value: string | null): string {
  if (!value) return '—'
  return format(hubDate(value), 'yyyy-MM-dd HH:mm:ss.SSS')
}

function scalarText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

interface MessagePart {
  type?: string
  content?: unknown
  name?: string
  id?: string
  arguments?: unknown
}

interface Message {
  role?: string
  parts?: MessagePart[]
}

function isMessageList(value: unknown): value is Message[] {
  return (
    Array.isArray(value) &&
    value.every((item) => item && typeof item === 'object' && Array.isArray((item as Message).parts))
  )
}

function text(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === undefined || value === null) return ''
  return JSON.stringify(value, null, 2)
}

/** A content attribute, opened: messages by role and part, anything else as it was recorded. */
function ContentValue({ value }: { value: unknown }) {
  if (isMessageList(value)) {
    return (
      <div className="space-y-2">
        {value.map((message, index) => (
          <div key={index}>
            <div className="mb-0.5 text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
              {message.role ?? 'message'}
            </div>
            {(message.parts ?? []).map((part, partIndex) => (
              <div key={partIndex} className="mb-1">
                {part.type && part.type !== 'text' && (
                  <span className="mr-1 text-[10.5px]" style={{ color: 'var(--text-3)' }}>
                    [{part.type}{part.name ? ` ${part.name}` : ''}]
                  </span>
                )}
                <pre className="whitespace-pre-wrap break-words text-[11.5px]" style={{ ...MONO, color: 'var(--text-2)' }}>
                  {part.type === 'tool_call' ? text(part.arguments) : text(part.content)}
                </pre>
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }
  return (
    <pre className="whitespace-pre-wrap break-words text-[11.5px]" style={{ ...MONO, color: 'var(--text-2)' }}>
      {text(value)}
    </pre>
  )
}

function ContentAttribute({ name, value }: { name: string; value: unknown }) {
  const [open, setOpen] = useState(false)
  const id = `trace-content-${name.replace(/[^a-z0-9]+/gi, '-')}`
  const size = text(value).length
  return (
    <div className="rounded-md" style={{ border: '1px solid var(--border)' }}>
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left text-[11.5px]"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((current) => !current)}
        style={{ color: 'var(--text-2)' }}
      >
        <Icon name="expand_more" size={13} style={{ transform: open ? undefined : 'rotate(-90deg)' }} />
        <span style={MONO}>{name}</span>
        <span className="ml-auto text-[10.5px]" style={{ color: 'var(--text-3)' }}>
          {size.toLocaleString()} chars
        </span>
      </button>
      <Expander open={open} id={id}>
        <div className="max-h-[360px] overflow-auto px-2 pb-2" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="pt-2">{open && <ContentValue value={value} />}</div>
        </div>
      </Expander>
    </div>
  )
}

/** Everything one span recorded: its timing and outcome, its attributes, and its events. */
export function SpanDetail({ span, nowMs }: { span: Span; nowMs: number }) {
  const entries = Object.entries(span.attributes ?? {})
  const scalars = entries.filter(([key]) => !CONTENT_ATTRIBUTES.has(key))
  const contents = entries.filter(([key]) => CONTENT_ATTRIBUTES.has(key))
  const startMs = hubDate(span.start_time).getTime()
  const endMs = span.end_time ? hubDate(span.end_time).getTime() : nowMs
  const open = !span.ended && !span.end_time

  return (
    <div className="space-y-3 text-[12px]" data-testid="trace-span-detail">
      <div className="flex flex-wrap items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: spanToken(span) }} aria-hidden="true" />
        <h3 className="text-[13px] font-semibold" style={{ color: 'var(--text)' }}>{span.name}</h3>
        <Badge>{operationLabel(span.operation)}</Badge>
        <Badge variant={span.status === 'error' ? 'danger' : span.status === 'ok' ? 'success' : 'default'}>
          {open ? 'open' : span.status}
        </Badge>
      </div>
      {span.status_message && (
        <p className="text-[12px]" style={{ color: span.status === 'error' ? 'var(--red)' : 'var(--text-2)' }}>
          {span.status_message}
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[11.5px]">
        <dt style={{ color: 'var(--text-3)' }}>Started</dt>
        <dd style={{ ...MONO, color: 'var(--text-2)' }}>{at(span.start_time)}</dd>
        <dt style={{ color: 'var(--text-3)' }}>Ended</dt>
        <dd style={{ ...MONO, color: 'var(--text-2)' }}>{open ? 'still open' : at(span.end_time)}</dd>
        <dt style={{ color: 'var(--text-3)' }}>Duration</dt>
        <dd style={{ ...MONO, color: 'var(--text-2)' }}>
          {formatDuration(Math.max(0, endMs - startMs))}
          {open ? ' so far' : ''}
        </dd>
        <dt style={{ color: 'var(--text-3)' }}>Operation</dt>
        <dd style={{ ...MONO, color: 'var(--text-2)' }}>{span.operation}</dd>
        <dt style={{ color: 'var(--text-3)' }}>Span</dt>
        <dd className="break-all" style={{ ...MONO, color: 'var(--text-3)' }}>{span.span_id}</dd>
      </dl>

      {scalars.length > 0 && (
        <section>
          <h4 className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--text-3)' }}>
            Attributes
          </h4>
          <table className="w-full text-[11.5px]" data-testid="trace-span-attributes">
            <tbody>
              {scalars.map(([key, value]) => (
                <tr key={key} style={{ borderTop: '1px solid var(--border)' }}>
                  <td className="py-1 pr-3 align-top" style={{ ...MONO, color: 'var(--text-3)', width: '40%' }}>{key}</td>
                  <td className="break-all py-1 align-top" style={{ ...MONO, color: 'var(--text)' }}>{scalarText(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {contents.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="text-[10.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--text-3)' }}>
            Content
          </h4>
          {contents.map(([key, value]) => (
            <ContentAttribute key={key} name={key} value={value} />
          ))}
        </section>
      )}

      {span.events.length > 0 && (
        <section>
          <h4 className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--text-3)' }}>
            Events
          </h4>
          <ul className="space-y-1">
            {span.events.map((event, index) => {
              const attrs = Object.entries(event.attributes ?? {})
              return (
                <li key={`${event.name}-${index}`} className="text-[11.5px]">
                  <span style={{ ...MONO, color: 'var(--text-3)' }}>
                    +{formatDuration(Math.max(0, hubDate(event.time).getTime() - startMs))}
                  </span>{' '}
                  <span style={{ color: 'var(--text)' }}>{event.name}</span>
                  {attrs.length > 0 && (
                    <span className="break-all" style={{ ...MONO, color: 'var(--text-2)' }}>
                      {' '}
                      {attrs.map(([key, value]) => `${key}=${scalarText(value)}`).join(' ')}
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </div>
  )
}
