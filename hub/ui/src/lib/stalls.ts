import type { Stall } from '@/api/stalls'

/** How a stall reads wherever it is shown (`a-two-profile-build-cannot-deadlock-and-a-stall-says-
 *  so`, D5): its status word, its notice, and which task each open stall names. Pure, so the
 *  screens that draw it and their tests share one statement of it. */

/** The status word and icon a stalled build or task shows over Running and Ready for review (FR-7,
 *  P21: a word and a shape, never colour alone). The sidebar's word (`NEED_WORD.stalled`). */
export const STALLED = { label: 'Stalled', icon: 'alert_triangle' } as const

/** A stall's notice in the operator's words (FR-9, P20): a sentence starting with a capital, with
 *  stored ids swapped for what they mean -- the task's readable reference, or "this task", and "a
 *  thread" for a conversation. */
export function stallNotice(reason: string, taskRef?: string | null): string {
  const text = reason
    .trim()
    .replace(/\btask-[0-9a-f]{6,}\b/g, taskRef || 'this task')
    .replace(/\bconv-[0-9a-f]{6,}\b/g, 'a thread')
    .replace(/\brun-[0-9a-f]{6,}\b/g, 'a run')
  if (!text) return text
  const capital = text.charAt(0).toUpperCase() + text.slice(1)
  return /[.!?]$/.test(capital) ? capital : `${capital}.`
}

/** The open stall naming each task, by task id: what the board card and the build page read. */
export function stallsByTask(stalls: Stall[]): Map<string, Stall> {
  const byTask = new Map<string, Stall>()
  for (const stall of stalls) if (stall.task_id && !byTask.has(stall.task_id)) byTask.set(stall.task_id, stall)
  return byTask
}
