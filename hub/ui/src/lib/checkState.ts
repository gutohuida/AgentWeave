/** A task's latest check run, as every task surface shows it (spec
 *  `task-stages-in-the-build-view-and-dependency-map`, FR-3, FR-12, FR-13). The Hub chooses the run
 *  and its state; this only words it. A passed run shows nothing: only what holds a task, or broke,
 *  is news on a row. */

import type { StageTone } from './taskStageVisual'

export type CheckKind = 'pre_review' | 'landing'
export type CheckRunState = 'waiting' | 'running' | 'passed' | 'failed' | 'could_not_run'

export interface CheckState {
  kind: CheckKind
  state: CheckRunState
}

export const CHECK_KIND_WORD: Record<CheckKind, string> = {
  pre_review: 'Pre-review checks',
  landing: 'Landing checks',
}

const KIND_SHORT: Record<CheckKind, string> = { pre_review: 'Pre-review', landing: 'Landing' }

const STATE_VISUAL: Record<CheckRunState, { glyph: string; word: string; tone: StageTone; moving?: boolean; explain: string }> = {
  waiting: { glyph: 'schedule', word: 'waiting', tone: 'idle', explain: 'queued for a check slot, or asked for and not started yet' },
  running: { glyph: 'sync', word: 'running', tone: 'info', moving: true, explain: 'running now' },
  passed: { glyph: 'check', word: 'passed', tone: 'done', explain: 'passed' },
  failed: { glyph: 'x', word: 'failed', tone: 'failed', explain: 'failed on the work. Open the task to see which check' },
  could_not_run: {
    glyph: 'block',
    word: 'could not run',
    tone: 'needs-you',
    explain: 'could not run, so they say nothing about the work. Open the task to see why',
  },
}

/** The stage that already names a kind of check, so the marker beside it need not repeat it. */
const STAGE_OF_KIND: Record<CheckKind, string> = { pre_review: 'pre_review_checks', landing: 'checking' }

export interface CheckMarkerVisual {
  glyph: string
  /** "Running" beside its own check stage; "Pre-review failed" beside any other stage. */
  text: string
  /** The whole sentence, for the tooltip and the accessible name. */
  title: string
  tone: StageTone
  moving: boolean
}

export function checkMarker(check: CheckState | null | undefined, stage: string | null | undefined): CheckMarkerVisual | null {
  if (!check || check.state === 'passed') return null
  const v = STATE_VISUAL[check.state]
  const named = STAGE_OF_KIND[check.kind] === stage
  const text = named ? v.word.charAt(0).toUpperCase() + v.word.slice(1) : `${KIND_SHORT[check.kind]} ${v.word}`
  return { glyph: v.glyph, text, title: `${CHECK_KIND_WORD[check.kind]} ${v.explain}.`, tone: v.tone, moving: Boolean(v.moving) }
}
