import type { Job, LoopSummary } from '@/api/jobs'
import type { SpecBuild } from '@/api/spec'
import type { RunningBuildInput } from '@/components/panel/runningModel'
import { jobs as fixtureJobs, PROJECT_ID } from './fixtures'

// mock state: the replica's two loops are both finished builds, so the Running tab's other states
// (a build working, one waiting on the operator, a stalled loop, a loop between firings, a
// scheduled job, a paused one, a build stopped early) are written here by hand. The clock is
// MOCK_NOW, 2026-10-17 12:10 UTC.

function loop(id: string, label: string, over: Partial<LoopSummary>): LoopSummary {
  return {
    id,
    label,
    agent: 'Builder',
    purpose: '',
    stop_when_queue_empties: true,
    queue: {},
    current_tasks: [],
    stall_reason: null,
    open_questions: 0,
    firing_active: false,
    ending_state: null,
    ...over,
  }
}

function build(id: string, over: Partial<SpecBuild>): SpecBuild {
  return {
    id,
    state: 'running',
    driver: 'flow',
    level: 'reviewed',
    builders: ['Builder'],
    reviewers: ['QA1'],
    lead: null,
    budget_cap_usd: null,
    spent_usd: null,
    unpriced_turns: 0,
    window_start: null,
    window_end: null,
    landing: 'main',
    loop_id: null,
    stop_reason: null,
    created_at: null,
    stopped_at: null,
    ...over,
  }
}

const working = loop('loop-mock-terra', 'Terra agent control center', {
  queue: { approved: 3, in_progress: 1, under_review: 1, assigned: 2 },
  firing_active: true,
  current_tasks: [
    { id: 't1', title: 'Desktop window and projects', status: 'in_progress', agent: 'Builder', agent_capacity: 'working' },
    { id: 't2', title: 'Plugins per project and rescan', status: 'under_review', agent: 'QA1', agent_capacity: 'working' },
    { id: 't3', title: 'Tray icon and notifications', status: 'assigned', agent: 'QA2', agent_capacity: 'next' },
  ],
})

const asking = loop('loop-mock-cairn-setup', 'Cairn interactive setup and skill selection', {
  queue: { approved: 1, in_progress: 1, assigned: 3 },
  open_questions: 1,
  current_tasks: [{ id: 't4', title: 'Skill picker in the setup wizard', status: 'in_progress', agent: 'Builder', agent_capacity: 'held' }],
})

const stopped = loop('loop-mock-export', 'Export the ledger as CSV', {
  queue: { approved: 2, assigned: 2 },
  ending_state: 'stopped',
  stop_reason: 'Stopped at its $5.00 budget, with 2 tasks left',
  stopped_at: '2026-10-16T18:40:00Z',
})

export const RUNNING_BUILDS: RunningBuildInput[] = [
  {
    number: 2,
    documentTitle: 'Terra agent control center',
    build: build('build-mock-terra', { loop_id: working.id, created_at: '2026-10-17T09:55:00Z', spent_usd: 4.2, builders: ['Builder'], reviewers: ['QA1', 'QA2'] }),
    loop: working,
  },
  {
    number: 1,
    documentTitle: 'Cairn interactive setup and skill selection',
    build: build('build-mock-cairn-setup', { loop_id: asking.id, created_at: '2026-10-17T11:20:00Z', spent_usd: 1.35 }),
    loop: asking,
  },
  {
    number: 1,
    documentTitle: 'Export the ledger as CSV',
    build: build('build-mock-export', { state: 'stopped', loop_id: stopped.id, created_at: '2026-10-16T14:00:00Z', stopped_at: stopped.stopped_at, stop_reason: stopped.stop_reason, spent_usd: 5 }),
    loop: stopped,
  },
  // The replica's own finished builds, from its recorded loops.
  ...fixtureJobs
    .filter((j) => j.loop)
    .map((j, i) => ({
      number: 1,
      documentTitle: j.loop!.label,
      build: build(`build-mock-done-${i}`, {
        state: 'finished' as const,
        loop_id: j.loop!.id,
        created_at: j.created_at,
        stopped_at: j.loop!.stopped_at ?? j.last_run ?? null,
        spent_usd: i === 0 ? 3.1 : 6.45,
      }),
      loop: j.loop!,
    })),
]

export const RUNNING_LOOPS: LoopSummary[] = [
  ...fixtureJobs.filter((j) => j.loop).map((j) => j.loop!),
  loop('loop-mock-sweep', 'Backlog sweep', {
    agent: 'QA2',
    queue: { approved: 4, assigned: 3 },
    stall_reason: 'QA2 is paused, so nobody can take the next task',
  }),
  loop('loop-mock-docs', 'Docs tidy-up', {
    agent: 'Architect',
    stop_when_queue_empties: true,
    queue: { approved: 2, assigned: 3 },
  }),
]

function job(id: string, name: string, over: Partial<Job>): Job {
  return {
    id,
    project_id: PROJECT_ID,
    name,
    agent: 'QA1',
    message: '',
    cron: '0 2 * * *',
    session_mode: 'new',
    enabled: true,
    source: 'hub',
    created_at: '2026-10-10T09:00:00Z',
    run_count: 0,
    archived_at: null,
    loop: null,
    ...over,
  }
}

export const RUNNING_JOBS: Job[] = [
  ...fixtureJobs,
  job('job-mock-docs', 'Docs tidy-up', {
    agent: 'Architect',
    cron: '*/30 * * * *',
    next_run: '2026-10-17T12:14:00Z',
    created_at: '2026-10-17T08:00:00Z',
    loop: RUNNING_LOOPS.find((l) => l.id === 'loop-mock-docs')!,
  }),
  job('job-mock-drift', 'Nightly drift scan', { last_run: '2026-10-17T02:00:00Z', next_run: '2026-10-18T02:00:00Z', run_count: 6 }),
  job('job-mock-digest', 'Morning digest', {
    agent: 'Architect',
    cron: '0 7 * * 1-5',
    last_run: '2026-10-17T07:00:00Z',
    next_run: '2026-10-20T07:00:00Z',
    run_count: 9,
    history: [{ id: 'run-mock-1', job_id: 'job-mock-digest', fired_at: '2026-10-17T12:08:00Z', status: 'in_progress', trigger: 'manual' }],
  }),
  job('job-mock-cost', 'Weekly cost report', { enabled: false, cron: '0 9 * * 1', last_run: '2026-10-13T09:00:00Z', run_count: 3 }),
]
