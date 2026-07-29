import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AgentOutputLine } from '@/api/agents'
import { SharedStreamRenderer } from '@/components/stream/SharedStreamRenderer'
import { normalizeStreamEvent, streamActivityEvents } from '@/components/stream/streamModel'

const line = (overrides: Partial<AgentOutputLine>): AgentOutputLine => ({
  id: 'out-1', agent: 'codex', content: 'hello',
  timestamp: '2026-07-29T12:00:00Z', ...overrides,
})

describe('shared stream semantics', () => {
  it('normalizes legacy prefixes through one adapter', () => {
    expect(normalizeStreamEvent(line({ content: '[stderr] warning' })).kind).toBe('diagnostic')
    expect(normalizeStreamEvent(line({ content: '[error] failed' })).kind).toBe('error')
    expect(normalizeStreamEvent(line({ content: '[thinking] work' })).kind).toBe('thinking')
  })

  it('pairs tools by run and call id and exposes safe payloads', () => {
    const lines = [
      line({ id: 'use', kind: 'tool_use', run_id: 'run-1', payload: { call_id: 'c1', tool: 'shell' }, content: 'Run shell' }),
      line({ id: 'result', kind: 'tool_result', run_id: 'run-1', sequence: 2, payload: { call_id: 'c1', output: 'ok' }, content: 'Shell finished' }),
    ]
    render(<SharedStreamRenderer lines={lines} />)
    expect(screen.getByText(/completed/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Run shell'))
    expect(screen.getByText(/"call_id": "c1"/)).toBeInTheDocument()
  })

  it('can hide diagnostics but never errors', () => {
    render(<SharedStreamRenderer showDiagnostics={false} lines={[
      line({ id: 'diag', kind: 'diagnostic', content: 'internal note' }),
      line({ id: 'error', kind: 'error', content: 'visible failure' }),
    ]} />)
    expect(screen.queryByText('internal note')).not.toBeInTheDocument()
    expect(screen.getByText('visible failure')).toBeInTheDocument()
  })

  it('groups live thinking and renders incomplete tools independently', () => {
    render(<SharedStreamRenderer lines={[
      line({ id: 'think-1', kind: 'thinking', run_id: 'run-live', content: 'first thought' }),
      line({ id: 'think-2', kind: 'thinking', run_id: 'run-live', content: 'second thought', timestamp: '2026-07-29T12:00:02Z' }),
      line({ id: 'tool-only', kind: 'tool_use', run_id: 'run-live', payload: { call_id: 'missing' }, content: 'Unpaired tool' }),
    ]} />)
    expect(screen.getByText(/Thinking · 2s/)).toBeInTheDocument()
    expect(screen.getByText(/awaiting result/)).toBeInTheDocument()
  })

  it('projects semantic activity without prefix classification', () => {
    const activity = streamActivityEvents([
      line({ id: 'text', kind: 'text' }),
      line({ id: 'status', kind: 'status', content: 'started' }),
      line({ id: 'tool', kind: 'tool_use', content: 'tool' }),
    ])
    expect(activity.map((event) => event.kind)).toEqual(['status', 'tool_use'])
  })
})
