import type { CouldNotRunCheck, TaskCheckResult } from '@/api/tasks'

/** The outcome the Hub gives a check whose command could not start (`project_checks.COULD_NOT_RUN`):
 *  neither passed nor failed, and never the work's (`a-check-that-cannot-run-says-so...`, FR-8). */
export const COULD_NOT_RUN = 'could_not_run'

export const isCouldNotRun = (result: Pick<TaskCheckResult, 'outcome'>) => result.outcome === COULD_NOT_RUN

/** `hub-ui could not run: eslint was not found` plus any dependency link that failed in its checkout. */
export function couldNotRunSentence(check: CouldNotRunCheck): string {
  const lacked = check.missing_program ? `${check.missing_program} was not found` : (check.spawn_error ?? '')
  const links = (check.dependency_link_failures ?? []).map((link) => `${link.name}: ${link.reason}`)
  return (
    `${check.name} could not run${lacked ? `: ${lacked}` : ''}` +
    (links.length ? ` · dependency link failed (${links.join('; ')})` : '')
  )
}
