import * as React from 'react'
import type { CheckpointNote, ProjectCheckpoint, ProjectCheckpointList } from '@/api/checkpoints'
import { CheckpointsPage } from '@/components/checkpoints/CheckpointsPage'
import { NO_FILTERS, type CheckpointFilters } from '@/components/checkpoints/checkpointModel'
import type { ScreenProps } from '../routes'

/** mock state: the fixtures are written by hand to show every case the screen words (each trigger,
 *  each status, a title the Hub made from the body and one from its facts, a probe that found
 *  files missing, a carried-over pair, a checkpoint with no covered runs, one with every detail).
 *  The shapes are the route's (`ProjectCheckpoint`); the components are the app's. */
const BODY = `## Objective

Make the dashboard's checkpoint list readable at a glance.

## Current state

- The list route returns every checkpoint, newest first.
- The tab is being built as real components.

## Decisions

- Triggers are shown in plain words, never the Hub's identifiers.
- A title the Hub made says so.

## Next actions

1. Wire the tab to the route.
2. Run the acceptance drive.
`

const run = (n: number, agent: string, at: string) => ({
  run_id: `run-${agent.toLowerCase()}-${n}`,
  agent,
  status: 'completed',
  started_at: at,
  ended_at: at,
})

const base = {
  probe_status: 'passed',
  probe_findings: null,
  previous_checkpoint_id: null,
  files_changed: null,
  open_questions: null,
  citations: null,
  generation_error: null,
  cut_over_to_conversation_id: null,
  has_unreadable_answer: false,
  unreadable_answer: null,
  title_made_by: 'model',
  title_reason: null,
  carried_from: null,
  carried_into: null,
} satisfies Partial<ProjectCheckpoint>

const CHECKPOINTS: ProjectCheckpoint[] = [
  {
    ...base,
    id: 'ckpt-7',
    conversation_id: 'conv-b2',
    agent: 'Builder',
    trigger: 'operator',
    status: 'ready',
    lineage_id: 'l7',
    title: 'Checkpoints tab wired to the route',
    summary: 'The tab lists every checkpoint with its filters. The acceptance drive is next.',
    body: BODY,
    created_at: '2026-10-17T12:02:00Z',
    files_changed: ['hub/ui/src/components/checkpoints/CheckpointsPage.tsx', 'hub/ui/src/styles/checkpoints.css'],
    open_questions: [{ id: 'q1', question: 'Should the tab remember its last narrowing?' }],
    citations: [{ id: 'c1', preview: 'Operator, 2026-11-04: a new project tab, judged in the mock.' }],
    covered_runs: [run(1, 'Builder', '2026-10-17T11:20:00Z'), run(2, 'Builder', '2026-10-17T11:41:00Z'), run(3, 'Builder', '2026-10-17T11:58:00Z')],
    carried_from: { checkpoint_id: 'ckpt-4', conversation_id: 'conv-b1', title: 'Routes list checkpoints across conversations' },
  },
  {
    ...base,
    id: 'ckpt-6',
    conversation_id: 'conv-q1',
    agent: 'QA',
    trigger: 'task_completion',
    status: 'ready',
    lineage_id: 'l6',
    title: 'Fill pass reviewed, one defect found',
    summary: 'The one-time fill passes its tests. A checkpoint with no body is titled from the Hub’s facts.',
    body: BODY,
    created_at: '2026-10-17T11:30:00Z',
    covered_runs: [run(1, 'QA', '2026-10-17T11:00:00Z')],
  },
  {
    ...base,
    id: 'ckpt-5',
    conversation_id: 'conv-b3',
    agent: 'Builder',
    trigger: 'context_pressure',
    status: 'failed',
    lineage_id: 'l5',
    title: 'Generation asks twice before falling back',
    summary: 'Both answers lacked a title, so the Hub made one from the first words of the body.',
    title_made_by: 'hub_from_body',
    title_reason: 'Both answers were rejected: the first had no title, the second had a summary of 412 characters (the limit is 300).',
    probe_status: 'failed',
    probe_findings: [{ dimension: 'files_changed', missing: ['hub/hub/checkpoint_fill.py'], invented: ['hub/hub/fill.py'] }],
    body: BODY,
    created_at: '2026-10-17T10:40:00Z',
    covered_runs: [run(1, 'Builder', '2026-10-17T10:00:00Z'), run(2, 'Builder', '2026-10-17T10:30:00Z')],
  },
  {
    ...base,
    id: 'ckpt-4',
    conversation_id: 'conv-b1',
    agent: 'Builder',
    trigger: 'operator',
    status: 'ready',
    lineage_id: 'l4',
    title: 'Routes list checkpoints across conversations',
    summary: 'The project route lists every checkpoint with filters. The conversation was carried over into a successor.',
    body: BODY,
    created_at: '2026-10-16T17:10:00Z',
    cut_over_to_conversation_id: 'conv-b2',
    carried_into: { conversation_id: 'conv-b2' },
    covered_runs: [run(1, 'Builder', '2026-10-16T16:30:00Z'), run(2, 'Builder', '2026-10-16T16:55:00Z')],
  },
  {
    ...base,
    id: 'ckpt-3',
    conversation_id: 'conv-q2',
    agent: 'QA',
    trigger: 'context_pressure',
    status: 'unwritten',
    lineage_id: 'l3',
    title: 'QA, the conversation grew long, Oct 16',
    summary: 'Made from the agent, the reason and the date: neither answer could be read.',
    title_made_by: 'hub_from_facts',
    title_reason: 'Neither answer could be read: the first was plain prose with no sections, and the second timed out.',
    has_unreadable_answer: true,
    body: null,
    created_at: '2026-10-16T15:02:00Z',
    covered_runs: [],
  },
  {
    ...base,
    id: 'ckpt-2',
    conversation_id: 'conv-a1',
    agent: 'Architect',
    trigger: 'handoff_requested',
    status: 'ready',
    lineage_id: 'l2',
    title: 'Roadmap slice scoped',
    summary: 'This one was taken for a reason the screen has no wording for; it still reads.',
    body: BODY,
    created_at: '2026-10-16T09:12:00Z',
    probe_status: null,
    covered_runs: [],
  },
]

const NOTES: CheckpointNote[] = [
  {
    id: 'note-1',
    agent: 'Builder',
    run_id: 'run-builder-3',
    intent: 'Keep the list route’s order; the tab relies on it.',
    suspicions: ['The archived filter may hide the successor'],
    warnings: [],
    consumed_by_checkpoint_id: 'ckpt-7',
    created_at: '2026-10-17T11:59:00Z',
  },
]

const CONVERSATIONS = [
  { id: 'conv-b2', label: 'Wire the Checkpoints tab', agent: 'Builder' },
  { id: 'conv-b3', label: 'Generation fallback', agent: 'Builder' },
  { id: 'conv-b1', label: 'Routes for checkpoints', agent: 'Builder' },
  { id: 'conv-q1', label: 'Review of the fill pass', agent: 'QA' },
  { id: 'conv-q2', label: 'Review of generation', agent: 'QA' },
  { id: 'conv-a1', label: 'Roadmap scoping', agent: 'Architect' },
]
const LABELS = new Map(CONVERSATIONS.map((c) => [c.id, c.label]))
const AGENTS = ['Architect', 'Builder', 'QA']

export default function Checkpoints({ now }: ScreenProps) {
  const [filters, setFilters] = React.useState<CheckpointFilters>(NO_FILTERS)
  const [selected, setSelected] = React.useState<string | null>('ckpt-7')
  const [raw, setRaw] = React.useState(false)

  const shown = CHECKPOINTS.filter(
    (c) =>
      (!filters.agent || c.agent === filters.agent) &&
      (!filters.trigger || c.trigger === filters.trigger) &&
      (!filters.conversationId || c.conversation_id === filters.conversationId),
  )
  const opened = CHECKPOINTS.find((c) => c.id === selected) ?? null
  const lineage: ProjectCheckpointList['lineage'] = filters.conversationId === 'conv-b2'
    ? {
        conversation_id: 'conv-b2',
        started_from: { checkpoint_id: 'ckpt-4', conversation_id: 'conv-b1', title: 'Routes list checkpoints across conversations' },
        carried_into: null,
      }
    : null

  return (
    <CheckpointsPage
      checkpoints={shown}
      lineage={lineage}
      filters={filters}
      onFilters={setFilters}
      agents={AGENTS}
      conversations={CONVERSATIONS.filter((c) => !filters.agent || c.agent === filters.agent)}
      conversationLabel={(id) => LABELS.get(id) ?? 'An earlier conversation'}
      selectedId={selected}
      opened={opened}
      onSelect={(id) => {
        setSelected(id)
        setRaw(false)
      }}
      notes={NOTES.filter((n) => n.consumed_by_checkpoint_id === selected)}
      rawAnswer={raw && selected === 'ckpt-3' ? 'Here is a summary of the conversation: the builder wired the route and the QA agent reviewed it.' : null}
      onShowRaw={() => setRaw(true)}
      onOpenConversation={(_, id) => setFilters({ ...NO_FILTERS, conversationId: id })}
      now={now}
    />
  )
}
