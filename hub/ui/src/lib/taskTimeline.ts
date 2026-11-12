/** A task's story as a timeline (`task-card-and-story-redesign`, FR-6): every event the Hub's
 *  `/story` route returns becomes one entry with a glyph, a label of at most six words, the actor and
 *  the time, and keeps its full text for when it is opened. Runs of four or more consecutive routine
 *  entries fold into one entry that opens.
 *
 *  Milestones never fold. Proposed in the spec's open question and not yet confirmed by the operator:
 *  created, finished building, approved, sent back, landed or did not land, closed. A failure (a
 *  failed check run, a run that stopped unfinished, a refused turn) is never folded either, so
 *  folding can hide only what went as expected. */

import type { StoryEvent } from '@/api/tasks'
import type { StageTone } from './taskStageVisual'

export interface TimelineEntry {
  id: string
  glyph: string
  /** At most six words (FR-6). */
  label: string
  actor: string | null
  at: string | null
  tone: StageTone
  milestone: boolean
  /** The entry's full text, shown when it is opened. */
  detail: string | null
}

export interface TimelineFold {
  id: string
  folded: TimelineEntry[]
}

export type TimelineItem = { kind: 'entry'; entry: TimelineEntry } | { kind: 'fold'; fold: TimelineFold }

/** How many consecutive routine entries make a fold (FR-6). */
export const FOLD_AT = 4

const TRANSITION: Record<string, { glyph: string; label: string; tone: StageTone; milestone?: boolean }> = {
  pending: { glyph: 'circle_dashed', label: 'Put back in the queue', tone: 'idle' },
  assigned: { glyph: 'person_add', label: 'Assigned', tone: 'idle' },
  in_progress: { glyph: 'circle_dot', label: 'Started building', tone: 'idle' },
  completed: { glyph: 'package_check', label: 'Finished building', tone: 'info', milestone: true },
  under_review: { glyph: 'visibility', label: 'Taken into review', tone: 'info' },
  approved: { glyph: 'stamp', label: 'Approved', tone: 'done', milestone: true },
  revision_needed: { glyph: 'restart_alt', label: 'Sent back', tone: 'needs-you', milestone: true },
  rejected: { glyph: 'remove_circle', label: 'Closed', tone: 'idle', milestone: true },
  blocked: { glyph: 'hand', label: 'Waiting on you', tone: 'needs-you' },
}

function who(kind: string | null | undefined, actor: string | null | undefined): string | null {
  if (kind === 'operator') return 'You'
  return actor ?? null
}

function duration(seconds: number | null): string {
  if (seconds == null) return ''
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function toEntry(event: StoryEvent): TimelineEntry {
  const base = { id: `${event.kind}-${event.id}`, at: event.at }
  switch (event.kind) {
    case 'created':
      return { ...base, glyph: 'add', label: 'Created', actor: event.by, tone: 'idle', milestone: true, detail: null }
    case 'transition': {
      const look = TRANSITION[event.to] ?? { glyph: 'arrow_forward', label: `Moved to ${event.to.replace(/_/g, ' ')}`, tone: 'idle' as StageTone }
      const by = event.job ? `${event.job_kind === 'flow' ? 'Flow' : 'Loop'} ${event.job}` : who(event.actor_kind, event.actor)
      const detail = [
        `${event.from.replace(/_/g, ' ')} → ${event.to.replace(/_/g, ' ')}`,
        event.override_reason ? `Overridden: ${event.override_reason}` : null,
      ]
        .filter(Boolean)
        .join('. ')
      return { ...base, glyph: look.glyph, label: look.label, actor: by, tone: look.tone, milestone: Boolean(look.milestone), detail }
    }
    case 'run': {
      const failed = event.status === 'failed' || Boolean(event.error)
      const live = event.status === 'running'
      const label = live ? 'Running now' : failed ? 'Run failed' : `Ran for ${duration(event.duration_seconds)}`.trim()
      const detail = [event.model, event.cost_usd != null ? `$${event.cost_usd.toFixed(2)}` : null, event.error].filter(Boolean).join(' · ')
      return { ...base, glyph: live ? 'circle_dot' : failed ? 'error' : 'terminal', label, actor: event.agent, tone: live ? 'live' : failed ? 'failed' : 'idle', milestone: false, detail: detail || null }
    }
    case 'evidence': {
      const decision = event.reviews[event.reviews.length - 1]?.decision
      const label = decision === 'accepted' ? 'Evidence accepted' : decision === 'rejected' ? 'Evidence rejected' : 'Evidence recorded'
      return {
        ...base,
        glyph: decision === 'rejected' ? 'error_outline' : 'clipboard_check',
        label,
        actor: who(event.evidence.actor_kind, event.evidence.actor),
        tone: decision === 'rejected' ? 'failed' : decision === 'accepted' ? 'done' : 'idle',
        milestone: false,
        detail: event.evidence.summary,
      }
    }
    case 'check': {
      const failures = event.results.filter((r) => !r.skipped && r.passed === false)
      const failed = event.state === 'failed' || event.state === 'error'
      const label =
        event.state === 'running' ? 'Checks running' : failed ? `${failures.length || 'Some'} ${failures.length === 1 ? 'check' : 'checks'} failed` : event.state === 'passed' ? 'Checks passed' : `Checks ${event.state}`
      const detail = failed ? failures.map((r) => r.name ?? r.command ?? 'check').join(', ') || event.error : null
      return { ...base, glyph: failed ? 'x' : 'fact_check', label, actor: null, tone: failed ? 'failed' : event.state === 'passed' ? 'done' : 'info', milestone: false, detail }
    }
    case 'integration': {
      const merged = event.outcome === 'merged'
      return {
        ...base,
        glyph: merged ? 'git_merge' : 'error',
        label: merged ? `Landed on ${event.target_branch ?? 'main'}` : 'Did not land',
        actor: who(event.actor_kind, event.actor),
        tone: merged ? 'done' : 'failed',
        milestone: true,
        detail: merged ? (event.commit_sha ? `Commit ${event.commit_sha.slice(0, 8)}` : null) : event.reason,
      }
    }
    case 'divergence':
      return { ...base, glyph: 'alert_triangle', label: 'Run stopped unfinished', actor: event.agent, tone: 'failed', milestone: false, detail: `The run ended with the task ${event.task_status_at_end.replace(/_/g, ' ')}.` }
    case 'question':
      return {
        ...base,
        glyph: 'help_circle',
        label: event.answered ? 'You answered a question' : 'Asked you a question',
        actor: event.agent,
        tone: event.answered ? 'idle' : 'needs-you',
        milestone: false,
        detail: event.answer ? `${event.question}\n\n${event.answer}` : event.question,
      }
    case 'turn':
      return { ...base, glyph: 'stop_circle', label: event.review ? 'Review turn refused' : 'Turn refused', actor: event.agent, tone: 'failed', milestone: false, detail: event.refusal ?? event.ended_reason }
    case 'workspace':
      return { ...base, glyph: 'folder', label: 'Checkout problem', actor: null, tone: 'failed', milestone: false, detail: event.reason }
    case 'review_unstaffed':
      return { ...base, glyph: 'person_add', label: 'No reviewer available', actor: null, tone: 'needs-you', milestone: false, detail: event.reason }
  }
}

/** Whether an entry may be folded: routine, and not a failure or something waiting on the operator. */
export function isRoutine(entry: TimelineEntry): boolean {
  return !entry.milestone && entry.tone !== 'failed' && entry.tone !== 'needs-you' && entry.tone !== 'live'
}

/** The story's events, oldest first as the route returns them, as entries and folds. */
export function timeline(events: StoryEvent[]): TimelineItem[] {
  const items: TimelineItem[] = []
  let run: TimelineEntry[] = []
  const flush = () => {
    if (run.length >= FOLD_AT) items.push({ kind: 'fold', fold: { id: `fold-${run[0].id}`, folded: run } })
    else for (const entry of run) items.push({ kind: 'entry', entry })
    run = []
  }
  for (const event of events) {
    const entry = toEntry(event)
    if (isRoutine(entry)) {
      run.push(entry)
      continue
    }
    flush()
    items.push({ kind: 'entry', entry })
  }
  flush()
  return items
}
