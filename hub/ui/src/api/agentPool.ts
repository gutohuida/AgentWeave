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

/** One entry as a spec task recommends it and a Build chooses it (FR-5, FR-6). */
export interface PoolEntryChoice {
  runner_id: string
  effort: string | null
}
