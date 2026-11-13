import type { SpecBlockingFinding } from '@/api/spec'

/* A gap the Hub lists, in the operator's words. The codes stay in the Hub's answers for agents;
 * the panel never shows them (AW-127). */

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many)

const count = (n: number) => (n === 1 ? 'one' : String(n))

/** The step a `steps_skipped` message says the journey goes on to, as the phase bar names it. */
function stepsSkipped(group: SpecBlockingFinding[]): string {
  const match = /goes on to ([a-z, ]+?),? which it never reached/.exec(group[0].message)
  const steps = match ? match[1].split(',').map((step) => step.trim()).filter(Boolean) : []
  const skipped = steps.length ? steps.join(' → ') : 'the earlier steps'
  return (
    `This spec skipped steps on its way here (${skipped}). If it already has what those steps ` +
    'produce, mark it as at its last step on the phase bar.'
  )
}

const WORDS: Record<string, (group: SpecBlockingFinding[]) => string> = {
  criterion_without_check: (g) =>
    `${count(g.length)} acceptance ${plural(g.length, 'criterion doesn’t', 'criteria don’t')} say how ` +
    `${plural(g.length, 'it', 'they')} will be checked or who checks ${plural(g.length, 'it', 'them')}.`,
  no_acceptance_drive: () =>
    'The first task should be the acceptance drive: the check that fails until the change works end to end, with every other task coming after it.',
  unresolved_question: (g) =>
    `${count(g.length)} open ${plural(g.length, 'question is', 'questions are')} still unanswered.`,
  requirement_without_criterion: (g) =>
    `${count(g.length)} ${plural(g.length, 'requirement has', 'requirements have')} no acceptance criterion saying when it is met.`,
  requirement_without_task: (g) =>
    `${count(g.length)} ${plural(g.length, 'requirement has', 'requirements have')} no task that builds ${plural(g.length, 'it', 'them')}.`,
  task_without_requirement: (g) =>
    `${count(g.length)} ${plural(g.length, 'task serves', 'tasks serve')} no requirement.`,
  unordered_file_overlap: (g) => {
    const files = [...new Set(g.map((gap) => /edit '([^']+)'/.exec(gap.message)?.[1]).filter(Boolean))]
    return (
      `${count(g.length)} ${plural(g.length, 'pair of tasks edits', 'pairs of tasks edit')} the same file ` +
      `with no order between them, so they could collide${files.length ? `: ${files.join(', ')}` : ''}.`
    )
  },
  undeclared_task_files: (g) =>
    `${count(g.length)} ${plural(g.length, 'task doesn’t', 'tasks don’t')} say which files ${plural(g.length, 'it', 'they')} will edit, so overlaps can’t be seen.`,
  steps_skipped: stepsSkipped,
  amendments_unreviewed: (g) => g[0].message.replace(/^(\d+) amendments? not reviewed by the operator.*/, '$1 changes a tester made to this spec are waiting for your review.'),
  vault_warning: (g) =>
    g.length === 1 ? g[0].message : `${g.length} requirements disagree with what the knowledge vault recorded.`,
  test_only_task: (g) =>
    `${count(g.length)} ${plural(g.length, 'task only writes', 'tasks only write')} tests, with nothing it checks.`,
  reviewer_undeclared: () => 'No reviewer is named, so any free agent will review the work.',
  recommended_people: () => 'No builder or checker is recommended for the tasks.',
}

/** `unknown_thing` → `Unknown thing`. */
function humanize(code: string): string {
  const words = code.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** A raw route instruction ("POST /api/v1/…") and the code-like places carry nothing for a person. */
function scrub(message: string): string {
  return message
    .replace(/(?:send it back first, )?POST \/api\/\S+(?: \{[^}]*\})?/g, '')
    .replace(/\(the step control on its phase bar\)/g, '')
    .replace(/\/api\/\S+/g, '')
    .replace(/\s+/g, ' ')
    .replace(/[:,]\s*$/, '.')
    .trim()
}

/** One sentence for a group of gaps sharing a code. Unknown codes fall back to their message. */
export function plainGap(code: string, group: SpecBlockingFinding[]): string {
  const known = WORDS[code]
  if (known) return known(group)
  const message = scrub(group[0].message)
  return group.length > 1 ? `${humanize(code)} (${group.length}): ${message}` : `${humanize(code)}: ${message}`
}
