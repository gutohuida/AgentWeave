// mock state for the Leaner navigation mock (spec "Leaner navigation", slice 1). Everything here is
// hand-written (the shapes are the routes'), so the new screens render the same on a fresh checkout
// whose recorded fixtures are stubs. Times sit just before MOCK_NOW (2026-10-17T12:10Z).
import * as React from 'react'
import type { AccountingSnapshot } from '@/api/accounting'
import type { Job } from '@/api/jobs'
import type { ProjectLedger } from '@/api/ledger'
import type { EventLogEntry } from '@/api/logs'
import type { Span, TraceDetail, TraceList, TraceSummary, TraceTotals, TraceTotalsAnswer } from '@/api/traces'
import type { ConversationRun } from '@/components/traces/conversationTraceModel'
import { useConfigStore } from '@/store/configStore'
import { PROJECT_ID } from './fixtures'
import { NIGHT_TALLY } from './workFixture'

const NOW_MS = Date.parse('2026-10-17T12:10:00Z')
const iso = (minutesBeforeNow: number) => new Date(NOW_MS - minutesBeforeNow * 60_000).toISOString()

/** The project's tabs after the cleanup: six, in this order. */
export const LEANER_TABS = ['overview', 'tasks', 'profiles', 'spec', 'vault', 'dashboards'] as const

// ---- Budgets: the usage the limits section reads, and the ledger under it -----------------------

const usage = (tokens: number, usd: number | null, turns = 12) => ({
  input_tokens: Math.round(tokens * 0.8),
  output_tokens: Math.round(tokens * 0.2),
  total_tokens: tokens,
  measured_turns: turns,
  unavailable_turns: 0,
  api_equivalent_usd_micros: usd == null ? null : Math.round(usd * 1_000_000),
  unpriced_turns: usd == null ? turns : 0,
})

export const LEANER_ACCOUNTING: AccountingSnapshot = {
  project: usage(31_843_065, 38.42, 96),
  agents: [
    { agent: 'Builder', ...usage(19_600_000, 24.1, 52) },
    { agent: 'Architect', ...usage(8_200_000, 11.3, 28) },
    { agent: 'QA1', ...usage(4_043_065, null, 16) },
  ],
  workers: [
    { kind: 'checkpoint', input_tokens: 410_000, output_tokens: 52_000, total_tokens: 462_000, measured_calls: 9, unmeasured_calls: 0, api_equivalent_usd_micros: 640_000 },
    { kind: 'conversation_title', input_tokens: 38_000, output_tokens: 4_000, total_tokens: 42_000, measured_calls: 31, unmeasured_calls: 0, api_equivalent_usd_micros: 40_000 },
  ],
  budget: { limit_tokens: 60_000_000, used_tokens: 31_843_065, remaining_tokens: 28_156_935, exhausted: false },
  preferred_display: { kind: 'api_equivalent', label: 'API-equivalent estimate', usd_micros: 38_420_000 } as AccountingSnapshot['preferred_display'],
  recent_turns: [],
}

export const LEANER_LEDGER: ProjectLedger = {
  merges: [
    { id: 'm1', task_id: 'task-1', task_title: 'Checkpoints tab wired to the route', outcome: 'merged', commit_sha: '9f2c1ab', source_branch: 'agentweave/Builder', target_branch: 'master', reason: null, actor_kind: 'operator', actor: 'you', at: iso(95) },
    { id: 'm2', task_id: 'task-2', task_title: 'Jobs list shows the next run', outcome: 'merged', commit_sha: '41be07d', source_branch: 'agentweave/Builder', target_branch: 'master', reason: null, actor_kind: 'agent', actor: 'Builder', at: iso(60 * 7) },
    { id: 'm3', task_id: 'task-3', task_title: 'Trace export keeps its headers', outcome: 'refused', commit_sha: null, source_branch: 'agentweave/QA1', target_branch: 'master', reason: 'The project folder has uncommitted changes to tracked files.', actor_kind: 'agent', actor: 'QA1', at: iso(60 * 26) },
  ],
  spend: {
    total_usd: 38.42,
    total_tokens: 31_843_065,
    worker_usd: 0.68,
    unpriced: 1,
    by_day: [
      { day: '2026-10-15', usd: 9.8, worker_usd: 0.2, tokens: 7_900_000 },
      { day: '2026-10-16', usd: 14.6, worker_usd: 0.3, tokens: 12_100_000 },
      { day: '2026-10-17', usd: 14.02, worker_usd: 0.18, tokens: 11_843_065 },
    ],
    by_agent: [
      { agent: 'Builder', usd: 24.1, tokens: 19_600_000, turns: 52 },
      { agent: 'Architect', usd: 11.3, tokens: 8_200_000, turns: 28 },
      { agent: 'QA1', usd: null, tokens: 4_043_065, turns: 16, unpriced: 16 },
    ],
    by_task: [
      { task_id: 'task-1', task_title: 'Checkpoints tab wired to the route', usd: 12.4, tokens: 9_800_000, turns: 21 },
      { task_id: 'task-2', task_title: 'Jobs list shows the next run', usd: 6.1, tokens: 4_900_000, turns: 11 },
    ],
  },
  divergences: [],
  messages: [
    { id: 'msg1', sender: 'Builder', recipient: 'QA1', subject: 'Ready for review', excerpt: 'The checkpoints panel is on its branch; the open-in-place view is the part to check.', task_id: 'task-1', task_title: 'Checkpoints tab wired to the route', at: iso(70) },
  ],
  origins: { spec: 4, loop: 1, agent: 2, operator: 3 },
  notices: [{ kind: 'context_warning', count: 37, first_at: iso(60 * 30), last_at: iso(12), by_agent: [{ agent: 'Builder', count: 25 }, { agent: 'Architect', count: 12 }] }],
  totals: { merged: 8, integrations: 10, divergences: 0, open_divergences: 0, tasks: 14 },
}

// ---- Jobs (a project settings section now) -------------------------------------------------------

const job = (n: number, name: string, agent: string, cron: string, message: string, extra: Partial<Job> = {}): Job => ({
  id: `job-${n}`,
  project_id: PROJECT_ID,
  name,
  agent,
  message,
  cron,
  session_mode: 'new',
  enabled: true,
  source: 'hub',
  created_at: '2026-10-10T09:00:00Z',
  last_run: iso(60 * 10),
  next_run: new Date(NOW_MS + 60 * 60_000 * 14).toISOString(),
  run_count: 6,
  archived_at: null,
  loop: null,
  ...extra,
})

export const LEANER_JOBS: Job[] = [
  job(1, 'Nightly drift scan', 'QA1', '0 2 * * *', 'Scan the spec documents for drift against master and report anything new.'),
  job(2, 'Daily dependency check', 'Builder', '0 9 * * *', 'Check the lockfiles for advisories and open a task for each real one.', { run_count: 3, next_run: new Date(NOW_MS + 60 * 60_000 * 21).toISOString() }),
  job(3, 'Morning summary', 'Architect', '30 7 * * 1-5', 'Summarize what changed yesterday and what is waiting for me.', { enabled: false, run_count: 12, next_run: undefined }),
]

// ---- Logs ---------------------------------------------------------------------------------------

const log = (n: number, minutes: number, event_type: string, agent: string, severity: string, data: Record<string, unknown> = {}): EventLogEntry => ({
  id: `log-${n}`,
  project_id: PROJECT_ID,
  event_type,
  agent,
  severity,
  timestamp: iso(minutes),
  data,
})

/** Newest first, as `GET /logs` answers. */
export const LEANER_LOGS: EventLogEntry[] = [
  log(8, 3, 'task_updated', 'Builder', 'info', { task_id: 'task-1', status: 'under_review' }),
  log(7, 5, 'agent_heartbeat', 'Builder', 'debug', { agent: 'Builder', status: 'working' }),
  log(6, 9, 'message_created', 'Builder', 'info', { from: 'Builder', to: 'QA1', subject: 'Ready for review' }),
  log(5, 14, 'watchdog_agent_exit', 'QA1', 'warn', { agent: 'QA1', exit_code: 1 }),
  log(4, 22, 'question_asked', 'QA1', 'info', { question: 'Allow a 30-second cache on search results?' }),
  log(3, 31, 'transport_error', 'Architect', 'error', { method: 'runner stream', error: 'The runner closed the connection before the turn ended.' }),
  log(2, 44, 'task_created', 'Architect', 'info', { task_id: 'task-3', title: 'Trace export keeps its headers', assignee: 'QA1' }),
  log(1, 58, 'agent_heartbeat', 'Architect', 'debug', { agent: 'Architect', status: 'idle' }),
]

// ---- Traces -------------------------------------------------------------------------------------

const run = (n: number, agent: string, minutesAgo: number, lengthMin: number, extra: Partial<TraceSummary> = {}): TraceSummary => ({
  trace_id: `trace-${n}`,
  root_span_id: `span-${n}`,
  run_id: `run-${n}`,
  name: `invoke_agent ${agent}`,
  operation: 'invoke_agent',
  kind: 'run',
  agent,
  conversation_id: 'conv-e3aba2c5956a',
  task_id: null,
  run_status: 'completed',
  initiator: 'operator',
  status: 'ok',
  status_message: null,
  start_time: iso(minutesAgo),
  end_time: iso(minutesAgo - lengthMin),
  ended: true,
  span_count: 40 + n * 3,
  model: 'claude-sonnet-5-5',
  task_ref: null,
  task_title: null,
  cost_usd: 0.4 + n * 0.17,
  cost_state: 'measured',
  tool_errors: 0,
  is_error: false,
  run_kind: 'thread',
  conversation_title: 'Wire the Checkpoints tab',
  ...extra,
})

export const LEANER_TRACE_LIST: TraceList = {
  traces: [
    run(6, 'Builder', 12, 9),
    run(5, 'QA1', 48, 14, { conversation_id: 'conv-qa1000000001', conversation_title: 'Review of the fill pass', run_kind: 'review', task_ref: 'FRORC-3', task_title: 'Checkpoints tab wired to the route', initiator: 'autonomous' }),
    run(4, 'Builder', 95, 26, { run_status: 'failed', status: 'error', status_message: 'The runner exited with code 1', is_error: true, tool_errors: 2, cost_usd: 1.9 }),
    run(3, 'Architect', 200, 11, { conversation_id: 'conv-9cdda4865e0b', conversation_title: 'Roadmap scoping', cost_usd: null, cost_state: 'unpriced' }),
    run(2, 'Builder', 410, 33, { run_kind: 'task', task_ref: 'FRORC-2', task_title: 'Jobs list shows the next run', initiator: 'autonomous' }),
  ],
  next_before: null,
}

const totals = (count: number, errors: number): TraceTotals => ({
  count,
  errors,
  error_kinds: { failed: errors, stopped: 0, trace_error: 0 },
  running: 0,
  cost_usd_micros: 4_870_000,
  priced: count - 1,
  unpriced: 1,
  duration_seconds: count * 700,
  duration_avg_seconds: 700,
  tokens: { input: 5_400_000, output: 610_000, cache_read: 3_100_000, cache_write: 240_000 },
  model_calls: count * 14,
  tool_calls: count * 38,
  tool_errors: errors * 2,
  wait_seconds: 410,
})

export const LEANER_TRACE_TOTALS: TraceTotalsAnswer = { totals: totals(5, 1), group_by: null, groups: null }

// ---- A thread's trace (the side panel's Trace tab) ----------------------------------------------

const asRun = (t: TraceSummary): ConversationRun => ({
  run_id: t.run_id!,
  trace_id: t.trace_id,
  agent: t.agent,
  model: t.model ?? null,
  initiator: t.initiator ?? null,
  run_status: t.run_status ?? null,
  status: t.status,
  status_message: t.status_message,
  start_time: t.start_time,
  end_time: t.end_time,
  ended: t.ended,
  cost_usd_micros: t.cost_usd != null ? Math.round(t.cost_usd * 1_000_000) : null,
  cost_state: t.cost_state,
  input_tokens: 600_000,
  output_tokens: 70_000,
  model_calls: 12,
  tool_calls: 30,
  tool_errors: t.tool_errors ?? 0,
  wait_seconds: 20,
  span_count: t.span_count,
})

export const THREAD_RUNS: ConversationRun[] = [
  run(2, 'Builder', 410, 33),
  run(4, 'Builder', 95, 26, { run_status: 'failed', status: 'error', status_message: 'The runner exited with code 1', is_error: true, tool_errors: 2 }),
  run(6, 'Builder', 12, 9),
].map(asRun)

function span(n: number, trace: string, parent: string | null, name: string, operation: string, startMs: number, endMs: number, status: Span['status'] = 'ok'): Span {
  return {
    span_id: `s-${n}`,
    trace_id: trace,
    parent_span_id: parent,
    name,
    operation,
    status,
    status_message: null,
    start_time: new Date(startMs).toISOString(),
    end_time: new Date(endMs).toISOString(),
    ended: true,
    attributes: {},
    events: [],
  }
}

/** A run's spans, for the turns the tab opens unfolded. */
export function threadDetail(r: ConversationRun): TraceDetail {
  const start = Date.parse(r.start_time)
  const end = Date.parse(r.end_time ?? r.start_time)
  const at = (f: number) => start + (end - start) * f
  const t = r.trace_id
  const root = span(0, t, null, 'invoke_agent Builder', 'invoke_agent', start, end, r.status)
  const kids = [
    span(1, t, 's-0', 'chat', 'chat', at(0.02), at(0.3)),
    span(2, t, 's-0', 'execute_tool Read', 'execute_tool', at(0.3), at(0.38)),
    span(3, t, 's-0', 'execute_tool Edit', 'execute_tool', at(0.38), at(0.45)),
    span(4, t, 's-0', 'chat', 'chat', at(0.45), at(0.8)),
    span(5, t, 's-0', 'execute_tool Bash', 'execute_tool', at(0.8), at(0.97), r.status === 'error' ? 'error' : 'ok'),
  ]
  return { trace_id: t, kind: 'run', run_id: r.run_id, root, spans: [root, ...kids], total: kids.length + 1, offset: 0, limit: 500 }
}

// ---- Serving the hooks' routes -------------------------------------------------------------------

/** Components that read through the app's own hooks (the ledger, the logs, the traces view) render
 *  in the mock by answering the routes they call. While a screen that needs it is mounted, the
 *  config store reads as configured against the mock's own origin, and `fetch` answers
 *  `/api/v1/projects/<id>/...` from the data above; every other request is passed through
 *  untouched. Nothing leaves the page, so no Hub is called. Restored on unmount. */
export function useMockRoutes(): boolean {
  const [ready, setReady] = React.useState(false)
  React.useEffect(() => {
    const before = useConfigStore.getState()
    const original = window.fetch
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
    window.fetch = async (input, init) => {
      const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const url = new URL(raw, window.location.origin)
      if (url.origin === window.location.origin && url.pathname.startsWith('/api/v1/')) {
        const rest = url.pathname.replace(`/api/v1/projects/${PROJECT_ID}`, '')
        if (rest === '/ledger') return json(LEANER_LEDGER)
        if (rest === '/stats') return json(NIGHT_TALLY)
        if (rest === '/logs/agents') return json(['Builder', 'Architect', 'QA1'])
        if (rest === '/logs') return json(!url.searchParams.get('offset') || url.searchParams.get('offset') === '0' ? LEANER_LOGS : [])
        if (rest === '/traces/totals') return json(LEANER_TRACE_TOTALS)
        if (rest === '/traces') return json(LEANER_TRACE_LIST)
        if (rest.startsWith('/agents')) return json([])
        return json({}, 404)
      }
      return original(input, init)
    }
    useConfigStore.setState({ isConfigured: true, apiKey: 'mock', hubUrl: window.location.origin, selectedProjectId: PROJECT_ID })
    setReady(true)
    return () => {
      window.fetch = original
      useConfigStore.setState({ isConfigured: before.isConfigured, apiKey: before.apiKey, hubUrl: before.hubUrl })
    }
  }, [])
  return ready
}