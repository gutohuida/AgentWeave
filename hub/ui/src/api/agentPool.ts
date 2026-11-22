import type { RunnerCli } from './runners'

/**
 * A profile's pool (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`, FR-1):
 * the runners it may run on, each with an optional reasoning effort, exactly one of them the
 * default. Shaped as the agents API is to return it; the routes arrive with the slice's
 * `pool-model` task, and until then only the mock feeds these types.
 */
export interface AgentPoolEntry {
  /** Stable id of the entry, for keys and removal. */
  id: string
  runner_id: string
  /** The runner's own name, as Settings → Runners lists it. */
  runner_name: string
  cli: RunnerCli
  /** The runner's model; null runs the CLI's own default. */
  model: string | null
  /** The catalog's effort value; null leaves it to the CLI. */
  effort: string | null
  default: boolean
}

/** A catalog model to add to a pool, named by provider and model rather than by a runner
 *  (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider`, FR-2): the Hub uses the
 *  project's plain runner for that model, or makes one. */
export interface PoolModelChoice {
  provider: RunnerCli
  model: string
  effort: string | null
}

/** One entry of a pool as `PATCH /agents/{name}` takes it: an entry already there, by its runner,
 *  or a catalog model to add, by provider and model. */
export type PoolEntryWrite =
  | { runner_id: string; effort: string | null; default?: boolean }
  | { provider: RunnerCli; model: string; effort: string | null; default?: boolean }

/** One entry as a spec task recommends it and a Build chooses it (FR-5, FR-6). */
export interface PoolEntryChoice {
  runner_id: string
  effort: string | null
}
