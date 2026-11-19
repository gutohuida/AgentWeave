import type { AgentPoolEntry, PoolEntryChoice } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Runner } from '@/api/runners'

/**
 * The pool's pure rules (spec `a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`):
 * how an entry reads, which efforts it may carry, what an edit is refused for, and which entry a
 * task's run is shown to use. The Hub decides each of these; the page says them first so a refusal
 * is rarely a surprise, and shows the Hub's own words when it is one.
 */

const CLI_LABEL: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', copilot: 'Copilot' }

export function cliLabel(cli: string): string {
  return CLI_LABEL[cli] ?? cli
}

export function modelLabel(catalog: ModelCatalogResponse | undefined, cli: string, model: string | null): string {
  if (!model) return 'Its default model'
  const provider = catalog?.providers.find((p) => p.provider === cli)
  return provider?.models.find((m) => m.id === model || m.aliases.includes(model))?.label ?? model
}

export function effortLabel(catalog: ModelCatalogResponse | undefined, cli: string, effort: string | null): string | null {
  if (!effort) return null
  const control = catalog?.providers.find((p) => p.provider === cli)?.controls.find((c) => c.id === 'effort')
  return control?.values.find((v) => v.id === effort)?.label ?? effort
}

/** "Opus 5.5 · High": the model, then its effort where one is set. The CLI is the mark beside it. */
export function entryLabel(catalog: ModelCatalogResponse | undefined, entry: Pick<AgentPoolEntry, 'cli' | 'model' | 'effort'>): string {
  const effort = effortLabel(catalog, entry.cli, entry.effort)
  return [modelLabel(catalog, entry.cli, entry.model), effort].filter(Boolean).join(' · ')
}

/** The efforts the catalog offers for a runner's CLI; empty when it offers none. */
export function effortsFor(catalog: ModelCatalogResponse | undefined, cli: string): Array<{ id: string; label: string }> {
  return catalog?.providers.find((p) => p.provider === cli)?.controls.find((c) => c.id === 'effort')?.values ?? []
}

export function choiceKey(choice: PoolEntryChoice | null | undefined): string {
  return choice ? `${choice.runner_id}|${choice.effort ?? ''}` : ''
}

export function entryKey(entry: AgentPoolEntry): string {
  return choiceKey(entry)
}

export function findEntry(pool: AgentPoolEntry[], choice: PoolEntryChoice | null | undefined): AgentPoolEntry | undefined {
  const key = choiceKey(choice)
  return key ? pool.find((e) => entryKey(e) === key) : undefined
}

export function defaultEntry(pool: AgentPoolEntry[]): AgentPoolEntry | undefined {
  return pool.find((e) => e.default) ?? pool[0]
}

/** Why adding this entry would be refused (FR-3), or null when it would not be. */
export function addRefusal(
  catalog: ModelCatalogResponse | undefined,
  pool: AgentPoolEntry[],
  runner: Runner | undefined,
  effort: string | null,
): string | null {
  if (!runner) return 'Choose a runner.'
  if (effort && !effortsFor(catalog, runner.cli).some((v) => v.id === effort)) {
    return `${modelLabel(catalog, runner.cli, runner.model ?? null)} does not offer ${effort} effort.`
  }
  if (findEntry(pool, { runner_id: runner.id, effort })) return 'It is already in the list.'
  return null
}

/** Why removing this entry would be refused (FR-3), or null. */
export function removeRefusal(pool: AgentPoolEntry[], entry: AgentPoolEntry): string | null {
  return entry.default && pool.length > 1 ? 'Make another model the default first.' : null
}

export type ResolvedSource = 'chosen' | 'recommended' | 'default'

/**
 * Which entry a task's run uses, in the order FR-7 gives: the operator's choice at Build, then the
 * spec's recommendation when it is in the pool, then the profile's default. `recommendedMissing`
 * is the recommendation the pool does not hold, for the line that says so.
 */
export function resolveEntry(
  pool: AgentPoolEntry[],
  chosen: PoolEntryChoice | null | undefined,
  recommended: PoolEntryChoice | null | undefined,
): { entry: AgentPoolEntry | undefined; source: ResolvedSource; recommendedMissing: boolean } {
  const recommendedEntry = findEntry(pool, recommended)
  const chosenEntry = findEntry(pool, chosen)
  if (chosenEntry) return { entry: chosenEntry, source: 'chosen', recommendedMissing: Boolean(recommended) && !recommendedEntry }
  if (recommendedEntry) return { entry: recommendedEntry, source: 'recommended', recommendedMissing: false }
  return { entry: defaultEntry(pool), source: 'default', recommendedMissing: Boolean(recommended) }
}
