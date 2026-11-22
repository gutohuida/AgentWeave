/** The pure rules of the dashboard Overview: the health sentence and the small figures the tiles
 *  speak in. No React, so a test can pin every sentence. */

export type MainState = 'green' | 'held' | 'failing' | 'unknown'
export type HealthLevel = 'healthy' | 'attention' | 'trouble'

export interface MainHealth {
  state: MainState
  branch: string | null
  /** Landings the Hub is holding back. Null when it could not tell. */
  heldLandings: number | null
  /** Null = the project's known-failing list has not been checked: unknown, never zero. */
  knownFailing: number | null
  /** One plain sentence for the tile ("3 checks fail on master"). */
  detail?: string | null
}

export interface SpendFigures {
  /** Null when no turn today was priced. */
  todayUsd: number | null
  periodUsd: number | null
  periodLabel: string
  /** Null when the project has no budget. */
  budgetUsd: number | null
  /** Oldest first, one entry per day; null = the day had turns the Hub could not price. */
  trend: { day: string; usd: number | null }[]
  unpricedTurns: number
}

/** The share of the budget used, or null when there is no budget or no figure to compare. */
export function budgetRatio(spend: SpendFigures | null): number | null {
  if (!spend || spend.budgetUsd == null || spend.budgetUsd <= 0 || spend.periodUsd == null) return null
  return spend.periodUsd / spend.budgetUsd
}

export const BUDGET_NEAR = 0.9

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many)

/** "Healthy — nothing needs you and main is green". Trouble outranks attention outranks healthy;
 *  the sentence names every cause, so the header never hides what a tile shows. */
export function healthOf(input: { needs: number; main: MainHealth; spend: SpendFigures | null }): { level: HealthLevel; label: string; sentence: string } {
  const { needs, main, spend } = input
  const branch = main.branch ?? 'main'
  const ratio = budgetRatio(spend)
  const problems: string[] = []
  if (main.state === 'failing') problems.push(`${branch} is failing`)
  if (main.heldLandings) problems.push(main.heldLandings === 1 ? 'a landing is held' : `${main.heldLandings} landings are held`)
  if (ratio != null && ratio >= BUDGET_NEAR) problems.push(`spend is at ${Math.round(ratio * 100)}% of its budget`)
  const needsPart = needs > 0 ? `${needs} ${plural(needs, 'thing needs', 'things need')} you` : null

  if (problems.length > 0) {
    return { level: 'trouble', label: 'Trouble', sentence: join([...problems, ...(needsPart ? [needsPart] : [])]) }
  }
  const mainWords = main.state === 'green' ? `${branch} is green` : main.state === 'unknown' ? `${branch}'s health is unknown` : null
  if (needsPart) {
    return { level: 'attention', label: 'Needs you', sentence: join([needsPart, ...(mainWords ? [mainWords] : [])]) }
  }
  return { level: 'healthy', label: 'Healthy', sentence: join(['nothing needs you', ...(mainWords ? [mainWords] : [])]) }
}

function join(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? ''
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`
  return `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}`
}

export interface FinishedTally {
  landed: number
  sentBack: number
  failed: number
}

/** "4 landed · 1 sent back · 1 failed", leaving out what is zero (these counts are known). */
export function tallyWords(t: FinishedTally): string {
  const parts = [`${t.landed} landed`]
  if (t.sentBack) parts.push(`${t.sentBack} sent back`)
  if (t.failed) parts.push(`${t.failed} failed`)
  return parts.join(' · ')
}

/** "Builder, QA1 and 2 more" for the Running tile. */
export function agentList(names: string[], max = 2): string {
  const unique = [...new Set(names)]
  if (unique.length <= max) return unique.join(', ')
  return `${unique.slice(0, max).join(', ')} and ${unique.length - max} more`
}
