import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAgents } from '@/api/agents'
import { conversationLabel as labelOf, useProjectConversations, type AgentConversation } from '@/api/agentChat'
import { startFromCheckpoint, useCheckpointNotes, useProjectCheckpoints } from '@/api/checkpoints'
import { useConfigStore } from '@/store/configStore'
import { checkpointsDestination, goTo } from '@/lib/navigation'
import { LoadingThread } from '@/components/common/LoadingThread'
import { QueryErrorNotice, type QueryFailure } from '@/components/common/QueryErrorNotice'
import { CheckpointsPanel } from './CheckpointsPanel'

/** Whose checkpoints are listed: one thread's (its side panel's tab) or one profile's (its page). */
export type CheckpointsScope = { conversationId: string } | { agent: string }

/**
 * `CheckpointsPanel` wired to the Hub, for a thread's Checkpoints tab and a profile's Checkpoints
 * section (leaner-navigation FR-8, FR-9). Reads what the retired Checkpoints screen read for the
 * opened checkpoint (its carried notes, the raw answer on request, the profiles a thread can start
 * with), so the detail shows every section that screen did.
 *
 * A checkpoint this list does not hold (a link to the one a thread started from) belongs to another
 * thread, so opening it goes to that thread's side panel rather than to nothing (FR-10).
 */
export function CheckpointsPanelContainer({
  scope,
  openedId,
  onOpen,
  onOpenConversation,
  emptyText,
}: {
  scope: CheckpointsScope
  openedId: string | null
  onOpen: (checkpointId: string | null) => void
  onOpenConversation: (agent: string, conversationId: string) => void
  emptyText?: string
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const queryClient = useQueryClient()
  const list = useProjectCheckpoints('agent' in scope ? { agent: scope.agent } : { conversationId: scope.conversationId })
  const checkpoints = useMemo(() => list.data?.checkpoints ?? [], [list.data])
  const opened = openedId ? (checkpoints.find((checkpoint) => checkpoint.id === openedId) ?? null) : null

  const openAgents = useAgents('open')
  const open = useProjectConversations(projectId, 'open')
  const archived = useProjectConversations(projectId, 'archived')
  const conversations = useMemo<AgentConversation[]>(
    () => [...(open.data?.conversations ?? []), ...(archived.data?.conversations ?? [])],
    [open.data, archived.data],
  )
  const byId = useMemo(() => new Map(conversations.map((c) => [c.id, c])), [conversations])
  const conversationLabel = (id: string) => {
    const known = byId.get(id)
    return known ? labelOf(known) : 'An earlier thread'
  }
  const startAgents = useMemo(() => (openAgents.data ?? []).map((agent) => agent.name).sort(), [openAgents.data])

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

  const failures: QueryFailure[] = [
    ['the checkpoints', list.error, () => list.refetch()],
    ['the profiles a thread can start with', openAgents.error, () => openAgents.refetch()],
    ['the open threads', open.error, () => open.refetch()],
    ['the archived threads', archived.error, () => archived.refetch()],
    ['the profile notes it carried', notes.error, () => notes.refetch()],
    ['what the model returned', raw.error, () => raw.refetch()],
  ]

  if (list.isLoading) return <LoadingThread label="Loading checkpoints" />
  return (
    <>
      <QueryErrorNotice failures={failures} />
      <CheckpointsPanel
        checkpoints={checkpoints}
        openedId={openedId}
        onOpen={(id) => {
          if (id && !checkpoints.some((checkpoint) => checkpoint.id === id) && projectId) {
            goTo(checkpointsDestination(projectId, { checkpoint: id }))
            return
          }
          onOpen(id)
        }}
        conversationLabel={conversationLabel}
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
        startAgents={startAgents}
        emptyText={emptyText}
      />
    </>
  )
}
