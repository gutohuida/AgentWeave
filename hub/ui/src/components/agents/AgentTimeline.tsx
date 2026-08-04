import { useEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'
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
  onDeliverNow?: () => void
  onWithdraw?: (entryId: string) => void
  /** Bump to fold every turn — driven by the header's "Fold all turns" button. */
  foldAllSignal?: number
}

const TERMINAL_LABEL: Partial<Record<RunLifecycleStatus, string>> = {
  failed: 'Turn failed',
  stopped: 'Turn stopped',
  interrupted: 'Turn interrupted',
}

type ColorLookup = Map<string, number | null | undefined>

export function AgentTimeline({
  agent,
  entries,
  roster,
  timelineEvents,
  queueStatus,
  isRunning,
  onDeliverNow,
  onWithdraw,
  foldAllSignal,
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

  // The caller always passes a defined counter (never undefined) that starts
  // at 0, so the effect must only react the SECOND time it sees a given
  // value change, not merely "the effect ran." A `mounted` boolean guard
  // looks equivalent but isn't: React 18 StrictMode double-invokes effects
  // on mount (to surface missing cleanup), which flips such a guard on the
  // phantom remount and folds every turn before the operator does anything.
  // Comparing against the last-*processed* value is immune to being invoked
  // an extra time, since a repeat invocation still carries the same value.
  const lastProcessedSignal = useRef(foldAllSignal)
  useEffect(() => {
    if (foldAllSignal === undefined || foldAllSignal === lastProcessedSignal.current) return
    lastProcessedSignal.current = foldAllSignal
    setFoldOverride(() => {
      const all: Record<string, boolean> = {}
      turns.forEach((t, i) => {
        all[t.runId ?? `turn-${i}`] = true
      })
      return all
    })
    // Only reacts to the signal firing — deliberately excludes `turns`, which
    // changes on every poll and would otherwise re-fold turns the operator
    // just reopened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foldAllSignal])

  const suspendedByParticipant = useMemo(() => {
    const groups = new Map<string, number>()
    for (const entry of pending) {
      if (entry.hop_budget_exceeded && entry.participant) {
        groups.set(entry.participant, (groups.get(entry.participant) ?? 0) + 1)
      }
    }
    return groups
  }, [pending])

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
    <div className="max-w-[960px] mx-auto flex flex-col gap-[21px] px-[30px]">
      {turns.map((turn, turnIndex) => {
        const key = turn.runId ?? `turn-${turnIndex}`
        const isLastTurn = turnIndex === turns.length - 1
        const runStatus = turn.runId ? statusByRun[turn.runId] : undefined
        // Default: the last turn is open, every earlier one starts folded to a
        // one-line summary — the operator can toggle any of them either way.
        const folded = foldOverride[key] ?? !isLastTurn

        if (folded) {
          return (
            <FoldedTurnPill
              key={key}
              turn={turn}
              onClick={() => setFoldOverride((old) => ({ ...old, [key]: false }))}
            />
          )
        }

        const terminalLabel = runStatus ? TERMINAL_LABEL[runStatus] : undefined

        return (
          <div key={key} className="flex flex-col gap-[21px]">
            {!isLastTurn && (
              <button
                onClick={() => setFoldOverride((old) => ({ ...old, [key]: true }))}
                className="fold-control self-start flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px]"
                style={{ color: 'var(--text-3)', opacity: 0.55 }}
                title="Fold this turn"
              >
                <Icon name="expand_more" size={11} />
                fold
              </button>
            )}
            <TurnBody
              turn={turn}
              turnKey={key}
              agentName={agent.name}
              colorByName={colorByName}
              workOpen={workOpen[key] ?? false}
              onToggleWork={() => setWorkOpen((old) => ({ ...old, [key]: !old[key] }))}
            />
            {terminalLabel && (
              <div
                className="flex items-center gap-2 justify-center text-[12px]"
                style={{ color: 'var(--text-3)' }}
              >
                <span className="flex-1 h-px" style={{ background: 'var(--border)' }} />
                {terminalLabel}
                {turn.entries.length > 0 &&
                  ` · ${format(new Date(turn.entries[turn.entries.length - 1].timestamp), 'HH:mm')}`}
                <span className="flex-1 h-px" style={{ background: 'var(--border)' }} />
              </div>
            )}
          </div>
        )
      })}

      {pending.map((entry) => (
        <MessageEntry
          key={entry.id}
          entry={entry}
          agentName={agent.name}
          colorByName={colorByName}
          queued
          onWithdraw={onWithdraw}
        />
      ))}

      {suspendedByParticipant.size > 0 && (
        <div
          className="flex items-start gap-2.5 px-[13px] py-2.5 rounded-lg text-[12.5px]"
          style={{
            border: '1px solid color-mix(in oklab, var(--amber) 28%, transparent)',
            background: 'color-mix(in oklab, var(--amber) 7%, transparent)',
            color: 'color-mix(in oklab, var(--amber) 65%, var(--text))',
          }}
        >
          <Icon name="warning" size={15} style={{ color: 'var(--amber)', marginTop: 1, flexShrink: 0 }} />
          <div className="flex-1">
            <b style={{ color: 'var(--amber)' }}>Autonomous continuation paused</b> —{' '}
            {[...suspendedByParticipant.entries()]
              .map(([who, count]) => `${count} ${count === 1 ? 'entry' : 'entries'} from ${who}`)
              .join(', ')}{' '}
            reached the hop budget. They'll be delivered with your next message.
          </div>
          {onDeliverNow && (
            <button
              onClick={onDeliverNow}
              className="shrink-0 text-[12px] font-medium px-2 py-1 rounded"
              style={{ color: 'var(--text-2)' }}
            >
              Deliver now
            </button>
          )}
        </div>
      )}

      {!isRunning && queueStatus && queueStatus.waiting_count > 0 && suspendedByParticipant.size === 0 && (
        <p className="text-[11.5px] text-center" style={{ color: 'var(--text-3)' }}>
          {queueStatus.waiting_count} waiting{queueStatus.waiting_reason ? ` — ${queueStatus.waiting_reason}` : ''}
        </p>
      )}
    </div>
  )
}

function FoldedTurnPill({ turn, onClick }: { turn: TimelineTurn; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="fold-control flex items-center gap-2 self-stretch px-[11px] py-[6px] rounded-lg text-[12.5px] text-left"
      style={{ border: '1px dashed var(--border)', color: 'var(--text-3)' }}
    >
      <Icon name="expand_more" size={13} style={{ transform: 'rotate(-90deg)' }} />
      Turn folded · {turn.entries.length} {turn.entries.length === 1 ? 'entry' : 'entries'}
    </button>
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
  const workDuration =
    work.length > 1
      ? ((new Date(work[work.length - 1].timestamp).getTime() - new Date(work[0].timestamp).getTime()) / 1000).toFixed(1)
      : null

  return (
    <>
      {work.length > 0 && (
        <details open={workOpen} className="work-disclosure rounded-lg overflow-hidden">
          <summary
            onClick={(e) => {
              e.preventDefault()
              onToggleWork()
            }}
            className="flex items-center gap-2 px-[11px] py-[7px] text-[12.5px] cursor-pointer list-none"
            style={{ color: 'var(--text-2)' }}
          >
            <Icon
              name="expand_more"
              size={13}
              style={{ opacity: 0.6, transform: workOpen ? undefined : 'rotate(-90deg)' }}
            />
            Work · {work.length} step{work.length === 1 ? '' : 's'}
            {workDuration ? ` · ${workDuration}s` : ''}
          </summary>
          {workOpen && (
            <div className="px-[11px] py-[9px] text-[12.5px]" style={{ borderTop: '1px solid var(--border)', color: 'var(--text-2)' }}>
              {workRows.map((entry) => (
                <WorkRow key={entry.id} entry={entry} paired={findPairedResult(work, entry)} />
              ))}
            </div>
          )}
        </details>
      )}

      {rest.map((entry) => {
        if (entryCategory(entry) === 'result') {
          return <ResultCard key={entry.id} entry={entry} turnKey={turnKey} />
        }
        return <MessageEntry key={entry.id} entry={entry} agentName={agentName} colorByName={colorByName} />
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
      className="flex gap-[.55rem] py-[2.5px] w-full text-left font-mono text-[12.5px]"
    >
      <b style={{ color: 'var(--text)', fontWeight: 500, minWidth: 64 }}>{label}</b>
      <span style={{ color: 'var(--text-2)' }}>{statusSuffix.replace(' · ', '')}</span>
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
      className="relative overflow-hidden px-[18px] py-4"
      style={{
        borderRadius: 'var(--radius-content)',
        border: `1px solid ${isError ? 'var(--amber)' : 'var(--border)'}`,
        background: 'color-mix(in oklab, var(--surface) 82%, transparent)',
        maxHeight: long && clipped ? 96 : undefined,
      }}
    >
      <p className="text-[13px] whitespace-pre-wrap" style={{ color: 'var(--text-2)' }}>
        {entry.content}
      </p>
      {long && clipped && (
        <button
          onClick={() => setClipped(false)}
          className="absolute inset-x-0 bottom-0 h-8 flex items-end justify-center text-[10px] pb-1"
          style={{
            background: 'linear-gradient(to top, var(--surface), transparent)',
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

function MessageEntry({
  entry,
  agentName,
  colorByName,
  queued = false,
  onWithdraw,
}: {
  entry: TimelineEntry
  agentName: string
  colorByName: ColorLookup
  queued?: boolean
  onWithdraw?: (entryId: string) => void
}) {
  const time = format(new Date(entry.timestamp), 'HH:mm')
  const wrapperStyle: React.CSSProperties = { opacity: queued ? 0.55 : 1 }
  const queuedTag = queued && (
    <span
      className="inline-flex items-center h-[18px] px-[.4rem] rounded text-[10.5px] font-semibold uppercase tracking-wide"
      style={{ background: 'var(--accent)', color: 'var(--text-3)' }}
    >
      queued
    </span>
  )
  const withdraw = queued && onWithdraw && (
    <button
      onClick={() => onWithdraw(entry.id)}
      title="Withdraw before it's delivered"
      className="text-[11px]"
      style={{ color: 'var(--text-3)' }}
    >
      <Icon name="close" size={12} />
    </button>
  )

  // Own plain text (or an error) — borderless, no bubble, just a "who" line.
  if (entry.kind === 'agent_output') {
    const isError = entry.output_kind === 'error'
    const colors = agentColorVars(colorByName.get(agentName))
    return (
      <div className="flex flex-col gap-[5px]" style={wrapperStyle}>
        <div className="flex items-center gap-[.4rem] text-[11.5px] font-semibold" style={{ color: 'var(--text-2)' }}>
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: isError ? 'var(--red)' : colors.accent }}
          />
          {agentName}
          <span className="font-normal" style={{ color: 'var(--text-3)' }}>
            {time}
          </span>
          {queuedTag}
          {withdraw}
        </div>
        <div
          className="text-sm leading-[1.6] whitespace-pre-wrap break-words"
          style={{ color: isError ? 'var(--red)' : 'var(--text)' }}
        >
          {entry.content}
        </div>
      </div>
    )
  }

  // Operator ("you") — right-aligned tinted bubble.
  if (entry.kind === 'operator_input') {
    return (
      <div className="flex flex-col items-end gap-[5px]" style={wrapperStyle}>
        <div className="flex items-center gap-[.4rem] text-[11.5px] font-semibold" style={{ color: 'var(--text-2)' }}>
          {queuedTag}
          {withdraw}
          you
          <span className="font-normal" style={{ color: 'var(--text-3)' }}>
            {time}
          </span>
        </div>
        <div
          className="max-w-[82%] px-[13px] py-[10px] text-sm leading-[1.6] whitespace-pre-wrap break-words"
          style={{
            borderRadius: 'var(--radius-xl, 18px)',
            border: '1px solid color-mix(in oklab, var(--blue) 30%, transparent)',
            background: 'color-mix(in oklab, var(--blue) 14%, var(--surface-2))',
            color: 'var(--text)',
          }}
        >
          {entry.content}
        </div>
      </div>
    )
  }

  // Peer traffic, both directions.
  const isInbound = entry.kind === 'inbound_peer'
  const colors = agentColorVars(colorByName.get(entry.participant || ''))
  const { name } = participantLabel(entry, agentName)

  return (
    <div
      className="px-[13px] py-[10px] text-sm"
      style={
        isInbound
          ? {
              borderRadius: 'var(--radius-xl, 18px)',
              border: `1px solid ${colors.border}`,
              background: colors.tint,
              ...wrapperStyle,
            }
          : {
              borderRadius: 'var(--radius-xl, 18px)',
              borderLeft: `2px solid ${colors.accent}`,
              background: 'transparent',
              ...wrapperStyle,
            }
      }
    >
      <div className="flex items-center gap-[.4rem] mb-[5px] text-[11.5px] font-semibold" style={{ color: colors.accent }}>
        {isInbound ? (
          <>
            {name}
            <span className="font-normal" style={{ color: 'var(--text-3)' }}>
              → {agentName}
            </span>
          </>
        ) : (
          <>
            {agentName}
            <span className="font-normal" style={{ color: 'var(--text-3)' }}>
              → {name}
            </span>
          </>
        )}
        <span className="font-normal" style={{ color: 'var(--text-3)' }}>
          {time}
        </span>
        {queuedTag}
        {withdraw}
      </div>
      <div className="whitespace-pre-wrap break-words" style={{ color: 'var(--text)' }}>
        {entry.content}
      </div>
    </div>
  )
}
