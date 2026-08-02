import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useSSEConnectionState } from '@/hooks/useSSE'
import { AgentSummary, useAgentOutput, useAgents, useAgentTimeline } from '@/api/agents'
import { useAgentChatHistory, useAgentConversations, useAgentRecentChat } from '@/api/agentChat'
import { useQueueStatus, withdrawQueueEntry } from '@/api/queue'
import { useWorkspacePaths } from '@/api/workspace'
import { useConfigStore } from '@/store/configStore'
import { AgentTimeline } from './AgentTimeline'
import { BannerStack, type ConversationBanner } from './BannerStack'
import { Composer } from './Composer'
import { ConversationControls, type HandoffState } from './ConversationControls'

interface AgentOutputPanelProps {
  agent: AgentSummary
  onBackToProject?: () => void
  initialConversationId?: string | null
  onConversationChange?: (conversationId: string | null) => void
}

const NEW_CONVERSATION_VALUE = '__new__'
const HANDOFF_PROMPT = `Prepare a durable AgentWeave handoff before ending this session.

Invoke your aw-checkpoint skill with reason pre_handoff. Save the current intent, files modified,
decisions and rationale, blockers, exact next steps, and verification commands under
.agentweave/shared/checkpoints/. Stop after confirming the checkpoint path.`

const RESUME_HANDOFF_PREFIX = `Resume from the latest durable AgentWeave handoff.

Before doing anything else, find and read the newest checkpoint for your agent under
.agentweave/shared/checkpoints/, then read .agentweave/shared/context.md. Treat the checkpoint
as authoritative and continue from its Next Steps.

User request:`

interface TriggerResult {
  status: string
  waiting_reason?: string | null
  conversation_id: string
  provider_session_id?: string | null
}

export function AgentOutputPanel({
  agent,
  onBackToProject,
  initialConversationId = null,
  onConversationChange,
}: AgentOutputPanelProps) {
  const { lines, isLoading } = useAgentOutput(agent.name)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoscroll, setAutoscroll] = useState(true)

  const { apiKey, projectId } = useConfigStore()
  const [isSending, setIsSending] = useState(false)
  const [selectedConversationId, setSelectedConversationId] = useState<string>(
    initialConversationId ?? '',
  )
  const onConversationChangeRef = useRef(onConversationChange)
  onConversationChangeRef.current = onConversationChange
  const [handoffState, setHandoffState] = useState<HandoffState>('idle')
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [isStopping, setIsStopping] = useState(false)
  const handoffOutputStartRef = useRef<number | null>(null)
  const handoffSawRunningRef = useRef(false)
  const { data: conversations = [] } = useAgentConversations(agent.name)

  useEffect(() => {
    setSelectedConversationId(initialConversationId ?? '')
    setHandoffState('idle')
    setSessionNotice(null)
    setSubmissionError(null)
    setIsStopping(false)
    handoffOutputStartRef.current = null
    handoffSawRunningRef.current = false
  }, [agent.name, initialConversationId])

  useEffect(() => {
    onConversationChangeRef.current?.(
      selectedConversationId && selectedConversationId !== NEW_CONVERSATION_VALUE
        ? selectedConversationId
        : null,
    )
  }, [selectedConversationId])

  useEffect(() => {
    if (agent.status !== 'running') setIsStopping(false)
  }, [agent.status])

  useEffect(() => {
    if (conversations.length > 0 && !selectedConversationId) {
      setSelectedConversationId(conversations[0].id)
    }
  }, [conversations, selectedConversationId])

  useEffect(() => {
    const outputStart = handoffOutputStartRef.current
    if (handoffState !== 'preparing' || outputStart === null) return
    if (agent.status === 'running') {
      handoffSawRunningRef.current = true
      return
    }

    const completed = lines.slice(outputStart).some(
      (line) => line.kind === 'status' && line.payload?.phase === 'completed',
    )
    if (completed || handoffSawRunningRef.current) {
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('ready')
      setSessionNotice('Handoff ready — your next message starts fresh and resumes it')
    }
  }, [agent.status, handoffState, lines.length])

  useEffect(() => {
    if (autoscroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoscroll])

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoscroll(atBottom)
  }

  const isRunning = agent.status === 'running'
  const handoffUnavailable = agent.runner === 'manual'
  const interactionLocked =
    isRunning || isSending || handoffState === 'preparing'
  const currentConversationId =
    selectedConversationId && selectedConversationId !== NEW_CONVERSATION_VALUE
      ? selectedConversationId
      : undefined

  const { data: roster = [] } = useAgents()
  const { data: timelineEvents = [] } = useAgentTimeline(agent.name)
  const { data: queueStatus } = useQueueStatus(agent.name)
  const { data: workspacePaths = [] } = useWorkspacePaths()
  const conversationChat = useAgentChatHistory(agent.name, currentConversationId ?? null)
  const recentChat = useAgentRecentChat(agent.name)
  const chat = currentConversationId ? conversationChat : recentChat
  const timelineEntries = chat.data?.entries ?? []
  const sseConnectionState = useSSEConnectionState()

  const [foldAllSignal, setFoldAllSignal] = useState(0)

  // Fixed evaluation order so a cleared condition never reshuffles the ones
  // that remain (design.md: "Conditions are reported in a banner stack").
  const banners: ConversationBanner[] = [
    submissionError ? { id: 'run-failure', message: submissionError } : null,
    sseConnectionState === 'reconnecting'
      ? { id: 'stream-loss', message: 'Live updates are disconnected — reconnecting…' }
      : null,
    timelineEntries.some((entry) => entry.hop_budget_exceeded)
      ? { id: 'blocked-queue', message: 'Queued messages are blocked by the hop limit — deliver now to continue.' }
      : null,
  ].filter((banner): banner is ConversationBanner => banner !== null)

  const handleWithdraw = (entryId: string) => {
    void withdrawQueueEntry(entryId)
  }

  const postTrigger = async (
    triggerMessage: string,
    conversationId?: string,
  ): Promise<TriggerResult> => {
    const response = await fetch('/api/v1/agent/trigger', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        agent: agent.name,
        message: triggerMessage,
        conversation_id: conversationId,
      }),
    })
    if (!response.ok) {
      throw new Error(`Trigger failed with status ${response.status}`)
    }
    return (await response.json()) as TriggerResult
  }

  // A 200 response does not mean the agent actually ran — the Hub can accept the input and
  // still leave it queued (no worktree yet, still running, etc). `status` tells the two
  // apart; without checking it here, a queued trigger looked identical to a running one and
  // the operator got no feedback at all (the "sent a message and nothing happened" report).
  const queuedNotice = (result: TriggerResult, fallback: string): string | null =>
    result.status === 'queued' ? (result.waiting_reason ?? fallback) : null

  const handleStop = async () => {
    if (!apiKey || !isRunning || isStopping) return
    setIsStopping(true)
    try {
      const response = await fetch(`/api/v1/agent/${agent.name}/stop`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}` },
      })
      if (!response.ok) {
        throw new Error(`Stop failed with status ${response.status}`)
      }
      // Left true: the status chip flips away from "running" once the process actually
      // exits (via the run_stopped SSE event's agents-query invalidation), and the effect
      // above clears isStopping at that point. Clearing it here instead would let the
      // button be clicked again mid-shutdown.
    } catch (err) {
      console.error('Failed to stop run:', err)
      setIsStopping(false)
    }
  }

  const handleDeliverNow = async () => {
    // Any operator-origin entry is depth 0, so it unblocks a hop-budget-suspended
    // chain and drains it in the same turn (design.md: "operator input resets
    // the chain") — this reuses that existing behavior rather than adding a
    // dedicated force-deliver endpoint.
    if (!apiKey || isRunning || isSending) return
    const isNew = !selectedConversationId || selectedConversationId === NEW_CONVERSATION_VALUE
    setIsSending(true)
    try {
      const result = await postTrigger(
        'Continue — deliver the queued messages.',
        isNew ? undefined : selectedConversationId,
      )
      setSelectedConversationId(result.conversation_id)
      const notice = queuedNotice(result, `${agent.name} is still not available to receive it`)
      if (notice) setSessionNotice(`Still queued — ${notice}`)
    } catch (err) {
      console.error('Failed to deliver queued messages:', err)
    } finally {
      setIsSending(false)
    }
  }

  const handleHandoff = async () => {
    if (!apiKey || !currentConversationId || isRunning || isSending) return
    setIsSending(true)
    setHandoffState('preparing')
    setSessionNotice('Preparing durable handoff…')
    handoffOutputStartRef.current = lines.length
    handoffSawRunningRef.current = false
    try {
      const result = await postTrigger(HANDOFF_PROMPT, currentConversationId)
      const notice = queuedNotice(result, `${agent.name} is not available to receive it`)
      if (notice) {
        handoffOutputStartRef.current = null
        handoffSawRunningRef.current = false
        setHandoffState('idle')
        setSessionNotice(`Could not start handoff — ${notice}`)
        return
      }
      setSelectedConversationId(NEW_CONVERSATION_VALUE)
    } catch (err) {
      console.error('Failed to prepare handoff:', err)
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('idle')
      setSelectedConversationId(currentConversationId)
      setSessionNotice('Failed to prepare handoff')
    } finally {
      setIsSending(false)
    }
  }

  const selectConversation = (id: string) => {
    setSelectedConversationId(id)
    setHandoffState('idle')
    setSessionNotice(null)
    handoffOutputStartRef.current = null
    handoffSawRunningRef.current = false
  }

  const handleComposerSubmit = async (typedMessage: string): Promise<void> => {
    if (!apiKey) throw new Error('Not configured')
    setIsSending(true)
    setSubmissionError(null)
    const isNew = !selectedConversationId || selectedConversationId === NEW_CONVERSATION_VALUE
    const outgoingMessage =
      isNew && handoffState === 'ready'
        ? `${RESUME_HANDOFF_PREFIX}\n\n${typedMessage}`
        : typedMessage
    if (isNew) setSessionNotice('Starting new conversation…')
    try {
      const result = await postTrigger(
        outgoingMessage,
        isNew ? undefined : selectedConversationId,
      )
      setSelectedConversationId(result.conversation_id)
      if (isNew) setHandoffState('idle')
      const notice = queuedNotice(result, `${agent.name} is not available to receive it right now`)
      if (notice) {
        setSessionNotice(`Queued — ${notice}`)
      }
    } catch (err) {
      console.error('Failed to send message:', err)
      setSubmissionError('Failed to send message')
      setSessionNotice('Failed to send message')
      throw err
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      {/* Header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b"
        data-testid="conversation-header"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        {onBackToProject && (
          <button
            type="button"
            onClick={onBackToProject}
            aria-label="Back to project"
            title="Back to project"
            className="text-sm"
            style={{ color: 'var(--text-2)' }}
          >
            ←
          </button>
        )}
        <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{agent.name}</span>

        {/* Status chip. Provider session identity is not shown here — see
            "Conversation identity is readable without exposing provider
            identity": normal controls use conversation_id only, and provider
            binding is confined to agent details / diagnostics. */}
        <span
          className="flex items-center gap-1.5"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 500,
            background: isRunning ? 'rgba(34,197,94,0.1)' : 'var(--surface-3)',
            color: isRunning ? 'var(--green)' : 'var(--text-3)',
          }}
        >
          {isRunning && (
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          )}
          {agent.status}
        </span>
      </div>

      {/* Output body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        data-testid="conversation-output"
        className="flex-1 overflow-y-auto py-[22px]"
        style={{ background: 'var(--bg)' }}
      >
        {isLoading || chat.isLoading ? (
          <p className="font-mono text-xs italic px-5" style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}>Loading output…</p>
        ) : (
          <AgentTimeline
            agent={agent}
            entries={timelineEntries}
            roster={roster}
            timelineEvents={timelineEvents}
            queueStatus={queueStatus}
            isRunning={isRunning}
            onDeliverNow={handleDeliverNow}
            onWithdraw={handleWithdraw}
            foldAllSignal={foldAllSignal}
          />
        )}
        <div ref={bottomRef} />
      </div>

      {/* Send message footer */}
      <div
        className="shrink-0 border-t px-3 py-2 flex flex-col gap-2"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <ConversationControls
          agent={agent}
          isRunning={isRunning}
          isStopping={isStopping}
          onStop={handleStop}
          conversations={conversations}
          currentConversationId={currentConversationId}
          onSelectConversation={selectConversation}
          onNewConversation={() => selectConversation(NEW_CONVERSATION_VALUE)}
          handoffState={handoffState}
          handoffUnavailable={handoffUnavailable}
          interactionLocked={interactionLocked}
          onHandoff={handleHandoff}
          onFoldAll={() => setFoldAllSignal((s) => s + 1)}
        />

        <BannerStack banners={banners} />

        <span
          data-testid="session-continuity"
          className="flex items-center gap-1"
          style={{
            fontSize: 11,
            color:
              handoffState === 'ready' || selectedConversationId === NEW_CONVERSATION_VALUE
                ? 'var(--blue)'
                : 'var(--text-3)',
          }}
        >
          <Icon
            name={
              handoffState === 'preparing'
                ? 'hourglass_top'
                : selectedConversationId === NEW_CONVERSATION_VALUE
                  ? 'move_up'
                  : 'link'
            }
            size={12}
          />
          {sessionNotice
            || (selectedConversationId === NEW_CONVERSATION_VALUE
              ? 'Next message starts a fresh conversation'
              : currentConversationId
                ? `Continuing ${currentConversationId.slice(0, 12)}…`
                : 'No conversation yet')}
        </span>

        {/* Input row */}
        <Composer
          key={`${agent.name}::${currentConversationId ?? NEW_CONVERSATION_VALUE}`}
          agent={agent.name}
          projectId={projectId}
          conversationId={currentConversationId ?? null}
          isRunning={isRunning}
          onSubmit={handleComposerSubmit}
          workspacePaths={workspacePaths}
        />
      </div>
    </div>
  )
}
