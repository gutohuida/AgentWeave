import { useMemo, useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import type { AgentSummary, AgentTimelineEvent } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import type { QueueStatus } from '@/api/queue'
import { agentColorVars } from '@/lib/agentColors'
import {
  entryCategory,
  findPairedResult,
  groupIntoTurns,
  runStatusByRunId,
  type RunLifecycleStatus,
  type TimelineTurn,
} from '@/lib/agentTimelineModel'

interface AgentTimelineProps {
  agent: AgentSummary
  entries: TimelineEntry[]
  roster: AgentSummary[]
  timelineEvents: AgentTimelineEvent[]
  queueStatus?: QueueStatus
  isRunning: boolean
  onStop?: () => void
  isStopping?: boolean
  onWithdraw?: (entryId: string) => void
}

const LIFECYCLE_LABEL: Record<RunLifecycleStatus, string> = {
  started: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  stopped: 'Stopped',
  interrupted: 'Interrupted',
}
const LIFECYCLE_COLOR: Record<RunLifecycleStatus, string> = {
  started: 'var(--blue)',
  completed: 'var(--green)',
  failed: 'var(--red)',
  stopped: 'var(--amber)',
  interrupted: 'var(--purple)',
}
const LIFECYCLE_ICON: Record<RunLifecycleStatus, string> = {
  started: 'play_arrow',
  completed: 'check_circle',
  failed: 'error',
  stopped: 'stop',
  interrupted: 'warning',
}

type ColorLookup = Map<string, number | null | undefined>

export function AgentTimeline({
  agent,
  entries,
  roster,
  timelineEvents,
  queueStatus,
  isRunning,
  onStop,
  isStopping,
  onWithdraw,
}: AgentTimelineProps) {
  const colorByName: ColorLookup = useMemo(() => {
    const map = new Map<string, number | null | undefined>()
    for (const a of roster) map.set(a.name, a.color_index)
    return map
  }, [roster])

  const { turns, pending } = useMemo(() => groupIntoTurns(entries), [entries])
  const statusByRun = useMemo(() => runStatusByRunId(timelineEvents), [timelineEvents])
  const [foldOverride, setFoldOverride] = useState<Record<string, boolean>>({})
  const [workOpen, setWorkOpen] = useState<Record<string, boolean>>({})

  if (turns.length === 0 && pending.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center h-full text-center px-6"
        style={{ color: 'var(--text-3)' }}
      >
        <Icon name="chat" size={40} style={{ opacity: 0.5, marginBottom: 12 }} />
        <p className="text-sm">No conversation yet</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {turns.map((turn, turnIndex) => {
        const key = turn.runId ?? `turn-${turnIndex}`
        const isLastTurn = turnIndex === turns.length - 1
        const runStatus = turn.runId ? statusByRun[turn.runId] : undefined
        const isRunningTurn = isLastTurn && isRunning && (!runStatus || runStatus === 'started')
        // Default: the last turn is unfolded, every earlier one starts folded
        // to a summary — the operator can toggle any of them either way.
        const folded = foldOverride[key] ?? !isLastTurn

        return (
          <div key={key} className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border)' }}>
            <button
              onClick={() => setFoldOverride((old) => ({ ...old, [key]: !folded }))}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left"
              style={{ background: 'var(--surface-2)' }}
            >
              <Icon
                name="expand_more"
                size={14}
                style={{
                  color: 'var(--text-3)',
                  transform: folded ? 'rotate(-90deg)' : undefined,
                  transition: 'transform var(--dur-fast) var(--ease)',
                }}
              />
              {isRunningTurn ? (
                <span
                  className="flex items-center gap-1.5 text-[11px] font-medium"
                  style={{ color: 'var(--green)' }}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                  Running
                </span>
              ) : runStatus ? (
                <span
                  className="flex items-center gap-1 text-[11px] font-medium"
                  style={{ color: LIFECYCLE_COLOR[runStatus] }}
                >
                  <Icon name={LIFECYCLE_ICON[runStatus]} size={12} />
                  {LIFECYCLE_LABEL[runStatus]}
                </span>
              ) : (
                <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                  Turn
                </span>
              )}
              <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                {formatDistanceToNow(new Date(turn.entries[0].timestamp), { addSuffix: true })}
              </span>
              <span className="flex-1" />
              {isRunningTurn && onStop && (
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation()
                    onStop()
                  }}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium"
                  style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--red)' }}
                >
                  <Icon name="stop" size={11} />
                  {isStopping ? 'Stopping…' : 'Stop'}
                </span>
              )}
            </button>

            {!folded && (
              <div className="p-3 space-y-2" style={{ background: 'var(--bg)' }}>
                <TurnBody
                  turn={turn}
                  turnKey={key}
                  agentName={agent.name}
                  colorByName={colorByName}
                  workOpen={workOpen[key] ?? false}
                  onToggleWork={() => setWorkOpen((old) => ({ ...old, [key]: !old[key] }))}
                />
              </div>
            )}
          </div>
        )
      })}

      {(pending.length > 0 || (queueStatus && queueStatus.waiting_count > 0)) && (
        <div
          className="rounded-lg p-3 space-y-2"
          style={{ border: '1px dashed var(--border-hi)', background: 'var(--surface-2)' }}
        >
          <div className="flex items-center gap-2 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
            <Icon name="schedule" size={13} />
            Waiting to be delivered
            {queueStatus ? ` (${queueStatus.waiting_count})` : ''}
            {!isRunning && queueStatus?.waiting_reason ? ` — ${queueStatus.waiting_reason}` : ''}
          </div>
          {pending.map((entry) => (
            <PendingEntry key={entry.id} entry={entry} colorByName={colorByName} onWithdraw={onWithdraw} />
          ))}
        </div>
      )}
    </div>
  )
}

function TurnBody({
  turn,
  turnKey,
  agentName,
  colorByName,
  workOpen,
  onToggleWork,
}: {
  turn: TimelineTurn
  turnKey: string
  agentName: string
  colorByName: ColorLookup
  workOpen: boolean
  onToggleWork: () => void
}) {
  const work = turn.entries.filter((e) => entryCategory(e) === 'work')
  const rest = turn.entries.filter((e) => entryCategory(e) !== 'work')
  // A tool_result is rendered inline with its tool_use, never as its own row.
  const pairedResultIds = new Set(
    work
      .filter((e) => e.output_kind === 'tool_use')
      .map((e) => findPairedResult(work, e)?.id)
      .filter((id): id is string => Boolean(id)),
  )
  const workRows = work.filter((e) => !pairedResultIds.has(e.id))

  return (
    <>
      {work.length > 0 && (
        <div className="rounded-md" style={{ border: '1px solid var(--border)' }}>
          <button
            onClick={onToggleWork}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[11px]"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon
              name="expand_more"
              size={12}
              style={{ transform: workOpen ? undefined : 'rotate(-90deg)' }}
            />
            {work.length} step{work.length === 1 ? '' : 's'} of intermediate work
          </button>
          {workOpen && (
            <div className="px-2.5 pb-2 space-y-1.5">
              {workRows.map((entry) => (
                <WorkRow key={entry.id} entry={entry} paired={findPairedResult(work, entry)} />
              ))}
            </div>
          )}
        </div>
      )}

      {rest.map((entry) => {
        if (entryCategory(entry) === 'result') {
          return <ResultCard key={entry.id} entry={entry} turnKey={turnKey} />
        }
        return (
          <MessageBubble
            key={entry.id}
            entry={entry}
            agentName={agentName}
            colorByName={colorByName}
          />
        )
      })}
    </>
  )
}

function WorkRow({ entry, paired }: { entry: TimelineEntry; paired?: TimelineEntry }) {
  const [expanded, setExpanded] = useState(false)
  const label =
    entry.output_kind === 'thinking'
      ? 'Thinking'
      : entry.output_kind === 'tool_use'
        ? entry.content || 'Tool call'
        : entry.content || 'Tool result'
  const statusSuffix = paired
    ? (paired.payload as Record<string, unknown> | null | undefined)?.is_error === true
      ? ' · failed'
      : ' · completed'
    : entry.output_kind === 'tool_use'
      ? ' · awaiting result'
      : ''

  return (
    <button
      onClick={() => setExpanded((v) => !v)}
      className="block w-full text-left font-mono text-[11px] leading-5"
      style={{ color: 'var(--text-2)' }}
    >
      <span style={{ color: 'var(--text-3)' }}>
        {label}
        {statusSuffix}
      </span>
      {expanded && (
        <span className="block whitespace-pre-wrap mt-0.5" style={{ color: 'var(--text-3)' }}>
          {entry.content}
          {paired && paired.content !== entry.content ? `\n${paired.content}` : ''}
        </span>
      )}
    </button>
  )
}

function ResultCard({ entry, turnKey }: { entry: TimelineEntry; turnKey: string }) {
  const [clipped, setClipped] = useState(true)
  const isError = entry.output_kind === 'diagnostic'
  const long = entry.content.length > 240
  return (
    <div
      data-testid={`result-card-${turnKey}`}
      className="relative overflow-hidden px-3 py-2"
      style={{
        borderRadius: 'var(--radius-content)',
        border: `1px solid ${isError ? 'var(--amber)' : 'var(--border-hi)'}`,
        background: 'color-mix(in oklab, var(--surface-2) 90%, transparent)',
        maxHeight: long && clipped ? 96 : undefined,
      }}
    >
      <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--text-2)' }}>
        {entry.content}
      </p>
      {long && clipped && (
        <button
          onClick={() => setClipped(false)}
          className="absolute inset-x-0 bottom-0 h-8 flex items-end justify-center text-[10px] pb-1"
          style={{
            background: 'linear-gradient(to top, var(--surface-2), transparent)',
            color: 'var(--text-3)',
          }}
        >
          Show more
        </button>
      )}
    </div>
  )
}

function participantLabel(entry: TimelineEntry, agentName: string): { name: string; align: 'left' | 'right' } {
  if (entry.kind === 'operator_input') return { name: 'You', align: 'right' }
  if (entry.kind === 'inbound_peer') return { name: entry.participant || 'agent', align: 'left' }
  // Positioned as the subject agent's own contribution, but labelled with the
  // RECIPIENT's name — colour reinforces identity, it never carries it alone,
  // and here the identity being reinforced is "who this was sent to".
  if (entry.kind === 'outbound_peer') return { name: entry.participant || 'agent', align: 'right' }
  return { name: agentName, align: 'left' }
}

function MessageBubble({
  entry,
  agentName,
  colorByName,
}: {
  entry: TimelineEntry
  agentName: string
  colorByName: ColorLookup
}) {
  const { name, align } = participantLabel(entry, agentName)
  const isPeer = entry.kind === 'inbound_peer' || entry.kind === 'outbound_peer'
  // Inbound is tinted with the SENDER's colour; outbound is accented with the
  // RECIPIENT's colour — both are `entry.participant`, the "other" agent.
  const colors = isPeer ? agentColorVars(colorByName.get(entry.participant || '')) : null
  const isError = entry.output_kind === 'error'

  return (
    <div className={`flex ${align === 'right' ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[85%] rounded-2xl px-3 py-2"
        style={{
          background: colors ? colors.tint : isError ? 'rgba(239,68,68,0.1)' : 'var(--surface-2)',
          border: colors ? `1px solid ${colors.border}` : undefined,
        }}
      >
        <div className="flex items-center gap-1.5 mb-0.5">
          <span
            className="text-[11px] font-medium"
            style={{ color: colors ? colors.accent : isError ? 'var(--red)' : 'var(--text-3)' }}
          >
            {name}
          </span>
        </div>
        <div className="text-sm whitespace-pre-wrap break-words" style={{ color: 'var(--text)' }}>
          {entry.content}
        </div>
      </div>
    </div>
  )
}

function PendingEntry({
  entry,
  colorByName,
  onWithdraw,
}: {
  entry: TimelineEntry
  colorByName: ColorLookup
  onWithdraw?: (entryId: string) => void
}) {
  const isPeer = entry.kind === 'inbound_peer'
  const colors = isPeer ? agentColorVars(colorByName.get(entry.participant || '')) : null
  const label = entry.kind === 'operator_input' ? 'You' : entry.participant || 'agent'

  return (
    <div
      className="flex items-start gap-2 px-2.5 py-1.5 rounded-md"
      style={{ background: 'var(--surface)', opacity: 0.85, border: '1px dashed var(--border)' }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-medium" style={{ color: colors ? colors.accent : 'var(--text-3)' }}>
            {label}
          </span>
          <span className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            queued
          </span>
        </div>
        <p className="text-xs mt-0.5 whitespace-pre-wrap break-words" style={{ color: 'var(--text-2)' }}>
          {entry.content}
        </p>
        {entry.hop_budget_exceeded && (
          <p className="text-[11px] mt-1" style={{ color: 'var(--amber)' }}>
            Autonomous continuation is paused — operator input will resume it.
          </p>
        )}
      </div>
      {onWithdraw && (
        <button
          onClick={() => onWithdraw(entry.id)}
          title="Withdraw before it's delivered"
          className="shrink-0 text-[11px] px-1.5 py-0.5 rounded"
          style={{ color: 'var(--text-3)' }}
        >
          <Icon name="close" size={12} />
        </button>
      )}
    </div>
  )
}
