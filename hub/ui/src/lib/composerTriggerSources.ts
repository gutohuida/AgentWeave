import type { ComposerTriggerMatch } from './composerTrigger'
import type { ComposerTriggerMenuItem } from '@/components/agents/ComposerTriggerMenu'

const SKILLS_DIR_PREFIX = '.claude/skills/'
const MAX_RESULTS = 50

// The commands the composer itself supports — no backend registry exists (or is
// needed) for this fixed, code-defined list (design.md Decision 3).
export const COMPOSER_BUILT_IN_COMMANDS: ComposerTriggerMenuItem[] = [{ value: 'model', label: '/model' }]

/**
 * Resolve a trigger's menu results from the one workspace path listing already
 * fetched for this composer (design.md's caching mitigation: fetched once, filtered
 * client-side per keystroke rather than re-requested).
 *
 * `path` results are the listing itself, filtered by query. `skill` results are the
 * same listing scoped to `.claude/skills/` — there is no separate skill-listing
 * endpoint (design.md Decision 2) — with that prefix and any `.md` suffix stripped
 * for display. `slash-command` results never touch `workspacePaths` at all.
 */
export function resolveTriggerResults(
  trigger: ComposerTriggerMatch,
  workspacePaths: string[],
): ComposerTriggerMenuItem[] {
  const query = trigger.query.toLowerCase()

  if (trigger.kind === 'slash-command') {
    return COMPOSER_BUILT_IN_COMMANDS.filter((command) => command.value.toLowerCase().includes(query))
  }

  if (trigger.kind === 'skill') {
    return workspacePaths
      .filter((path) => path.startsWith(SKILLS_DIR_PREFIX))
      .map((path) => path.slice(SKILLS_DIR_PREFIX.length).replace(/\.md$/, ''))
      .filter((name) => name.toLowerCase().includes(query))
      .slice(0, MAX_RESULTS)
      .map((name) => ({ value: name, label: name }))
  }

  return workspacePaths
    .filter((path) => path.toLowerCase().includes(query))
    .slice(0, MAX_RESULTS)
    .map((path) => ({ value: path, label: path }))
}
