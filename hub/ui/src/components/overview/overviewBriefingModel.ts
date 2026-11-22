import { healthOf, tallyWords, type MainHealth, type SpendFigures } from './overviewDashboardModel'
import type { ActivityOutcome } from './OverviewDashboard'

/** The words of the Briefing: a headline and a short summary written from the data. Pure, so a
 *  test can pin every sentence. */

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many)
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function headline(input: { needs: number; main: MainHealth; spend: SpendFigures | null }): string {
  return `${cap(healthOf(input).sentence)}.`
}

/** Finished work grouped by how it ended, in the order the Briefing lists them. */
export const OUTCOME_ORDER: ActivityOutcome[] = ['failed', 'sent_back', 'stopped', 'landed']

/** "3 landed, 1 sent back, 1 failed, 1 stopped" over what ended since the operator last looked. */
export function sinceWords(items: { outcome: ActivityOutcome }[]): string {
  const c = { landed: 0, sentBack: 0, failed: 0, stopped: 0 }
  for (const i of items) {
    if (i.outcome === 'landed') c.landed += 1
    else if (i.outcome === 'sent_back') c.sentBack += 1
    else if (i.outcome === 'failed') c.failed += 1
    else if (i.outcome === 'stopped') c.stopped += 1
  }
  return [tallyWords(c), c.stopped ? `${c.stopped} stopped` : null].filter(Boolean).join(' \u00b7 ').replace(/ \u00b7 /g, ', ')
}

/** The summary: what changed since the last look (only when the Hub knows when that was), who is
 *  working on what. How many things need the operator is the headline's. */
export function summary(input: {
  /** "2 hours ago", or null when the Hub has no record of a last visit. */
  lastSeenWords: string | null
  finished: { outcome: ActivityOutcome }[]
  working: { agent: string; what: string }[]
}): string[] {
  const out: string[] = []
  if (input.lastSeenWords == null) {
    out.push('The Hub has no record of your last visit, so this is where things stand now.')
  } else if (input.finished.length === 0) {
    out.push(`Since you last looked ${input.lastSeenWords}, nothing has finished.`)
  } else {
    const n = input.finished.length
    out.push(`Since you last looked ${input.lastSeenWords}, ${n} ${plural(n, 'task has', 'tasks have')} finished: ${sinceWords(input.finished)}.`)
  }
  if (input.working.length === 0) out.push('No profile is working right now.')
  else {
    const first = input.working[0]!
    const more = input.working.length - 1
    out.push(`${first.agent} is working on \u201c${first.what}\u201d${more > 0 ? `, and ${more} ${plural(more, 'other turn is', 'other turns are')} running` : ''}.`)
  }
  return out
}