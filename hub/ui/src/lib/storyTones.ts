import type { Tone } from '@/components/common/StatePill'

/** Which state tone a task status reads in (vis-D8: colour carries state and nothing else). */
export function statusTone(status: string): Tone {
  switch (status) {
    case 'approved':
      return 'green'
    case 'rejected':
    case 'revision_needed':
      return 'red'
    case 'under_review':
      return 'amber'
    case 'in_progress':
      return 'blue'
    case 'blocked':
      return 'purple'
    default:
      return 'neutral'
  }
}

/** Which state tone a piece of evidence reads in. */
export function evidenceTone(state: string): Tone {
  if (state === 'accepted') return 'green'
  if (state === 'rejected') return 'red'
  return 'amber'
}
