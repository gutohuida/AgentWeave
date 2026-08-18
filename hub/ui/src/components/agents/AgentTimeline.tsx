import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import { ToolEditDiff } from '@/components/agents/ToolEditDiff'
import { editDiffStat } from '@/lib/editDiff'
import { formatElapsedSeconds, useElapsedSeconds } from '@/hooks/useElapsedSeconds'
import type { AgentSummary, AgentTimelineEvent } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import type { QueueStatus } from '@/api/queue'
import { agentColorVars } from '@/lib/agentColors'
import {
  entryCategory,
  findPairedResult,
  groupIntoTurns,
  isSuccessCompletionEntry,
  reduceTurnBlocks,
  runDurationsByRunId,
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

/** Every lifecycle status that means "this run is over", whatever the outcome. `started` is
 *  the only one that is not terminal. */
const TERMINAL_STATUSES = new Set<RunLifecycleStatus | undefined>([
  'completed',
  'failed',
  'stopped',
  'interrupted',
])

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
  const durationByRun = useMemo(() => runDurationsByRunId(timelineEvents), [timelineEvents])

  // `isRunning` is `agent.status === 'running'` — a POLLED roster field, so it stays true for a
  // beat after the run has actually ended. The response text and the run's terminal lifecycle
  // event both arrive over SSE well before that poll lands, which left the live indicator sitting
  // underneath a finished answer, still counting, before flipping to "Worked for Xs" seconds
  // later (operator, 2026-08-18: "the working indicator then moves to under the message stays
  // active for a couple more seconds then disappears and collapse at the worked for one").
  //
  // So the indicator is gated on the lifecycle events instead — the same source `durationByRun`
  // reads — which makes the handoff atomic: the instant the terminal event lands, the live
  // counter goes and the settled line appears. `isRunning` is still required, so the indicator
  // cannot appear for an idle agent whose last run simply has no terminal event recorded.
  const lastRunId = turns.length > 0 ? turns[turns.length - 1].runId : null
  const lastRunSettled =
    lastRunId !== null && lastRunId !== undefined
      ? TERMINAL_STATUSES.has(statusByRun[lastRunId])
      : false
  const runVisiblyActive = isRunning && !lastRunSettled

  // Timed from the moment this pane saw the run begin. Only ever shown live; once the run ends,
  // `durationByRun` (from persisted event timestamps) takes over, so a refresh does not change
  // what a finished turn says it took.
  const liveElapsed = useElapsedSeconds(runVisiblyActive)
  const [foldOverride, setFoldOverride] = useState<Record<string, boolean>>({})

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
        const runStatus = turn.runId ? statusByRun[turn.runId] : undefined
        // Foldedness is the operator's choice, never a function of position. The default used
        // to be `!isLastTurn` — derived from the turn's index — so appending a turn silently
        // collapsed whatever the operator was reading the moment they sent a message. Now every
        // turn renders open until folded by hand, via the per-turn control below or
        // "Fold all turns".
        const folded = foldOverride[key] ?? false

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
            {/* Every turn is foldable, including the last. Nothing folds on its own any more,
                so gating this on `!isLastTurn` would leave a single-turn conversation with no
                way to fold at all. */}
            <button
              onClick={() => setFoldOverride((old) => ({ ...old, [key]: true }))}
              className="fold-control self-start flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px]"
              style={{ color: 'var(--text-3)', opacity: 0.55 }}
              title="Fold this turn"
            >
              <Icon name="expand_more" size={11} />
              fold
            </button>
            <TurnBody
              turn={turn}
              turnKey={key}
              agentName={agent.name}
              colorByName={colorByName}
              durationSeconds={turn.runId ? durationByRun[turn.runId] : undefined}
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

      {/* Where the answer is about to appear, not down in the composer. Operator, 2026-08-18:
          "I think the working should be on the composer screen not the chat box. Right where the
          agent is supposed to answer." Sitting here also means the response arrives *under* it
          rather than shoving it aside, so nothing jumps as the text streams in. */}
      {runVisiblyActive && (
        <div
          className="flex items-center gap-2 text-[11px]"
          style={{ color: 'var(--text-3)' }}
          data-testid="timeline-working-indicator"
          role="status"
          aria-live="polite"
        >
          <span className="inline-flex items-center gap-[3px]" aria-hidden="true">
            {[0, 200, 400].map((delay) => (
              <span
                key={delay}
                className="h-1 w-1 rounded-full animate-pulse"
                style={{ background: 'var(--green)', animationDelay: `${delay}ms` }}
              />
            ))}
          </span>
          <span>
            Working{liveElapsed !== null ? ` · ${formatElapsedSeconds(liveElapsed)}` : ''}
          </span>
        </div>
      )}

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
  durationSeconds,
}: {
  turn: TimelineTurn
  turnKey: string
  agentName: string
  colorByName: ColorLookup
  /** Whole-run duration for a finished turn; undefined while running or if unknown. */
  durationSeconds?: number
}) {
  // Walked in execution order — a block is never hoisted ahead of the text that
  // preceded it (2026-08-04-hub-charcoal-visual-refresh).
  const blocks = useMemo(() => reduceTurnBlocks(turn.entries), [turn.entries])

  // Where the agent's half of the turn starts — the operator's own message is not something
  // the agent "worked for", so the duration belongs after it, immediately above the response.
  const firstAgentBlockId = useMemo(() => {
    const first = blocks.find(
      (block) => block.kind === 'work' || block.entry.kind === 'agent_output',
    )
    return first?.kind === 'work' ? first.id : first?.entry.id
  }, [blocks])

  return (
    <>
      {blocks.map((block) => {
        const blockId = block.kind === 'work' ? block.id : block.entry.id
        // Operator, 2026-08-18: "After answering it could just look like worked for Xs and then
        // the response underneath." Unlike the "Completed" message this replaces, it says
        // something — and it sits where the eye already is rather than down in the composer.
        const durationLine =
          durationSeconds !== undefined && blockId === firstAgentBlockId ? (
            <div
              key={`worked-${blockId}`}
              className="text-[11px]"
              style={{ color: 'var(--text-3)' }}
              data-testid="turn-worked-for"
            >
              Worked for {formatElapsedSeconds(durationSeconds)}
            </div>
          ) : null

        if (block.kind === 'work') {
          return (
            <Fragment key={block.id}>
              {durationLine}
              <WorkBlockDisclosure entries={block.entries} />
            </Fragment>
          )
        }
        const entry = block.entry
        // No end-of-turn text for a normal successful run (operator: "We don't want any
        // end-of-conversation message"). The event itself is untouched — only its card here.
        if (isSuccessCompletionEntry(entry)) return null
        if (entryCategory(entry) === 'result') {
          return (
            <Fragment key={entry.id}>
              {durationLine}
              <ResultCard entry={entry} turnKey={turnKey} />
            </Fragment>
          )
        }
        return (
          <Fragment key={entry.id}>
            {durationLine}
            <MessageEntry entry={entry} agentName={agentName} colorByName={colorByName} />
          </Fragment>
        )
      })}
    </>
  )
}

function WorkBlockDisclosure({ entries }: { entries: TimelineEntry[] }) {
  // Disclosure state is local to this block: a turn with several work groups
  // tracks each one independently rather than toggling as one.
  const [open, setOpen] = useState(false)
  // A tool_result is rendered inline with its tool_use, never as its own row — pairing is
  // computed within this block, not across the whole turn, so it can never reach across a
  // block boundary into a different run of work.
  const pairedResultIds = new Set(
    entries
      .filter((e) => e.output_kind === 'tool_use')
      .map((e) => findPairedResult(entries, e)?.id)
      .filter((id): id is string => Boolean(id)),
  )
  const workRows = entries.filter((e) => !pairedResultIds.has(e.id))
  const duration =
    entries.length > 1
      ? ((new Date(entries[entries.length - 1].timestamp).getTime() - new Date(entries[0].timestamp).getTime()) / 1000).toFixed(1)
      : null

  // What is worth knowing before opening this. "14 steps · 27.3s" says how much happened but not
  // whether any of it matters — a block that only read files and one that rewrote three of them
  // looked identical, so deciding whether to expand meant expanding. These are the two facts that
  // change the answer: files this block wrote to, and calls that failed.
  const highlights = useMemo(() => {
    const filesTouched = new Set<string>()
    let writes = 0
    let failures = 0
    for (const item of entries) {
      const payload = item.payload as Record<string, unknown> | null | undefined
      if (item.output_kind === 'tool_use' && typeof payload?.tool === 'string') {
        if (WRITING_TOOLS.has(payload.tool)) {
          writes += 1
          // Only a real `file_path` names a file. `callDetail` falls back to the raw input for
          // anything it cannot parse, and treating that as a path produced a "file" called
          // `{not valid json` — a name is only shown when the payload actually carries one.
          const fileName = writtenFileName(payload)
          if (fileName) filesTouched.add(fileName)
        }
      }
      if (item.output_kind === 'tool_result' && payload?.is_error === true) failures += 1
    }
    return { files: [...filesTouched], writes, failures }
  }, [entries])

  return (
    <details open={open} className="work-disclosure rounded-lg overflow-hidden">
      <summary
        onClick={(e) => {
          e.preventDefault()
          setOpen((v) => !v)
        }}
        className="flex items-center gap-1.5 py-[3px] text-[11.5px] cursor-pointer list-none"
        style={{ color: 'var(--text-3)' }}
      >
        <Icon
          name="expand_more"
          size={12}
          style={{ opacity: 0.55, transform: open ? undefined : 'rotate(-90deg)' }}
        />
        Work · {entries.length} step{entries.length === 1 ? '' : 's'}
        {duration ? ` · ${duration}s` : ''}
        {/* Louder than the step count deliberately: these are the reasons to open it. */}
        {highlights.writes > 0 && (
          <span
            className="inline-flex items-center gap-1 shrink-0"
            style={{ color: 'var(--text-2)' }}
            title={
              highlights.files.length > 0
                ? `Wrote to ${highlights.files.join(', ')}`
                : `${highlights.writes} write${highlights.writes === 1 ? '' : 's'}`
            }
          >
            <Icon name="edit" size={11} />
            {highlights.files.length === 1
              ? highlights.files[0]
              : highlights.files.length > 1
                ? `${highlights.files.length} files`
                : `${highlights.writes} edit${highlights.writes === 1 ? '' : 's'}`}
          </span>
        )}
        {highlights.failures > 0 && (
          <span
            className="inline-flex items-center gap-1 shrink-0"
            style={{ color: 'var(--red)' }}
            title={`${highlights.failures} call${highlights.failures === 1 ? '' : 's'} failed`}
          >
            <Icon name="alert_triangle" size={11} />
            {highlights.failures} failed
          </span>
        )}
      </summary>
      {open && (
        <div className="pl-[3px] py-1 text-[12px]" style={{ color: 'var(--text-2)' }}>
          {workRows.map((entry) => (
            <WorkRow key={entry.id} entry={entry} paired={findPairedResult(entries, entry)} />
          ))}
        </div>
      )}
    </details>
  )
}

/** design.md D2 — a fixed lookup, not inferred, keyed on `payload.tool`. Unmapped tool
 * names (a future runner's new tool) degrade to `TOOL_ICON_FALLBACK` rather than throwing. */
const TOOL_ICON: Record<string, { icon: string; label: string }> = {
  Read: { icon: 'description', label: 'Read' },
  Write: { icon: 'file_plus', label: 'Write' },
  Edit: { icon: 'edit', label: 'Edit' },
  MultiEdit: { icon: 'edit', label: 'Edit' },
  Bash: { icon: 'terminal', label: 'Bash' },
  Grep: { icon: 'search', label: 'Search' },
  Glob: { icon: 'folder_search', label: 'Find files' },
  WebFetch: { icon: 'public', label: 'Fetch' },
  WebSearch: { icon: 'search', label: 'Web search' },
  Task: { icon: 'group', label: 'Subagent' },
  Agent: { icon: 'group', label: 'Subagent' },
  TodoWrite: { icon: 'task_alt', label: 'Plan' },
  NotebookEdit: { icon: 'edit_note', label: 'Notebook' },
}
const TOOL_ICON_FALLBACK = { icon: 'build' }

/** Tools that change the workspace, as opposed to reading it. A block that wrote something is
 *  worth opening; one that only looked at things usually is not. */
const WRITING_TOOLS = new Set(['Edit', 'MultiEdit', 'Write', 'NotebookEdit', 'apply_patch'])

/** The bare filename a write targeted, or '' when the payload does not carry a usable path. */
function writtenFileName(payload: Record<string, unknown> | null | undefined): string {
  const input = payload?.input
  if (typeof input !== 'string') return ''
  let parsed: unknown
  try {
    parsed = JSON.parse(input)
  } catch {
    return ''
  }
  if (!parsed || typeof parsed !== 'object') return ''
  const fields = parsed as Record<string, unknown>
  const path = fields.file_path ?? fields.path
  if (typeof path !== 'string' || !path.trim()) return ''
  return path.split(/[\\/]/).pop() ?? ''
}

/** Codex and MCP name their tools differently from Claude, and every one of them was falling
 * through to the wrench — so a run of `shell`, `shell`, `agentweave.get_task` rendered as three
 * identical icons and the scanning the icons exist for was impossible. Measured on a real
 * verifier turn before this existed. MCP tools are matched by their `server.tool` prefix rather
 * than enumerated, since the tool set is whatever the operator has connected. */
function toolVisual(toolName: unknown): { icon: string; label?: string } {
  if (typeof toolName !== 'string' || !toolName) return TOOL_ICON_FALLBACK
  const direct = TOOL_ICON[toolName]
  if (direct) return direct
  if (toolName === 'shell' || toolName === 'local_shell') return { icon: 'terminal', label: 'Shell' }
  if (toolName.startsWith('agentweave.')) {
    return { icon: 'hub', label: toolName.slice('agentweave.'.length) }
  }
  if (toolName.includes('.')) return { icon: 'extension', label: toolName.split('.').slice(-1)[0] }
  // A name with no mapping and no namespace keeps the generic label it has always had: the
  // content line is more informative than echoing the bare name back.
  return TOOL_ICON_FALLBACK
}

/** The one field a reader actually wants from a call, per tool. `payload.input` is a JSON string
 * (the runner sends it that way), so a call that reads "Called Bash" carries the command all
 * along — it was simply never rendered, and expanding showed the label again instead. */
function callDetail(payload: unknown): string {
  const input = (payload as Record<string, unknown> | null | undefined)?.input
  if (typeof input !== 'string' || !input.trim()) return ''
  let parsed: unknown
  try {
    parsed = JSON.parse(input)
  } catch {
    return input // Not JSON: show it as sent rather than nothing.
  }
  if (!parsed || typeof parsed !== 'object') return String(parsed)
  const fields = parsed as Record<string, unknown>
  for (const key of ['command', 'file_path', 'path', 'pattern', 'query', 'url', 'prompt']) {
    const value = fields[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return JSON.stringify(parsed, null, 2)
}

function WorkRow({ entry, paired }: { entry: TimelineEntry; paired?: TimelineEntry }) {
  const [expanded, setExpanded] = useState(false)
  // design.md D2 — declines (returns null) for anything not shaped like a single-pair edit;
  // WorkRow falls back to the raw text rendering it already had for every other tool.
  const editDiff = entry.output_kind === 'tool_use' ? ToolEditDiff({ payload: entry.payload }) : null
  const label =
    entry.output_kind === 'thinking'
      ? 'Thinking'
      : entry.output_kind === 'tool_use'
        ? entry.content || 'Tool call'
        : entry.content || 'Tool result'
  const toolName = (entry.payload as Record<string, unknown> | null | undefined)?.tool
  const visual = toolVisual(toolName)
  const iconName = visual.icon
  const displayLabel = visual.label ?? label
  const detail = callDetail(entry.payload)
  // The size of the change, before opening it. "+12 −3" is the difference between a rename
  // and a rewrite, and that is the decision the collapsed row exists to support.
  const stat = entry.output_kind === 'tool_use' ? editDiffStat(entry.payload) : null
  // The result body is worth reading; the tool_use content is just "Called X", which the label
  // beside it already says. Repeating it was most of why expanding felt empty.
  const resultBody = paired && paired.content !== entry.content ? paired.content : ''
  const statusSuffix = paired
    ? (paired.payload as Record<string, unknown> | null | undefined)?.is_error === true
      ? ' · failed'
      : ' · completed'
    : entry.output_kind === 'tool_use'
      ? ' · awaiting result'
      : ''

  // A column, not a row. The expanded body used to be the fourth child of a `flex` row, so it
  // laid out to the RIGHT of the label instead of underneath it — a wide, unreadable column of
  // text beside the icon. The header keeps its own flex row; the body is its sibling below.
  return (
    <button
      onClick={() => setExpanded((v) => !v)}
      className="flex flex-col w-full text-left font-mono text-[12px] py-[2.5px]"
    >
      <span className="flex gap-[.55rem] items-baseline w-full min-w-0">
        <Icon name={iconName} size={12} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
        <b style={{ color: 'var(--text)', fontWeight: 500 }}>{displayLabel}</b>
        {/* The call's own subject, inline and truncated. Scanning a run of six `shell` calls is
            impossible when every row says only "shell". */}
        {detail && !expanded && (
          <span className="truncate min-w-0 flex-1" style={{ color: 'var(--text-3)' }}>
            {detail.split('\n')[0]}
          </span>
        )}
        {stat && (
          <span className="flex-shrink-0 tabular-nums" title={`${stat.added} added, ${stat.removed} removed`}>
            <span style={{ color: 'var(--green)' }}>+{stat.added}</span>{' '}
            <span style={{ color: 'var(--red)' }}>−{stat.removed}</span>
          </span>
        )}
        <span className="ml-auto flex-shrink-0" style={{ color: 'var(--text-3)' }}>
          {statusSuffix.replace(' · ', '')}
        </span>
      </span>
      {expanded &&
        (editDiff ?? (
          <span className="block mt-1 ml-[1.15rem] space-y-1">
            {detail && (
              <span
                className="block whitespace-pre-wrap px-2 py-1 rounded"
                style={{ color: 'var(--text-2)', background: 'var(--surface-2, var(--surface))' }}
              >
                {detail}
              </span>
            )}
            {resultBody && (
              <span className="block whitespace-pre-wrap" style={{ color: 'var(--text-3)' }}>
                {resultBody}
              </span>
            )}
            {!detail && !resultBody && (
              <span className="block" style={{ color: 'var(--text-3)' }}>
                No input or output was recorded for this call.
              </span>
            )}
          </span>
        ))}
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
        {isError ? (
          <div
            className="text-sm leading-[1.6] whitespace-pre-wrap break-words"
            style={{ color: 'var(--red)' }}
          >
            {entry.content}
          </div>
        ) : (
          <div className="text-sm leading-[1.6] break-words">
            <MarkdownMessage content={entry.content} />
          </div>
        )}
      </div>
    )
  }

  // Operator ("you") — right-aligned neutral bubble. Deliberately no hue: this used to be a
  // 14% `--blue` wash with a 30% blue border, which read as leftover navy against the charcoal
  // palette. `--blue` is the interface's single chromatic accent and is reserved for focus and
  // selection. Right-alignment plus a neutral surface already distinguishes it from peer
  // bubbles, which carry their own per-agent tint.
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
          className="max-w-[82%] px-[13px] py-[10px] text-sm leading-[1.6] break-words"
          style={{
            borderRadius: 'var(--radius-xl, 18px)',
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
            color: 'var(--text)',
          }}
        >
          <MarkdownMessage content={entry.content} />
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
      <div className="break-words" style={{ color: 'var(--text)' }}>
        <MarkdownMessage content={entry.content} />
      </div>
    </div>
  )
}
