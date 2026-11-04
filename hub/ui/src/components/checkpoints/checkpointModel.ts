import type { ProjectCheckpoint } from '@/api/checkpoints'

/**
 * What a checkpoint says on screen, in the operator's words. The Hub records `task_completion`,
 * `unwritten`, `hub_from_body`; none of them is ever a label here (`every-checkpoint-findable-and-
 * readable`, FR-3). A value this screen has no wording for is made readable rather than shown raw.
 */

/** What triggered a checkpoint, as a past-tense phrase: "The operator asked". */
const TRIGGER_WORDS: Record<string, string> = {
  task_completion: 'A task finished',
  operator: 'The operator asked',
  context_pressure: 'The conversation grew long',
}

/** The triggers the filter offers: the ones the Hub records today. */
export const TRIGGER_FILTER_OPTIONS = Object.entries(TRIGGER_WORDS).map(([value, label]) => ({ value, label }))

function sentenceCase(words: string): string {
  const spaced = words.replace(/[_-]+/g, ' ').trim()
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : 'Taken for a reason not recorded'
}

export function triggerWords(trigger: string | null | undefined): string {
  if (!trigger) return 'Taken for a reason not recorded'
  return TRIGGER_WORDS[trigger] ?? sentenceCase(trigger)
}

export type StatusTone = 'green' | 'amber' | 'red' | 'neutral'

const STATUS_WORDS: Record<string, { label: string; tone: StatusTone }> = {
  ready: { label: 'Ready', tone: 'green' },
  unwritten: { label: 'Nothing was written', tone: 'amber' },
  failed: { label: 'Failed its checks', tone: 'red' },
}

export function statusWords(status: string | null | undefined): { label: string; tone: StatusTone } {
  if (!status) return { label: 'Status not recorded', tone: 'neutral' }
  return STATUS_WORDS[status] ?? { label: sentenceCase(status), tone: 'neutral' }
}

/** Who wrote the title and summary: only the Hub's own are worth saying. */
export function madeByHub(checkpoint: Pick<ProjectCheckpoint, 'title_made_by'>): boolean {
  return Boolean(checkpoint.title_made_by) && checkpoint.title_made_by !== 'model'
}

/** The sentence that goes with a title the Hub made, and where it came from. */
export function madeByHubWords(checkpoint: Pick<ProjectCheckpoint, 'title_made_by'>): string | null {
  if (checkpoint.title_made_by === 'hub_from_body') {
    return 'The title and summary were made by the Hub from the start of the checkpoint, because the model’s answers were rejected.'
  }
  if (checkpoint.title_made_by === 'hub_from_facts') {
    return 'The title was made by the Hub from the agent, the reason and the date, because the model’s answers could not be read.'
  }
  return madeByHub(checkpoint) ? 'The title and summary were made by the Hub, not written by the model.' : null
}

/** A checkpoint's title; one the fill has not reached yet still gets a readable stand-in. */
export function checkpointTitle(checkpoint: ProjectCheckpoint): string {
  return checkpoint.title?.trim() || `${triggerWords(checkpoint.trigger)} (no title yet)`
}

/** The dimension names the checks use, as the operator would say them. */
const DIMENSION_WORDS: Record<string, string> = {
  files: 'files changed',
  files_changed: 'files changed',
  open_questions: 'open questions',
  questions: 'open questions',
  citations: 'citations',
  tasks: 'tasks',
}

export function dimensionWords(dimension: string): string {
  return DIMENSION_WORDS[dimension] ?? dimension.replace(/[_-]+/g, ' ')
}

/** What the checks found, one sentence per area: "files changed: missing a.py; invented b.py". */
export function findingWords(finding: { dimension: string; missing?: string[]; invented?: string[] }): string {
  const parts: string[] = []
  if (finding.missing?.length) parts.push(`missing ${finding.missing.join(', ')}`)
  if (finding.invented?.length) parts.push(`invented ${finding.invented.join(', ')}`)
  return `${dimensionWords(finding.dimension)}: ${parts.join('; ') || 'a mismatch'}`
}

export interface CheckpointFilters {
  agent: string
  trigger: string
  conversationId: string
}

export const NO_FILTERS: CheckpointFilters = { agent: '', trigger: '', conversationId: '' }

/** The filters as the Hub's route takes them. */
export function routeFilters(filters: CheckpointFilters) {
  return {
    agent: filters.agent || undefined,
    trigger: filters.trigger || undefined,
    conversationId: filters.conversationId || undefined,
  }
}

/** Splits the covered runs' word for the list: "3 runs", or the reason there are none. */
export function coveredRunsWords(count: number): string {
  if (count === 0) return 'Covers no recorded run'
  return count === 1 ? 'Covers 1 run' : `Covers ${count} runs`
}
