import type { LatestIntegration, Task } from '@/api/tasks'

/** The compact board card's one status line: which fact it states, and how. */
export type StatusTone = 'working' | 'waiting' | 'review' | 'failed' | 'revision' | 'gated' | 'decided'

/** Which fact the status line states. Exposed as `data-reason` so a test can name the fact
 *  without depending on the sentence. */
export type CardStatusReason =
  | 'waiting'
  | 'proceeded'
  | 'not-merged'
  | 'divergence'
  | 'regressed'
  | 'gated-on-rejected'
  | 'gated'
  | 'revision'
  | 'working'
  | 'review'
  | 'decided-without-you'

export interface CardStatus {
  tone: StatusTone
  reason: CardStatusReason
  text: string
  detail?: string
  retry?: boolean
}

const STALLED_DETAIL = 'A run worked on this and ended without changing its status. Nothing is running now.'

/** The one thing worth saying about this card, if any. Order is urgency: something the operator
 *  must answer, then a failure, then a gate, then live work, then what the column already implies.
 *
 *  Every fact today's card drew as its own badge has a line here: the wait (`blocked` or an open
 *  ask, coalesced as one, F14), a decision taken without the operator's answer (F60), the merge
 *  outcome, a dropped run (divergence), a prerequisite that regressed under running work, a gate
 *  on a prerequisite (F19, red when that prerequisite was rejected), and live work (D12). */
export function cardStatus(task: Task, working?: boolean): CardStatus | null {
  const waiting = task.blocked_reason ?? task.awaiting_answer_reason
  if (waiting || task.status === 'blocked') {
    const why = waiting ?? 'an answer from you'
    // A wait does not make an earlier dropped run less true (F902): say both.
    if (task.has_open_divergence) {
      return {
        tone: 'waiting',
        reason: 'waiting',
        text: `Waiting on you · ${why} · stalled`,
        detail: `${why}. ${STALLED_DETAIL}`,
      }
    }
    return { tone: 'waiting', reason: 'waiting', text: `Waiting on you · ${why}`, detail: why }
  }
  const proceeded = task.proceeded_without_answer_reason
  if (proceeded && task.status !== 'approved') {
    return { tone: 'review', reason: 'proceeded', text: 'Went ahead without your answer', detail: proceeded }
  }
  const integration: LatestIntegration | null | undefined = task.latest_integration
  if (task.status === 'approved' && integration && integration.outcome !== 'merged') {
    return {
      tone: 'failed',
      reason: 'not-merged',
      text: integration.outcome === 'failed' ? 'Merge failed' : 'Not merged',
      detail: integration.reason ? sentence(integration.reason) : undefined,
      retry: integration.retryable,
    }
  }
  if (task.has_open_divergence) {
    // Not "Dropped": shown that word, the operator asked "what is a dropped task?" (2026-08-10).
    return {
      tone: 'failed',
      reason: 'divergence',
      text: 'The run stopped without finishing it',
      detail: STALLED_DETAIL,
    }
  }
  if (task.dependency_state === 'running_on_regressed') {
    return {
      tone: 'failed',
      reason: 'regressed',
      text: 'A prerequisite regressed',
      detail: 'This work is under way, but a task it depends on no longer reads approved.',
    }
  }
  if (task.dependency_state === 'gated_on_rejected' || task.dependency_state === 'gated') {
    const blocking = (task.prerequisites ?? []).filter((p) => p.status !== 'approved')
    const rejected = task.dependency_state === 'gated_on_rejected'
    return {
      tone: rejected ? 'failed' : 'gated',
      reason: rejected ? 'gated-on-rejected' : 'gated',
      text: rejected
        ? 'A prerequisite was rejected'
        : blocking.length
          ? `Waits on ${blocking.length === 1 ? blocking[0]!.title : `${blocking.length} tasks`}`
          : 'Waits on a prerequisite',
      detail: blocking.length
        ? `Cannot start yet — waiting on ${blocking.map((p) => `${p.title} (${p.status.replace(/_/g, ' ')})`).join(', ')}`
        : 'Cannot start yet — a prerequisite has not been approved.',
    }
  }
  if (task.status === 'revision_needed') return { tone: 'revision', reason: 'revision', text: 'Sent back for changes' }
  if (working) return { tone: 'working', reason: 'working', text: `${task.assignee ?? 'An agent'} is working on it` }
  if (task.status === 'under_review') return { tone: 'review', reason: 'review', text: 'Waiting for a review' }
  if (proceeded) {
    return { tone: 'decided', reason: 'decided-without-you', text: 'Decided without you earlier', detail: proceeded }
  }
  return null
}

function sentence(text: string): string {
  const t = text.trim()
  return t ? t[0]!.toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? '' : '.') : t
}
