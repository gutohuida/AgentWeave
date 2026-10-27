import { ProviderMark } from '@/components/common/Icon'
import type { SelectOption } from '@/components/ui/menu'
import type { ProjectSettings } from '@/api/projects'
import type { Runner } from '@/api/runners'
import type { ControlValue, ModelDescriptor } from '@/api/modelCatalog'

/** Values and option builders the settings screens share (kept out of the component files so
 *  Fast Refresh keeps working on them). */

export const PROJECT_DEFAULTS: Pick<
  ProjectSettings,
  | 'hop_budget'
  | 'turn_delivery_cap'
  | 'agent_budget'
  | 'allow_agent_jobs'
  | 'checkpoint_mode'
  | 'checkpoint_auto_continue'
  | 'checks_auto_override'
> = {
  hop_budget: 6,
  turn_delivery_cap: 10,
  agent_budget: 8,
  allow_agent_jobs: true,
  checkpoint_mode: 'offered',
  checkpoint_auto_continue: false,
  checks_auto_override: true,
}

/** What each posture lets an agent do, in a sentence: the menu's second line. */
export const PERMISSION_DETAILS: Record<string, string> = {
  acceptEdits: 'Edits files without asking; asks before running commands.',
  workspace: 'Works freely inside its own workspace; anything beyond it is refused.',
  manual: 'Asks you before every action.',
  bypassPermissions: 'Does anything without asking, outside the workspace too.',
}

export function permissionOptions(values: ControlValue[], unsetLabel: string, unsetDetail: string): SelectOption<string>[] {
  return [
    { value: '', label: unsetLabel, detail: unsetDetail },
    ...values.map((v) => ({ value: v.id, label: v.label, detail: PERMISSION_DETAILS[v.id] })),
  ]
}

export function runnerOptions(runners: Runner[], none: { label: string; detail: string }): SelectOption<string>[] {
  return [
    { value: '', label: none.label, detail: none.detail },
    ...runners.map((r) => ({
      value: r.id,
      label: r.name,
      detail: r.model ?? 'The CLI’s own default model',
      icon: <ProviderMark provider={r.cli} label={r.cli} size={13} />,
    })),
  ]
}

export function modelOptions(models: ModelDescriptor[], runnerLabel = 'Use the runner’s model'): SelectOption<string>[] {
  return [{ value: '', label: runnerLabel }, ...models.map((m) => ({ value: m.id, label: m.label ?? m.id, detail: m.id }))]
}

/** Whole numbers from `min` to `max`, as a validator for `CommittedInput`. */
export function wholeNumber(min: number, max: number, unit: string) {
  return (draft: string): string | null => {
    if (!/^\d+$/.test(draft.trim())) return `A whole number of ${unit}.`
    const n = Number(draft)
    if (n < min) return `At least ${min}.`
    if (n > max) return `At most ${max}.`
    return null
  }
}

/** The charter's Scope line as plain text, or its first paragraph when it has none. */
export function charterSummary(content: string): string {
  const scope = /\*\*Scope:\*\*\s*([\s\S]*?)(?:\n\s*\n|\n#)/.exec(content)
  const raw = scope ? scope[1] : (content.replace(/^#.*$/m, '').trim().split(/\n\s*\n/)[0] ?? '')
  return raw
    .replace(/^>\s?/gm, '')
    .replace(/[*_`#]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** A runner menu whose second line names the model the choice runs on, read from the catalog
 *  (F268: `runnerModelPart`), and the CLI. */
export function runnerChoiceOptions(
  runners: Runner[],
  none: { label: string; detail: string },
  modelPart: (runner: Runner) => string,
): SelectOption<string>[] {
  return [
    { value: '', label: none.label, detail: none.detail },
    ...runners.map((r) => ({
      value: r.id,
      label: r.name,
      detail: `${modelPart(r)} · ${r.cli}`,
      icon: <ProviderMark provider={r.cli} label={r.cli} size={13} />,
    })),
  ]
}

/** A provider's models as menu options: each declared model, then its aliases as "latest"
 *  choices, then a stored value the catalog does not list (kept, so opening the menu never
 *  re-points a working setting at the first option). */
export function catalogModelOptions(
  models: ModelDescriptor[],
  {
    unsetLabel = 'Use the runner’s model',
    stored,
    aliases = true,
  }: { unsetLabel?: string; stored?: string | null; aliases?: boolean } = {},
): SelectOption<string>[] {
  const options: SelectOption<string>[] = [{ value: '', label: unsetLabel }]
  for (const m of models) options.push({ value: m.id, label: m.label ?? m.id, detail: m.id })
  if (aliases) {
    for (const m of models) {
      for (const alias of m.aliases) options.push({ value: alias, label: `${alias}, the latest`, detail: `Now ${m.label}` })
    }
  }
  if (stored && !options.some((o) => o.value === stored)) options.push({ value: stored, label: stored, detail: 'Not in the model catalog' })
  return options
}
