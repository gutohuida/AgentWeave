/** The one stage a card shows (`where-each-task-stands-is-visible-on-the-board`, FR-9). The Hub
 *  derives it from real state (`hub/task_stage.py`); this only words it. */

export const STAGE_LABELS: Record<string, string> = {
  not_started: 'Not started',
  working: 'Being worked on',
  waiting_for_answer: 'Waiting for an answer',
  waiting_for_review: 'Waiting for review',
  under_review: 'Under review',
  sent_back: 'Sent back',
  approved_waiting: 'Approved, waiting to land',
  checking: 'Checking',
  landing: 'Landing',
  on_main: 'On main',
  landing_held: 'Landing held',
  did_not_land: 'Did not land',
  closed: 'Closed without landing',
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, ' ')
}

/** How long a task has been at its stage, compactly: "now", "14 min", "3 hours", "2 days". */
export function formatStageAge(since: string | number | Date, now: Date = new Date()): string {
  const minutes = (now.getTime() - new Date(since).getTime()) / 60000
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${Math.floor(minutes)} min`
  const hours = minutes / 60
  if (hours < 24) {
    const n = Math.floor(hours)
    return `${n} ${n === 1 ? 'hour' : 'hours'}`
  }
  const n = Math.floor(hours / 24)
  return `${n} ${n === 1 ? 'day' : 'days'}`
}
