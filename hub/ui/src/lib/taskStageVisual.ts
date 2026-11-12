/** How each task stage looks (`task-card-and-story-redesign`, FR-2, FR-8, FR-9): a glyph, a short
 *  word, a status tone, and where it sits on the task's thread. The Hub decides the stage
 *  (`hub/task_stage.py`); this only draws it. Every stage pairs its colour with a glyph and a word,
 *  so none is told by colour alone. */

import { stageLabel } from './taskStage'

export type StageTone = 'idle' | 'live' | 'needs-you' | 'info' | 'done' | 'failed'

export interface StageVisual {
  glyph: string
  /** The card's word for the stage: short enough to share a line with the time at stage. */
  word: string
  tone: StageTone
  /** Which knot of the thread the task has reached (see THREAD_KNOTS), and whether the thread is
   *  cut there (a landing that did not happen, or a task closed without landing). */
  knot: number
  cut?: boolean
  /** Something is moving at this stage: the knot pulses (still under reduced motion). */
  moving?: boolean
}

/** The task's thread, left to right: built, reviewed, approved, checked, on main. */
export const THREAD_KNOTS = ['Built', 'Reviewed', 'Approved', 'Checked', 'On main'] as const

const VISUALS: Record<string, StageVisual> = {
  not_started: { glyph: 'circle_dashed', word: 'Not started', tone: 'idle', knot: -1 },
  working: { glyph: 'circle_dot', word: 'Building', tone: 'live', knot: 0, moving: true },
  waiting_for_answer: { glyph: 'hand', word: 'Needs your answer', tone: 'needs-you', knot: 0 },
  waiting_for_review: { glyph: 'hourglass', word: 'Ready for review', tone: 'idle', knot: 1 },
  under_review: { glyph: 'visibility', word: 'In review', tone: 'info', knot: 1, moving: true },
  sent_back: { glyph: 'restart_alt', word: 'Sent back', tone: 'needs-you', knot: 0 },
  approved_waiting: { glyph: 'stamp', word: 'Approved', tone: 'info', knot: 2 },
  checking: { glyph: 'fact_check', word: 'Checking', tone: 'info', knot: 3, moving: true },
  landing: { glyph: 'git_merge', word: 'Landing', tone: 'info', knot: 4, moving: true },
  on_main: { glyph: 'circle_check_big', word: 'On main', tone: 'done', knot: 4 },
  landing_held: { glyph: 'pause', word: 'Landing held', tone: 'needs-you', knot: 3 },
  did_not_land: { glyph: 'error', word: 'Did not land', tone: 'failed', knot: 4, cut: true },
  closed: { glyph: 'remove_circle', word: 'Closed', tone: 'idle', knot: -1, cut: true },
}

/** How the card words the Hub's `stage_waits_on`, which names a different thing per stage
 *  (`hub/task_stage.py`): the agent asking, the prerequisites not yet done, what a landing is held
 *  behind. */
export function waitsWording(stage: string | null | undefined, waitsOn: string): string {
  if (stage === 'waiting_for_answer') return `asked by ${waitsOn}`
  if (stage === 'landing_held') return `behind ${waitsOn}`
  if (stage === 'not_started') return `after ${waitsOn}`
  return `on ${waitsOn}`
}

export function stageVisual(stage: string | null | undefined): StageVisual {
  if (!stage) return VISUALS.not_started
  return VISUALS[stage] ?? { glyph: 'circle', word: stageLabel(stage), tone: 'idle', knot: -1 }
}

/** The token each tone draws in. Amber is "needs you", per the brand book; the accent never is. */
export const TONE_COLOR: Record<StageTone, string> = {
  idle: 'var(--text-3)',
  live: 'var(--green)',
  'needs-you': 'var(--amber)',
  info: 'var(--blue)',
  done: 'var(--green)',
  failed: 'var(--red)',
}
