import { create } from 'zustand'
import { cutOver, takeCheckpoint, type CutoverResult } from '@/api/checkpoints'
import { readableApiError } from '@/api/client'

export type CheckpointOperation = {
  projectId: string
  conversationId: string
  status: 'writing' | 'succeeded' | 'failed'
  message: string
  successorConversationId?: string
  startedAt: number
}

type CheckpointOperationState = {
  operations: Record<string, CheckpointOperation>
  setOperation: (key: string, operation: CheckpointOperation) => void
  dismiss: (key: string) => void
}

export const checkpointOperationKey = (projectId: string, conversationId: string) =>
  `${projectId}:${conversationId}`

export const useCheckpointOperationStore = create<CheckpointOperationState>((set) => ({
  operations: {},
  setOperation: (key, operation) =>
    set((state) => ({ operations: { ...state.operations, [key]: operation } })),
  dismiss: (key) =>
    set((state) => {
      const operations = { ...state.operations }
      delete operations[key]
      return { operations }
    }),
}))

const inFlight = new Map<string, Promise<CutoverResult | null>>()

export function writeCheckpoint(
  projectId: string,
  conversationId: string,
): Promise<CutoverResult | null> {
  const key = checkpointOperationKey(projectId, conversationId)
  const existing = inFlight.get(key)
  if (existing) return existing

  const startedAt = Date.now()
  const update = (operation: Omit<CheckpointOperation, 'projectId' | 'conversationId' | 'startedAt'>) =>
    useCheckpointOperationStore.getState().setOperation(key, {
      projectId,
      conversationId,
      startedAt,
      ...operation,
    })
  update({ status: 'writing', message: 'Writing checkpoint…' })

  const promise = (async () => {
    try {
      const checkpoint = await takeCheckpoint(projectId, conversationId)
      if (checkpoint.status !== 'ready') {
        const reason = checkpoint.generation_error?.trim()
        update({
          status: 'failed',
          message: reason
            ? `Checkpoint failed: ${reason}`
            : checkpoint.status === 'failed'
              ? 'Checkpoint failed its own checks — nothing was cut over.'
              : 'Checkpoint has no written summary — nothing was cut over.',
        })
        return null
      }
      const result = await cutOver(projectId, checkpoint.id)
      update({
        status: 'succeeded',
        message: 'Checkpoint written — continuing in the successor conversation.',
        successorConversationId: result.successor_conversation_id,
      })
      return result
    } catch (error) {
      update({
        status: 'failed',
        message: readableApiError(error, 'Checkpoint request failed.'),
      })
      return null
    } finally {
      inFlight.delete(key)
    }
  })()
  inFlight.set(key, promise)
  return promise
}
