import type { SpecAmendment } from '@/api/spec'

/** How an amendment's operation reads: a recorded change, and the same change proposed. */
export const OP_LABEL: Record<SpecAmendment['op'], string> = {
  add_task: 'Added task',
  add_requirement: 'Added requirement',
  add_criterion: 'Added criterion',
  change_criterion: 'Changed criterion',
  remove_criterion: 'Removed criterion',
  cannot_satisfy: 'Cannot satisfy',
}

export const PROPOSED_LABEL: Record<SpecAmendment['op'], string> = {
  add_task: 'Proposes a task',
  add_requirement: 'Proposes a requirement',
  add_criterion: 'Proposes a criterion',
  change_criterion: 'Proposes changing criterion',
  remove_criterion: 'Proposes removing criterion',
  cannot_satisfy: 'Cannot satisfy',
}
