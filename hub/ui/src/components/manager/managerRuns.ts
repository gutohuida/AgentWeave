import type { ManagerEndedRun, ManagerJob, ManagerRunningRun } from '@/api/manager'
import type { SpecDocumentRecord } from '@/api/spec'
import { hubDate } from '@/lib/hubTime'

/** How a manager run reads on screen (`background-manager-work-you-can-see`): its job's title and
 *  the item it works on, from the payload the Hub sent. Nothing here names a job's behaviour, so a
 *  job added later reads with its registry title and its subject's own keys (FR-14). */

/** The mender is not a one-shot job, but the Hub lists it in the manager's registry with this key. */
export const MENDER_JOB = 'mender'

/** "spec-vault-check" → "Spec vault check", for a job the registry did not list. */
function humanize(key: string): string {
  const words = key.replace(/[-_]+/g, ' ').trim()
  return words ? words[0]!.toUpperCase() + words.slice(1) : key
}

export function jobTitle(job: string, jobs: ManagerJob[] | undefined): string {
  return jobs?.find((j) => j.key === job)?.title ?? humanize(job)
}

/** The last path segment that is not `spec.json`: the change's own name. */
function documentName(path: string): string {
  const parts = path.split('/').filter((p) => p && p !== 'spec.json')
  return parts[parts.length - 1] ?? path
}

/** The item a run works on, in words: the spec's title, the stall's reason, else the subject's
 *  first value. Null when the subject names nothing. */
export function subjectLabel(subject: Record<string, unknown> | null | undefined, documents: SpecDocumentRecord[] | undefined): string | null {
  if (!subject) return null
  // A spec-vault-check names the document by path; a build retrospective by id, with `path` beside it.
  const document = typeof subject.path === 'string' ? subject.path : subject.document
  if (typeof document === 'string') return documents?.find((d) => d.path === document || d.id === document)?.title ?? documentName(document)
  if (typeof subject.reason === 'string' && subject.reason) return subject.reason
  if (typeof subject.source === 'string') return `Vault source ${subject.source}`
  if (typeof subject.conversation_id === 'string') return 'A thread'
  const first = Object.values(subject).find((v) => typeof v === 'string' && v)
  return typeof first === 'string' ? first : null
}

/** Seconds between a Hub timestamp and `nowMs` (this window's clock), never negative. */
export function secondsSince(startedAt: string, nowMs: number): number {
  return Math.max(0, (nowMs - hubDate(startedAt).getTime()) / 1000)
}

/** Whether a run is on the item a placement shows: its job, and the subject's match when given. */
export function onItem(
  run: Pick<ManagerRunningRun, 'job' | 'subject'>,
  job: string,
  matches?: (subject: Record<string, unknown>) => boolean,
): boolean {
  return run.job === job && (!matches || matches(run.subject ?? {}))
}

export type EndedOutcome = 'finished' | 'failed'

export function endedAs(run: Pick<ManagerEndedRun, 'outcome'>): EndedOutcome {
  return run.outcome === 'failed' ? 'failed' : 'finished'
}
