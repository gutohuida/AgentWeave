import type { ComposerTriggerMatch } from './composerTrigger'
import type { ComposerTriggerMenuItem } from '@/components/agents/ComposerTriggerMenu'
import { isSafeMentionValue } from './fileMentions'

const SKILLS_DIR_PREFIX = '.claude/skills/'
const MAX_RESULTS = 50
/** At most this many specs head the `@` menu, so a large project's specs never push the files
 *  out of it (`reference-a-spec-in-a-sentence-from-the-composer`, design D7). */
export const MAX_SPEC_RESULTS = 10

/** A specification document as the `@` menu needs it: the project's document list's own fields. */
export interface SpecReferenceTarget {
  id: string
  title: string
  path: string
  updated_at?: string | null
}

/**
 * The specs an `@query` offers: those whose title or path contains the query (case-insensitive),
 * most recently updated first, capped at `MAX_SPEC_RESULTS`. Filtering keeps the recency order
 * rather than ranking by match (D7). A document with no `updated_at` sorts last; ties keep the
 * list's own order.
 */
export function resolveSpecResults(query: string, specs: SpecReferenceTarget[]): SpecReferenceTarget[] {
  const needle = query.toLowerCase()
  const time = (spec: SpecReferenceTarget) => {
    const parsed = spec.updated_at ? Date.parse(spec.updated_at) : NaN
    return Number.isNaN(parsed) ? -Infinity : parsed
  }
  return specs
    .filter((spec) => spec.title.toLowerCase().includes(needle) || spec.path.toLowerCase().includes(needle))
    .map((spec, index) => ({ spec, index, at: time(spec) }))
    .sort((a, b) => (b.at === a.at ? a.index - b.index : b.at > a.at ? 1 : -1))
    .slice(0, MAX_SPEC_RESULTS)
    .map(({ spec }) => spec)
}

function skillNameFromPath(path: string): string {
  const relative = path.slice(SKILLS_DIR_PREFIX.length)
  return relative.endsWith('/SKILL.md')
    ? relative.slice(0, -'/SKILL.md'.length)
    : relative.replace(/\.md$/, '')
}

/** Accepting this command opens the composer's model picker instead of inserting text (F553). */
export const MODEL_COMMAND = 'model'

// The commands the composer itself supports — no backend registry exists (or is
// needed) for this fixed, code-defined list (design.md Decision 3).
export const COMPOSER_BUILT_IN_COMMANDS: ComposerTriggerMenuItem[] = [{ value: MODEL_COMMAND, label: '/model' }]

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
  specs: SpecReferenceTarget[] = [],
): ComposerTriggerMenuItem[] {
  const query = trigger.query.toLowerCase()

  if (trigger.kind === 'slash-command') {
    return COMPOSER_BUILT_IN_COMMANDS.filter((command) => command.value.toLowerCase().includes(query))
  }

  if (trigger.kind === 'skill') {
    return workspacePaths
      .filter((path) => path.startsWith(SKILLS_DIR_PREFIX))
      .map(skillNameFromPath)
      // F409 D10: refuse an unsafe name before the cap, so refused values take no slots.
      .filter((name) => isSafeMentionValue(name) && name.toLowerCase().includes(query))
      .slice(0, MAX_RESULTS)
      .map((name) => ({ value: name, label: name }))
  }

  // `@` lists the project's specs under Specs, above the workspace files under Files (FR-1).
  const specItems: ComposerTriggerMenuItem[] = resolveSpecResults(trigger.query, specs).map((spec) => ({
    value: `spec:${spec.id}`,
    label: spec.title,
    detail: spec.path,
    group: 'Specs',
    spec: { id: spec.id, title: spec.title },
  }))
  const fileItems: ComposerTriggerMenuItem[] = workspacePaths
    .filter((path) => isSafeMentionValue(path) && path.toLowerCase().includes(query))
    .slice(0, MAX_RESULTS - specItems.length)
    .map((path) => (specItems.length > 0 ? { value: path, label: path, group: 'Files' } : { value: path, label: path }))
  return [...specItems, ...fileItems]
}
