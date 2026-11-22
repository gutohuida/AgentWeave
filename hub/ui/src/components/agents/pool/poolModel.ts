import type { AgentPoolEntry, PoolEntryChoice } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

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

/** Whether a catalog control is part of a pool entry, and so chosen with the entry rather than on
 *  its own pill: the effort (FR-1). */
export function isEntryControl(controlId: string): boolean {
  return controlId === 'effort'
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

/** Why adding this catalog model at this effort would be refused, or null when it would not be.
 *  The pool already holding the model at that effort is refused here, whichever runner holds it:
 *  the operator chose a model, not a runner. */
export function addRefusal(
  catalog: ModelCatalogResponse | undefined,
  pool: AgentPoolEntry[],
  choice: { provider: string; model: string } | null,
  effort: string | null,
): string | null {
  if (!choice) return 'Choose a model.'
  if (effort && !effortsFor(catalog, choice.provider).some((v) => v.id === effort)) {
    return `${modelLabel(catalog, choice.provider, choice.model)} does not offer ${effort} effort.`
  }
  if (pool.some((e) => e.cli === choice.provider && e.model === choice.model && (e.effort ?? null) === effort)) {
    return 'It is already in the list.'
  }
  return null
}

/** Why removing this entry would be refused (FR-3), or null. */
export function removeRefusal(pool: AgentPoolEntry[], entry: AgentPoolEntry): string | null {
  return entry.default && pool.length > 1 ? 'Make another model the default first.' : null
}

/** The conversation override naming the runner of the entry a chat chose (FR-9). The Hub stores an
 *  entry on the default's runner without it, so the chat follows the default. */
export const CHAT_RUNNER_KEY = 'runner_id'

/** The override naming which catalog provider a chat's `model` is (`a-profile-s-pool-and-a-new-
 *  chat-can-use-any-model-of-any-provider`, FR-10). Sent, never stored: the Hub answers it with the
 *  runner it launches on. */
export const CHAT_PROVIDER_KEY = 'provider'

/** What a chat's next turn runs on: a CLI, a model, an effort, and the pool entry it is when it is
 *  one. */
export interface ChatChoice {
  cli: string
  model: string | null
  effort: string | null
  entry?: AgentPoolEntry
}

/** A choice in the chat's model picker: one of the pool's entries, or any catalog model. */
export type ChatPick = { kind: 'entry'; entry: AgentPoolEntry } | { kind: 'model'; provider: string; model: string }

/** Whether two model names are one catalog model of `cli` (an id and its alias are). */
export function sameModel(catalog: ModelCatalogResponse | undefined, cli: string, left: string | null, right: string | null): boolean {
  if (!left || !right) return left === right
  if (left === right) return true
  const models = catalog?.providers.find((p) => p.provider === cli)?.models ?? []
  const find = (name: string) => models.find((m) => m.id === name || m.aliases.includes(name))
  const a = find(left)
  return Boolean(a && a === find(right))
}

/**
 * What a chat's next turn runs on, read from its overrides (FR-3, FR-10): a catalog model it named,
 * else the runner it chose (a pool entry's, or one the Hub made for a model outside the pool, read
 * from `runners`), else the pool's default. The effort is the chat's own where it chose one (FR-6);
 * the default's effort otherwise, which the Hub fills in.
 */
export function chatChoice(
  catalog: ModelCatalogResponse | undefined,
  pool: AgentPoolEntry[],
  overrides: Record<string, string>,
  runners?: Array<{ id: string; cli: string; model?: string | null }>,
): ChatChoice | undefined {
  const chosenEffort = overrides.effort ?? null
  const entryFor = (cli: string, model: string | null, runnerId?: string) => {
    const same = pool.filter((e) => (runnerId ? e.runner_id === runnerId : e.cli === cli && sameModel(catalog, cli, e.model, model)))
    return same.find((e) => (e.effort ?? null) === chosenEffort) ?? same[0]
  }
  const provider = overrides[CHAT_PROVIDER_KEY]
  if (provider && overrides.model) {
    return { cli: provider, model: overrides.model, effort: chosenEffort, entry: entryFor(provider, overrides.model) }
  }
  const runnerId = overrides[CHAT_RUNNER_KEY]
  if (runnerId) {
    const held = entryFor('', null, runnerId)
    if (held) return { cli: held.cli, model: held.model, effort: chosenEffort, entry: held }
    const runner = runners?.find((r) => r.id === runnerId)
    if (runner) return { cli: runner.cli, model: runner.model ?? null, effort: chosenEffort }
  }
  const fallback = defaultEntry(pool)
  if (!fallback) return undefined
  const effort = 'effort' in overrides ? chosenEffort : (fallback.effort ?? null)
  if (overrides.model && !sameModel(catalog, fallback.cli, overrides.model, fallback.model)) {
    return { cli: fallback.cli, model: overrides.model, effort, entry: entryFor(fallback.cli, overrides.model) }
  }
  return { cli: fallback.cli, model: fallback.model, effort, entry: fallback }
}

/**
 * The overrides that make *pick* the chat's choice (FR-3, FR-6). An entry is chosen by its runner
 * and brings its effort; a catalog model by its provider and id, keeping the chosen effort where
 * its provider offers it. Whatever model, runner and provider were chosen before are replaced;
 * every other control stays.
 */
export function chatPickOverrides(
  catalog: ModelCatalogResponse | undefined,
  overrides: Record<string, string>,
  pick: ChatPick,
): Record<string, string> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { model, effort, [CHAT_RUNNER_KEY]: runner, [CHAT_PROVIDER_KEY]: provider, ...rest } = overrides
  if (pick.kind === 'entry') {
    const entry = pick.entry
    return { ...rest, [CHAT_RUNNER_KEY]: entry.runner_id, ...(entry.effort ? { effort: entry.effort } : {}) }
  }
  const out: Record<string, string> = { ...rest, [CHAT_PROVIDER_KEY]: pick.provider, model: pick.model }
  if (effort && effortsFor(catalog, pick.provider).some((v) => v.id === effort)) out.effort = effort
  return out
}

/** The overrides with the chat's effort set to *effort*, or cleared back to the usual one (FR-6).
 *  The runner the chat is on is not moved. */
export function chatEffortOverrides(overrides: Record<string, string>, effort: string | null): Record<string, string> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { effort: _was, ...rest } = overrides
  return effort ? { ...rest, effort } : rest
}

/** The entry a chat's next turn runs on, when it is one of the pool's (FR-9). */
export function chatEntry(pool: AgentPoolEntry[], overrides: Record<string, string>): AgentPoolEntry | undefined {
  return chatChoice(undefined, pool, overrides)?.entry
}

/** The overrides that choose *entry* in a chat. */
export function chatChoiceOverrides(overrides: Record<string, string>, entry: AgentPoolEntry): Record<string, string> {
  return chatPickOverrides(undefined, overrides, { kind: 'entry', entry })
}

/** The CLI a conversation started on, for the picker's greyed-out entries: the one its latest run
 *  recorded, else the default's when it has a session (a run that predates the record ran on the
 *  agent's runner); null before its first turn. */
export function chatStartedOn(
  pool: AgentPoolEntry[],
  conversation: { started_cli?: string | null; provider_session_id?: string | null } | undefined,
): string | null {
  if (!conversation) return null
  if (conversation.started_cli) return conversation.started_cli
  return conversation.provider_session_id ? (defaultEntry(pool)?.cli ?? null) : null
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
