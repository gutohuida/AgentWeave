/**
 * The Profiles page's pure rules: what a profile's status says, the order the list keeps, how the
 * filter narrows it, and what its model line reads. No React here, so the rules are tested alone.
 */

export type ProfileStatusKind = 'working' | 'reviewing' | 'idle' | 'held' | 'no-model'

export interface ProfileStatus {
  kind: ProfileStatusKind
  /** The task a working or reviewing profile is on; the reason a held one is held ("rate limit"). */
  detail?: string | null
}

/** What a profile is doing now, for the detail's "Now" strip. */
export type ProfileNow =
  | {
      kind: 'working' | 'reviewing'
      task: string
      build?: string | null
      since: string
      /** Reviewing: whose work it is checking. */
      reviewing?: string | null
    }
  | { kind: 'held'; reason: string; until?: string | null; lastTask?: string | null }
  | { kind: 'last-run'; at: string; task?: string | null }
  | { kind: 'never' }

export interface ProfileListItem {
  name: string
  colorIndex: number | null
  charterName: string | null
  /** The default model's provider (the mark) and its display name; null with no model. */
  provider: string | null
  providerLabel: string | null
  model: string | null
  /** Models the pool holds beyond the default. */
  moreModels: number
  status: ProfileStatus
  /** Spent so far; `null` is unknown ("unpriced"), never zero. `undefined` is nothing spent yet. */
  spendUsd: number | null | undefined
  lastActiveAt: string | null
  archived: boolean
}

const WORDS: Record<ProfileStatusKind, string> = {
  working: 'Working',
  reviewing: 'Reviewing',
  idle: 'Idle',
  held: 'Held',
  'no-model': 'No model',
}

/** The word that carries the status (colour only accompanies it). */
export function statusWord(status: ProfileStatus): string {
  return WORDS[status.kind]
}

/** "Working on Add retries", "Held, rate limit": the word and, where there is one, its detail. */
export function statusSentence(status: ProfileStatus): string {
  const word = statusWord(status)
  if (!status.detail) return word
  return status.kind === 'held' ? `${word}, ${status.detail}` : `${word} on ${status.detail}`
}

export function isActive(item: ProfileListItem): boolean {
  return !item.archived && (item.status.kind === 'working' || item.status.kind === 'reviewing')
}

/** "Sonnet 5.5", "Sonnet 5.5 +2 models", "No model". */
export function modelLine(item: Pick<ProfileListItem, 'model' | 'moreModels'>): string {
  if (!item.model) return 'No model'
  if (item.moreModels <= 0) return item.model
  return `${item.model} +${item.moreModels} ${item.moreModels === 1 ? 'model' : 'models'}`
}

/** Case-insensitive match on the name, charter, model and status word. */
export function matchesQuery(item: ProfileListItem, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [item.name, item.charterName, item.model, statusWord(item.status), item.status.detail]
    .filter((v): v is string => Boolean(v))
    .some((v) => v.toLowerCase().includes(q))
}

export interface ProfileGroups {
  /** Working or reviewing now. */
  active: ProfileListItem[]
  /** Everyone else, A to Z. */
  rest: ProfileListItem[]
  archived: ProfileListItem[]
}

const byName = (a: ProfileListItem, b: ProfileListItem) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })

/** Profiles at work first, then the rest alphabetically; archived ones last, in their own group. */
export function groupProfiles(items: readonly ProfileListItem[], query = ''): ProfileGroups {
  const shown = items.filter((i) => matchesQuery(i, query))
  return {
    active: shown.filter(isActive).sort(byName),
    rest: shown.filter((i) => !i.archived && !isActive(i)).sort(byName),
    archived: shown.filter((i) => i.archived).sort(byName),
  }
}

/** The rows in the order they are drawn, for arrow-key movement and the default selection. */
export function listOrder(groups: ProfileGroups, archivedOpen: boolean): ProfileListItem[] {
  return [...groups.active, ...groups.rest, ...(archivedOpen ? groups.archived : [])]
}

/** "8 profiles" or "2 of 8 profiles", for the quiet line under the filter. */
export function countLine(shown: number, total: number): string {
  const noun = total === 1 ? 'profile' : 'profiles'
  return shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`
}
