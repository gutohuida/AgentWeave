/** The one stage a card shows (`where-each-task-stands-is-visible-on-the-board`, FR-9). The Hub
 *  derives it from real state (`hub/task_stage.py`); this only words it. */

import { hubDate } from './hubTime'

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
  const start = since instanceof Date ? since : hubDate(since)
  const minutes = (now.getTime() - start.getTime()) / 60000
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

const REVIEW_STAGES: ReadonlySet<string> = new Set([
  'waiting_for_review',
  'under_review',
  'sent_back',
  'approved_waiting',
  'checking',
  'landing',
  'on_main',
  'landing_held',
  'did_not_land',
])

/** The builder and current reviewer a card and the drawer name from "waiting for review" onward
 *  (FR-8). The reviewer is the holder while the task waits for or is under review, and only when it
 *  is somebody other than the builder; a task never reviewed names only its builder. */
export function builderAndReviewer(task: {
  stage?: string | null
  builder?: string | null
  assignee?: string | null
}): { builder: string | null; reviewer: string | null } {
  if (!task.stage || !REVIEW_STAGES.has(task.stage) || !task.builder) return { builder: null, reviewer: null }
  const reviewing = task.stage === 'waiting_for_review' || task.stage === 'under_review'
  const reviewer = reviewing && task.assignee && task.assignee !== task.builder ? task.assignee : null
  return { builder: task.builder, reviewer }
}

/** Stages of an approved task whose work is not on main yet (FR-13). */
export const NOT_ON_MAIN_STAGES: ReadonlySet<string> = new Set([
  'approved_waiting',
  'checking',
  'landing',
  'landing_held',
  'did_not_land',
])

/** The two board-level groups: approved but not yet on main, and being worked on. */
export function groupByStanding<T extends { stage?: string | null }>(tasks: T[]): { notOnMain: T[]; working: T[] } {
  return {
    notOnMain: tasks.filter((t) => t.stage && NOT_ON_MAIN_STAGES.has(t.stage)),
    working: tasks.filter((t) => t.stage === 'working'),
  }
}
