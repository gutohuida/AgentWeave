/**
 * The one place a task lifecycle status is mapped to a colour.
 *
 * There used to be three hand-rolled copies of this mapping — `Badge.tsx`'s `STATUS_STYLES`,
 * `TasksBoard`'s per-column `accentColor`, and an inline ternary chain on the Overview — and they
 * had already drifted: `in_progress` rendered blue on the board and amber on the Overview, where it
 * also collided with `under_review` so the two were indistinguishable. The S7 design rationale
 * warned in advance that changing one copy without a shared config would widen the drift, which is
 * exactly what happened. Import from here instead of re-deriving.
 *
 * `null` means "no hue" — the status is carried by neutral text (`--text-2`), which is deliberate
 * for the three statuses that are not asking for anything: pending, assigned, completed.
 *
 * On `--blue` for `in_progress`: IDENTITY.md clause 2 reserved `--blue` for focus and selection.
 * It was amended on 2026-08-23 to permit exactly this one status use and nothing else, because the
 * remaining semantic colours are all spoken for — amber is `under_review`, green is `approved`, red
 * is the two failure states — and collapsing `in_progress` into any of them loses a distinction the
 * board is built to show. See IDENTITY.md, "Fixed" clause 2.
 */
export type TaskStatusTone = string | null

const TASK_STATUS_TONES: Record<string, TaskStatusTone> = {
  pending: null,
  assigned: null,
  in_progress: 'var(--blue)',
  under_review: 'var(--amber)',
  completed: null,
  approved: 'var(--green)',
  rejected: 'var(--red)',
  revision_needed: 'var(--red)',
}

/** The status's colour token, or `null` when the status is deliberately neutral. */
export function taskStatusTone(status: string): TaskStatusTone {
  return status in TASK_STATUS_TONES ? TASK_STATUS_TONES[status] : null
}

/** The status's colour token, falling back to neutral body text for display contexts that always
 *  need a concrete colour (a dot, a label). */
export function taskStatusColor(status: string, fallback = 'var(--text-2)'): string {
  return taskStatusTone(status) ?? fallback
}
