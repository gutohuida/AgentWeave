import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAgents } from '@/api/agents'
import { conversationLabel as labelOf, useProjectConversations, type AgentConversation } from '@/api/agentChat'
import { startFromCheckpoint, useCheckpointNotes, useProjectCheckpoints } from '@/api/checkpoints'
import { useConfigStore } from '@/store/configStore'
import { checkpointsDestination, type ProjectTabDestination } from '@/lib/navigation'
import { QueryErrorNotice, type QueryFailure } from '@/components/common/QueryErrorNotice'
import { CheckpointsPage } from './CheckpointsPage'
import { routeFilters, type CheckpointFilters } from './checkpointModel'

/**
 * The Checkpoints tab, wired to the Hub. The address (`destination`) holds what is opened and how
 * the list is narrowed, so a link, a reload and the back button all land where the operator was.
 */
export function CheckpointsScreen({
  destination,
  onNavigate,
  onOpenConversation,
}: {
  destination: ProjectTabDestination
  onNavigate: (destination: ProjectTabDestination) => void
  onOpenConversation: (agent: string, conversationId: string) => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const queryClient = useQueryClient()
  const filters: CheckpointFilters = {
    agent: destination.checkpointAgent ?? '',
    trigger: destination.checkpointTrigger ?? '',
    conversationId: destination.checkpointConversation ?? '',
  }
  const selectedId = destination.checkpoint ?? null

  const list = useProjectCheckpoints(routeFilters(filters))
  const checkpoints = useMemo(() => list.data?.checkpoints ?? [], [list.data])
  const inList = selectedId ? checkpoints.find((checkpoint) => checkpoint.id === selectedId) : null
  // A link to a checkpoint the narrowing hides still opens it: it is read from the whole list.
  const whole = useProjectCheckpoints({}, { enabled: Boolean(selectedId) && !inList && !list.isLoading })
  const opened = inList ?? whole.data?.checkpoints.find((checkpoint) => checkpoint.id === selectedId) ?? null

  const agents = useAgents('all')
  const open = useProjectConversations(projectId, 'open')
  const archived = useProjectConversations(projectId, 'archived')
  const conversations = useMemo<AgentConversation[]>(
    () => [...(open.data?.conversations ?? []), ...(archived.data?.conversations ?? [])],
    [open.data, archived.data],
  )
  const byId = useMemo(() => new Map(conversations.map((c) => [c.id, c])), [conversations])
  const conversationLabel = (id: string) => {
    const known = byId.get(id)
    return known ? labelOf(known) : 'An earlier conversation'
  }
  const agentNames = useMemo(() => {
    const names = new Set((agents.data ?? []).map((agent) => agent.name))
    for (const checkpoint of checkpoints) names.add(checkpoint.agent)
    return [...names].sort()
  }, [agents.data, checkpoints])
  const conversationOptions = conversations
    .filter((c) => !filters.agent || c.agent === filters.agent)
    .map((c) => ({ id: c.id, label: labelOf(c) }))

  const notes = useCheckpointNotes(opened?.conversation_id ?? null, Boolean(opened))
  const carried = (notes.data?.notes ?? []).filter((note) => opened && note.consumed_by_checkpoint_id === opened.id)

  const [rawFor, setRawFor] = useState<string | null>(null)
  const raw = useProjectCheckpoints(
    { conversationId: opened?.conversation_id, includeRaw: true },
    { enabled: Boolean(opened) && rawFor === opened?.id },
  )
  const rawAnswer = rawFor === opened?.id
    ? raw.data?.checkpoints.find((checkpoint) => checkpoint.id === opened?.id)?.unreadable_answer ?? null
    : null

  const go = (next: Partial<{ checkpoint: string | null } & CheckpointFilters>) => {
    const merged = { ...filters, checkpoint: selectedId, ...next }
    onNavigate(
      checkpointsDestination(destination.projectId, {
        checkpoint: merged.checkpoint,
        agent: merged.agent,
        trigger: merged.trigger,
        conversation: merged.conversationId,
      }),
    )
  }

  const failures: QueryFailure[] = [
    ['the checkpoints', list.error, () => list.refetch()],
    ['the checkpoint being opened', whole.error, () => whole.refetch()],
    ['the agents', agents.error, () => agents.refetch()],
    ['the open conversations', open.error, () => open.refetch()],
    ['the archived conversations', archived.error, () => archived.refetch()],
    ['the agent notes it carried', notes.error, () => notes.refetch()],
    ['what the model returned', raw.error, () => raw.refetch()],
  ]

  return (
    <>
    <QueryErrorNotice failures={failures} />
    <CheckpointsPage
      checkpoints={checkpoints}
      lineage={list.data?.lineage ?? null}
      filters={filters}
      onFilters={(next) => go(next)}
      agents={agentNames}
      conversations={conversationOptions}
      conversationLabel={conversationLabel}
      selectedId={selectedId}
      opened={opened}
      onSelect={(checkpoint) => go({ checkpoint })}
      notes={carried}
      rawAnswer={rawAnswer}
      onShowRaw={(id) => setRawFor(id)}
      onOpenConversation={(agent, conversationId) => {
        const owner = agent ?? byId.get(conversationId)?.agent ?? opened?.agent
        if (owner) onOpenConversation(owner, conversationId)
      }}
      onStart={async (checkpointId, agent, message) => {
        if (!projectId) return
        const started = await startFromCheckpoint(projectId, checkpointId, agent, message)
        await queryClient.invalidateQueries({ queryKey: ['project', projectId, 'checkpoints'] })
        await queryClient.invalidateQueries({ queryKey: ['project', projectId, 'conversations'] })
        onOpenConversation(started.agent, started.conversation_id)
      }}
      loading={list.isLoading}
      error={list.isError}
    />
    </>
  )
}
