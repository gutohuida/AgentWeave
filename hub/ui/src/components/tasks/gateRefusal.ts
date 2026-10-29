import { ApiError } from '@/api/client'
import type { TaskCheckRun } from '@/api/tasks'
import { hubDate } from '@/lib/hubTime'

/**
 * Reading a refused landing (`GateRefusal.to_dict()`): which causes it names, and what the checks
 * are doing, as plain functions the drawer and its remedies share
 * (`every-task-can-always-be-moved-on`, FR-11, FR-12).
 */

/** The categories of `GateRefusal.to_dict()` this surface reads; every key is optional. */
export interface GateBody {
  code?: string
  message?: string
  checks?: Array<{ state?: string }>
  unaccepted?: Array<{
    evidence_id?: string
    identifier?: string
    commit_sha?: string
    recorded_by_task?: string | null
    recorded_by_another_task?: boolean
  }>
  unlinked?: Array<{ evidence_id?: string; identifier?: string; commit_sha?: string }>
  [category: string]: unknown
}

/** The gate's refusal body from a 409, or null for any other error. */
export function gateBodyOf(error: unknown): GateBody | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null
  try {
    const detail = (JSON.parse(error.message) as { detail?: GateBody }).detail
    return detail && detail.code === 'gate_unsatisfied' ? detail : null
  } catch {
    return null
  }
}

const filled = (body: GateBody, key: string) =>
  Array.isArray(body[key]) && (body[key] as unknown[]).length > 0

/** Causes other than the checks: when any is present the checks are not what the refusal waits on. */
const OTHER_CAUSES = [
  'blocking',
  'diagnostics',
  'unmergeable',
  'unaccepted',
  'unlanded',
  'unlinked',
  'unfinished',
]

const WAITING = ['running', 'started', 'not_run']
/** A check has failed (or could not produce a result): the only states 'Land anyway' is for. */
const FAILED = ['failed', 'error', 'preexisting']

/** The refusal is the checks and nothing else, and they are still running or not yet started. */
export function waitsOnChecks(body: GateBody): boolean {
  return (
    filled(body, 'checks') &&
    !OTHER_CAUSES.some((key) => filled(body, key)) &&
    WAITING.includes(body.checks?.[0]?.state ?? '')
  )
}

/** The refusal is the checks alone and one has failed: 'Land anyway', with a reason, is offered. */
export function overrideOffered(body: GateBody): boolean {
  return (
    filled(body, 'checks') &&
    !OTHER_CAUSES.some((key) => filled(body, key)) &&
    FAILED.includes(body.checks?.[0]?.state ?? '')
  )
}

/** How long an earlier run took, from the timestamps the Hub recorded. */
function durationSeconds(run: TaskCheckRun): number | null {
  if (!run.started_at || !run.ended_at) return null
  const seconds = (hubDate(run.ended_at).getTime() - hubDate(run.started_at).getTime()) / 1000
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null
}

/** The run the task's landing waits on, with its elapsed time and how long the previous run took. */
export function checksWait(
  runs: TaskCheckRun[],
  running: boolean,
): { run: TaskCheckRun; previousSeconds: number | null } | null {
  const run = runs[0]
  if (!run || (run.state !== 'running' && !running)) return null
  const previous = runs.slice(1).find((earlier) => earlier.state === 'passed' || earlier.state === 'failed')
  return { run, previousSeconds: previous ? durationSeconds(previous) : null }
}

