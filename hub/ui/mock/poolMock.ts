/** The profile-pool slice's mock data (spec `a-profile-runs-each-task-on-a-runner-and-model-chosen-
 *  from-its-pool`). Everything here is `// mock state`: no Hub records a pool yet, and the tracked
 *  fixture stubs carry no catalog or runners. The catalog mirrors the Hub's built-in one
 *  (`hub/hub/model_catalog.py`), cut to the models this project runs; the tasks are the slice's own
 *  seven, with the recommendations its document gives, plus one the pool does not hold. */
import type { AgentPoolEntry, PoolEntryChoice } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Runner } from '@/api/runners'
import type { SpecRecommendedBuild } from '@/api/spec'
import type { BuildPlanAgent, BuildPlanTask } from '@/components/spec/BuildPlanDialog'

const effort = (ids: string[]) => ({
  id: 'effort',
  label: 'Effort',
  kind: 'enum' as const,
  // The Hub's `_enum` labels are the id capitalised ("Xhigh"); kept as it sends them.
  values: ids.map((id) => ({ id, label: id.charAt(0).toUpperCase() + id.slice(1) })),
  default: 'medium',
  apply: { style: 'flag' as const, template: '--effort {value}' },
})

export const POOL_CATALOG: ModelCatalogResponse = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [
        { id: 'claude-opus-5-5', label: 'Opus 5.5', aliases: ['opus'], context_window: 1_000_000, default: false },
        { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', aliases: ['sonnet'], context_window: 1_000_000, default: true },
        { id: 'claude-haiku-5-5', label: 'Haiku 5.5', aliases: ['haiku'], context_window: 1_000_000, default: false },
      ],
      controls: [effort(['low', 'medium', 'high', 'xhigh', 'max'])],
    },
    {
      provider: 'codex',
      label: 'Codex CLI',
      models: [
        { id: 'gpt-6.1-sol', label: 'GPT-6.1-Sol', aliases: [], context_window: 272_000, default: true },
        { id: 'gpt-6-luna', label: 'GPT-6-Luna', aliases: [], context_window: 272_000, default: false },
      ],
      controls: [effort(['low', 'medium', 'high', 'xhigh'])],
    },
  ],
}

const runner = (id: string, name: string, cli: Runner['cli'], model: string): Runner => ({
  id,
  project_id: 'proj-d85a82bf4216',
  name,
  cli,
  model,
  flags: null,
  provider_config: null,
  created_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-01T09:00:00Z',
  model_unrecognised: false,
})

export const POOL_RUNNERS: Runner[] = [
  runner('runner-opus', 'claude-opus', 'claude', 'claude-opus-5-5'),
  runner('runner-sonnet', 'claude-sonnet', 'claude', 'claude-sonnet-5-5'),
  runner('runner-haiku', 'claude-haiku', 'claude', 'claude-haiku-5-5'),
  runner('runner-sol', 'codex-sol', 'codex', 'gpt-6.1-sol'),
  runner('runner-luna', 'codex-luna', 'codex', 'gpt-6-luna'),
]

let seq = 0
export function poolEntry(runnerId: string, effortId: string | null, isDefault = false): AgentPoolEntry {
  const r = POOL_RUNNERS.find((x) => x.id === runnerId)!
  seq += 1
  return { id: `pool-${seq}`, runner_id: r.id, runner_name: r.name, cli: r.cli, model: r.model ?? null, effort: effortId, default: isDefault }
}

/** One profile per role, as the roadmap's fold-the-roster slice would leave the team: Developer
 *  can run on five entries, the checkers on two each, Architect on one. */
export const POOLS: Record<string, AgentPoolEntry[]> = {
  Developer: [
    poolEntry('runner-sonnet', null, true),
    poolEntry('runner-haiku', null),
    poolEntry('runner-opus', null),
    poolEntry('runner-opus', 'high'),
    poolEntry('runner-sol', 'high'),
  ],
  QA: [poolEntry('runner-opus', null, true), poolEntry('runner-opus', 'high')],
  QA2: [poolEntry('runner-sonnet', null, true), poolEntry('runner-opus', null)],
  Architect: [poolEntry('runner-opus', 'high', true)],
}

const MODEL_OF: Record<string, string> = { Developer: 'Sonnet 5.5 and 4 more', QA: 'Opus 5.5 and 1 more', QA2: 'Sonnet 5.5 and 1 more', Architect: 'Opus 5.5 · High' }
export const POOL_AGENTS: BuildPlanAgent[] = ['Developer', 'QA', 'QA2', 'Architect'].map((name, i) => ({ name, detail: MODEL_OF[name], colorIndex: i }))

export const POOL_TASKS: BuildPlanTask[] = [
  { key: 'acceptance-drive', title: 'Acceptance drive: two models in one build' },
  { key: 'pool-model', title: 'Profile pools: model, migration, API' },
  { key: 'spec-and-build-choice', title: 'Per-task entry in spec tasks and Build' },
  { key: 'launch-path', title: 'Runs launch with their chosen entry' },
  { key: 'chats-and-holds', title: 'Chats pick from the pool; holds per CLI' },
  { key: 'pool-settings-ui', title: 'Edit a profile’s pool in settings' },
  { key: 'drive-run', title: 'Run the acceptance drive on the built slice' },
]

const opus: PoolEntryChoice = { runner_id: 'runner-opus', effort: null }
const opusHigh: PoolEntryChoice = { runner_id: 'runner-opus', effort: 'high' }
const sonnet: PoolEntryChoice = { runner_id: 'runner-sonnet', effort: null }

export const POOL_RECOMMENDED: SpecRecommendedBuild = {
  mode: 'flow',
  agent: 'Developer',
  reviewer: null,
  tester: null,
  cron: '*/5 * * * *',
  stop_when_queue_empties: true,
  stop_at: null,
  driver: 'flow',
  level: 'reviewed',
  builder: 'Developer',
  checker: 'QA',
  landing: 'main',
  task_builders: Object.fromEntries(POOL_TASKS.map((t) => [t.key, 'Developer'])),
  task_checkers: {
    'acceptance-drive': 'QA',
    'pool-model': 'QA',
    'spec-and-build-choice': 'QA2',
    'launch-path': 'QA',
    'chats-and-holds': 'QA2',
    'pool-settings-ui': 'QA2',
    'drive-run': 'QA',
  },
  task_builder_entries: {
    'acceptance-drive': opus,
    'pool-model': opus,
    'spec-and-build-choice': opus,
    // mock state: a recommendation Developer's pool does not hold, so its row says so.
    'launch-path': { runner_id: 'runner-opus', effort: 'max' },
    'chats-and-holds': opus,
    'pool-settings-ui': sonnet,
    // mock state: no recommendation, so the default (Sonnet) is shown.
    'drive-run': null,
  },
  task_checker_entries: {
    'acceptance-drive': opusHigh,
    'pool-model': opusHigh,
    'spec-and-build-choice': opus,
    'launch-path': opusHigh,
    'chats-and-holds': opus,
    'pool-settings-ui': opus,
    'drive-run': opus,
  },
  task_reasons: {
    'acceptance-drive': { builder: 'The baseline is evidence the reviewer judges; Opus has fewer evidence-only send-backs here.', checker: 'Checks that every baseline check fails for the right reason.' },
    'pool-model': { builder: 'A migration on live data: Opus, with a third of Sonnet’s defect send-backs here.', checker: 'Opus at high effort for a Tier 2 migration.' },
    'spec-and-build-choice': { builder: 'A contract across the spec schema, the Build route and the dialog.' },
    'launch-path': { builder: 'The code that starts every run: the highest-hazard task.', checker: 'Opus at high effort for the launch path.' },
    'chats-and-holds': { builder: 'Hold keys reach the scheduler’s offer and start gates.' },
    'pool-settings-ui': { builder: 'A self-contained settings form on an existing API: routine for Sonnet.', checker: 'Opus to catch what Sonnet’s send-back rate predicts.' },
    'drive-run': {},
  },
  reasons: {
    mode: 'Several tasks with a migration and a launch-path change; a flow runs the independent ones in parallel.',
    stop: 'Stop when the queue empties: the slice is finite.',
    checker: 'A different profile checks, as independence requires.',
  },
}
