import * as React from 'react'
import type { ProjectCheckpointList } from '@/api/checkpoints'
import { CheckpointsPage } from '@/components/checkpoints/CheckpointsPage'
import { NO_FILTERS, type CheckpointFilters } from '@/components/checkpoints/checkpointModel'
import type { ScreenProps } from '../routes'
import { AGENTS, CHECKPOINTS, CONVERSATIONS, LABELS, NOTES } from '../checkpointsMock'

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
