import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import { ToolEditDiff } from '@/components/agents/ToolEditDiff'
import { editDiffStat } from '@/lib/editDiff'
import { formatElapsedSeconds, useElapsedSeconds } from '@/hooks/useElapsedSeconds'
import type { AgentRunFacts, AgentSummary, AgentTimelineEvent, RunLifecycleStatus } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import type { QueueStatus } from '@/api/queue'
import type { TurnUsage } from '@/api/accounting'
import { agentColorVars } from '@/lib/agentColors'
import { hubDate } from '@/lib/hubTime'
import {
  entryCategory,
  findPairedResult,
  groupIntoTurns,
  isSuccessCompletionEntry,
  reduceTurnBlocks,
  tokensByRunId,
  type TimelineTurn,
} from '@/lib/agentTimelineModel'

interface AgentTimelineProps {
  agent: AgentSummary
  entries: TimelineEntry[]
  roster: AgentSummary[]
  /** The agent's run-lifecycle events. Nothing in this component reads them any more — phase 4
   *  pointed all three former readers at `runs` — and the prop survives only because deleting it
   *  touches ~45 render sites, so task 4.6a decides it rather than this commit. Do not add a
   *  reader back: an event list the route truncates is exactly what F190 was. */
  timelineEvents: AgentTimelineEvent[]
  /** The facts of the runs `timelineEvents` names, keyed by `run_id`, straight from the
   *  timeline route. Required rather than optional and defaulted: a silently-empty map reads
   *  as "no run ended" everywhere it is consulted, which is the exact failure this change
   *  exists to delete. A caller with nothing to say must say `{}` on purpose. */
  runs: Record<string, AgentRunFacts>
  queueStatus?: QueueStatus
  isRunning: boolean
  onDeliverNow?: () => void
  onWithdraw?: (entryId: string) => void
  /** Continue a chain the hop budget is holding — re-bases the entry to depth 0 and
   *  delivers it. Offered only on entries the timeline marks `hop_budget_exceeded`. */
  onRelease?: (entryId: string) => void
  /** Bump to fold every turn — driven by the header's "Fold all turns" button. */
  foldAllSignal?: number
  /** The project's recent measured turns (accounting API) — matched to a rendered turn by
   *  `run_id` to show what it cost beside "Worked for Xs". Absent (not just empty) while
   *  accounting hasn't loaded yet, so no turn briefly claims "0 tokens". */
  recentTurns?: TurnUsage[]
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

/**
 * How long a finished run took, in whole seconds — from the run row's own timestamps.
 *
 * Deliberately not the live `useElapsedSeconds` counter: that measures how long *this browser
 * tab* watched a run, so it is null for every turn that finished before the page loaded and
 * wrong for one that began before it. "Worked for 12s" has to read the same after a refresh as
 * it did when the turn landed.
 *
 * This figure is RE-BASELINED rather than reconciled against the event-derived one it replaces
 * (design D4). `Run.started_at` is stamped when the row is constructed and the `run_started`
 * event only once the pty exists, so every duration now includes the spawn and reads a little
 * longer — and a run whose spawn failed outright has a duration for the first time, which is
 * the honest number rather than a regression.
 *
 * A run with no `ended_at` (still going, or the process died without one) is `undefined` rather
 * than 0 — the live indicator covers the first case and nothing should be claimed about the
 * second. So is a run whose clock went backwards between the two writes: "Worked for -3s" reads
 * as a bug in the product rather than in the clock.
 */
function runDurationSeconds(facts: AgentRunFacts | undefined): number | undefined {
  if (!facts?.ended_at) return undefined
  const start = Date.parse(facts.started_at)
  const end = Date.parse(facts.ended_at)
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return undefined
  return Math.round((end - start) / 1000)
}

type ColorLookup = Map<string, number | null | undefined>

export function AgentTimeline({
  agent,
  entries,
  roster,
  runs,
  queueStatus,
  isRunning,
  onDeliverNow,
  onWithdraw,
  onRelease,
  foldAllSignal,
  recentTurns,
}: AgentTimelineProps) {
  const colorByName: ColorLookup = useMemo(() => {
    const map = new Map<string, number | null | undefined>()
    for (const a of roster) map.set(a.name, a.color_index)
    return map
  }, [roster])

  const { turns, pending } = useMemo(() => groupIntoTurns(entries), [entries])
  const tokensByRun = useMemo(() => tokensByRunId(recentTurns ?? []), [recentTurns])

  // `isRunning` is `agent.status === 'running'` — a POLLED roster field, so it stays true for a
  // beat after the run has actually ended. The response text and the run's terminal lifecycle
  // event both arrive over SSE well before that poll lands, which left the live indicator sitting
  // underneath a finished answer, still counting, before flipping to "Worked for Xs" seconds
  // later (operator, 2026-08-18: "the working indicator then moves to under the message stays
  // active for a couple more seconds then disappears and collapse at the worked for one").
  //
  // So the indicator is gated on how the run itself says it went — the same source the settled
  // "Worked for Xs" line reads — which makes the handoff atomic: the instant the run's outcome
  // lands, the live counter goes and the settled line appears. `isRunning` is still required, so
  // the indicator cannot appear for an idle agent whose last run has no outcome recorded.
  // Two terminal signals, deliberately, because they arrive at very different speeds:
  //
  //   1. The run's own status line, which STREAMS in with the entries (`kind="status"`,
  //      `payload.phase="completed"` — the row `isSuccessCompletionEntry` hides from view). It
  //      lands the instant the run ends.
  //   2. `runs[runId].status` — the run row's own outcome, authoritative but arriving late: the
  //      SSE event only INVALIDATES the timeline query (`useAgentTimeline`), so the value costs
  //      a further HTTP round trip.
  //
  // Gating on (2) alone still left a visible tail — the counter kept running under a finished
  // answer for as long as the refetch took (operator, 2026-08-18: "It still linger a little
  // bit"). (1) closes that gap; (2) stays as the backstop for a run whose status line never
  // arrived, and for history loaded fresh where the entry is long since persisted.
  //
  // Signal 2 used to be reduced out of the lifecycle EVENTS instead, which is the defect this
  // change deletes: the route truncates its event list, so a run whose terminal event fell off
  // the end read as "still going" forever (F190). The run row cannot fall off — the route
  // returns a row for every run the events it returns name.
  const lastTurn = turns.length > 0 ? turns[turns.length - 1] : undefined
  const lastRunId = lastTurn?.runId ?? null
  const lastRunSettled =
    (lastTurn?.entries.some(isSuccessCompletionEntry) ?? false) ||
    (lastRunId !== null && TERMINAL_STATUSES.has(runs[lastRunId]?.status))

  // A run other than the newest loaded turn's, started and not yet ended. A new run's row is in
  // `runs` before that run's first entry has been grouped into a turn — the route returns a row
  // for every run its events name, and `run_started` is one of them — so this is the only signal
  // available in the window between the two.
  //
  // It is what makes stop-then-send work. Stopping settles run A; sending starts run B; and until
  // B's own entries arrive, the newest turn on screen is still the stopped A. Gating on the last
  // turn alone therefore hid the indicator for the whole of B (operator, 2026-08-20: "if I stop
  // the turn and send a new message the working indicator do not show anymore").
  //
  // Excluding `lastRunId` is what keeps the lingering-tail fix above intact: during the tail the
  // completed run's own status has not been refetched yet, so counting it here would show the
  // indicator under a finished answer — precisely the complaint that motivated the entry-based
  // signal in the first place.
  const anotherRunIsUnderway = useMemo(
    () =>
      Object.entries(runs).some(
        ([runId, facts]) => runId !== lastRunId && !TERMINAL_STATUSES.has(facts.status)
      ),
    [runs, lastRunId]
  )

  const runVisiblyActive = isRunning && (!lastRunSettled || anotherRunIsUnderway)

  // Timed from the run's own first entry rather than from when this pane mounted, so leaving
  // the conversation and returning does not restart the count. Only ever shown live; once the
  // run ends, `runDurationSeconds` (from the run row's own timestamps) takes over, so a refresh
  // does not change what a finished turn says it took.
  const activeRunStartedAt =
    runVisiblyActive && lastTurn?.entries.length ? lastTurn.entries[0].timestamp : null
  const liveElapsed = useElapsedSeconds(runVisiblyActive, activeRunStartedAt)
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
        className="timeline-empty-state flex h-full flex-col items-center justify-center px-6 text-center"
        style={{ color: 'var(--text-3)' }}
      >
        <span className="timeline-empty-icon" aria-hidden="true"><Icon name="chat" size={20} /></span>
        <p className="mt-3 text-[13px] font-semibold" style={{ color: 'var(--text)' }}>No conversation yet</p>
        <p className="mt-1 text-[11.5px]">Write below to start this thread.</p>
      </div>
    )
  }

  return (
    <div className="max-w-[960px] mx-auto flex flex-col gap-[21px] px-[30px]">
      {turns.map((turn, turnIndex) => {
        const key = turn.runId ?? `turn-${turnIndex}`
        const runStatus = turn.runId ? runs[turn.runId]?.status : undefined
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
          // `data-turn-boundary` is how AgentOutputPanel measures the newest turn, so it can size
          // the tail spacer and pin a just-sent message to the top of the viewport. A marker
          // rather than a ref because the panel owns the scroll container and this component owns
          // the turns; passing refs up for every turn would couple them far more tightly.
          <div key={key} data-turn-boundary="" className="flex flex-col gap-[21px]">
            {/* Every turn is foldable, including the last. Nothing folds on its own any more,
                so gating this on `!isLastTurn` would leave a single-turn conversation with no
                way to fold at all. */}
            <button
              onClick={() => setFoldOverride((old) => ({ ...old, [key]: true }))}
              className="fold-control self-start flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px]"
              style={{ color: 'var(--text-3)', opacity: 0.55 }}
              title="Fold this turn"
            >
              <Icon name="expand_more" size={13} />
              fold
            </button>
            <TurnBody
              turn={turn}
              turnKey={key}
              agentName={agent.name}
              colorByName={colorByName}
              durationSeconds={turn.runId ? runDurationSeconds(runs[turn.runId]) : undefined}
              tokenCount={turn.runId ? tokensByRun[turn.runId] : undefined}
            />
            {terminalLabel && (
              <div
                className="flex items-center gap-2 justify-center text-[12px]"
                style={{ color: 'var(--text-3)' }}
              >
                <span className="flex-1 h-px" style={{ background: 'var(--border)' }} />
                {terminalLabel}
                {turn.entries.length > 0 &&
                  ` · ${format(hubDate(turn.entries[turn.entries.length - 1].timestamp), 'HH:mm')}`}
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
          onRelease={onRelease}
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
            {/* This used to end "They'll be delivered with your next message", which described
                the leak this change closes: an operator message no longer releases the chain,
                and saying so would send the operator to do something that does nothing. Name
                what to do instead — Continue delivers them and restarts the count from here,
                Discard on each entry drops it, and raising the project's hop budget admits
                them at the depth they already have. */}
            reached the hop budget. Continue to deliver them and restart the count from here,
            or discard them individually below.
          </div>
          {onDeliverNow && (
            <button
              onClick={onDeliverNow}
              className="shrink-0 text-[12px] font-medium px-2 py-1 rounded"
              style={{ color: 'var(--text-2)' }}
            >
              Continue
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
      className="fold-control flex items-center gap-1.5 self-center rounded-full px-2.5 py-1 text-[11px] text-left"
      style={{ border: '1px solid var(--border-region)', background: 'var(--surface-2)', color: 'var(--text-3)' }}
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
  tokenCount,
}: {
  turn: TimelineTurn
  turnKey: string
  agentName: string
  colorByName: ColorLookup
  /** Whole-run duration for a finished turn; undefined while running or if unknown. */
  durationSeconds?: number
  /** Total tokens this turn measured, from the accounting API; undefined if unmeasured. */
  tokenCount?: number
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
        // The token count rides the same line (Q7 Gap 5) rather than a second one — both are
        // "what this turn cost", and a turn with a duration but no measured usage (or vice
        // versa) still reads as one fact, not a half-empty second line.
        const statLine = [
          durationSeconds !== undefined ? `Worked for ${formatElapsedSeconds(durationSeconds)}` : null,
          tokenCount !== undefined ? `${tokenCount.toLocaleString()} tokens` : null,
        ]
          .filter((part): part is string => part !== null)
          .join(' · ')
        const durationLine =
          statLine && blockId === firstAgentBlockId ? (
            <div
              key={`worked-${blockId}`}
              className="text-[11px]"
              style={{ color: 'var(--text-3)' }}
              data-testid="turn-worked-for"
            >
              {statLine}
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
      ? ((hubDate(entries[entries.length - 1].timestamp).getTime() - hubDate(entries[0].timestamp).getTime()) / 1000).toFixed(1)
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
          size={14}
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
            <Icon name="edit" size={13} />
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
            <Icon name="alert_triangle" size={13} />
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
        <Icon name={iconName} size={14} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
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
  onRelease,
}: {
  entry: TimelineEntry
  agentName: string
  colorByName: ColorLookup
  queued?: boolean
  onWithdraw?: (entryId: string) => void
  onRelease?: (entryId: string) => void
}) {
  const time = format(hubDate(entry.timestamp), 'HH:mm')
  const fullTime = format(hubDate(entry.timestamp), 'EEE d MMM, HH:mm:ss')
  const timestamp = (
    <time className="timeline-timestamp font-normal" dateTime={entry.timestamp} data-full-time={fullTime} title={fullTime}>
      {time}
    </time>
  )
  // The Hub stopped trying to deliver this one. It arrives in the same `pending` group a waiting
  // entry does — `delivery_state !== 'delivered'` is what puts it there — but it is the opposite
  // fact: nothing is going to happen to it. Before this it was filtered out of the thread
  // entirely, so a dropped message and a delivered one looked the same here (F87).
  const abandoned = entry.delivery_state === 'abandoned'
  const wrapperStyle: React.CSSProperties = { opacity: queued ? 0.55 : 1 }
  const queuedTag = queued && (
    <span className="inline-flex items-center gap-[.35rem]">
      <span
        className="inline-flex items-center h-[18px] px-[.4rem] rounded text-[10.5px] font-semibold uppercase tracking-wide"
        style={
          abandoned
            ? { background: 'color-mix(in oklab, var(--red) 16%, transparent)', color: 'var(--red)' }
            : { background: 'var(--accent)', color: 'var(--text-3)' }
        }
      >
        {abandoned ? 'not delivered' : 'queued'}
      </span>
      {/* The reason, in the header row every shape below renders, rather than under the content
          each of them renders differently. Without it the chip states that something was lost and
          not what to do about it — and the reason names the remedy ("no commit to review", "the
          workspace is unavailable") in every case the Hub gives up for. */}
      {abandoned && entry.abandoned_reason && (
        <span className="font-normal text-[11px]" style={{ color: 'var(--text-3)' }}>
          {entry.abandoned_reason}
        </span>
      )}
    </span>
  )
  // Continue only where the hop budget is what is holding the entry. Elsewhere the entry is
  // waiting for something a re-base would not fix — an agent already running, a missing CLI —
  // and the endpoint refuses, so offering the button there would be an offer to be told no.
  const held = queued && entry.hop_budget_exceeded === true
  // Nothing to withdraw and nothing to continue: both endpoints refuse a row that is no longer
  // `queued`, so every control here would be an offer to be told no.
  const actions = queued && !abandoned && (onWithdraw || onRelease) && (
    <span className="inline-flex items-center gap-[.35rem]">
      {held && onRelease && (
        <button
          onClick={() => onRelease(entry.id)}
          title="Deliver this now, restarting the chain's count from here"
          className="text-[11px] font-medium px-[.35rem] h-[18px] rounded"
          style={{ color: 'var(--amber)' }}
        >
          Continue
        </button>
      )}
      {onWithdraw && (
        <button
          onClick={() => onWithdraw(entry.id)}
          title={held ? 'Discard — this message is never delivered' : "Withdraw before it's delivered"}
          className="text-[11px]"
          style={{ color: 'var(--text-3)' }}
        >
          {held ? 'Discard' : <Icon name="close" size={14} />}
        </button>
      )}
    </span>
  )

  // Own plain text (or an error) — borderless, no bubble, just a "who" line.
  if (entry.kind === 'agent_output') {
    const isError = entry.output_kind === 'error'
    const colors = agentColorVars(colorByName.get(agentName))
    return (
      <div className="timeline-message-row flex flex-col gap-[5px]" style={wrapperStyle}>
        <div className="flex items-center gap-[.4rem] text-[11.5px] font-semibold" style={{ color: 'var(--text-2)' }}>
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: isError ? 'var(--red)' : colors.accent }}
          />
          {agentName}
          {timestamp}
          {queuedTag}
          {actions}
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
      <div className="timeline-message-row timeline-message-row-mine flex flex-col items-end gap-[5px]" style={wrapperStyle}>
        <div className="flex items-center gap-[.4rem] text-[11.5px] font-semibold" style={{ color: 'var(--text-2)' }}>
          {queuedTag}
          {actions}
          you
          {timestamp}
        </div>
        <div
          className="timeline-bubble max-w-[82%] px-[13px] py-[10px] text-sm leading-[1.6] break-words"
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

  // Outbound peer traffic folds — see OutboundMessageEntry. Inbound stays a full, always-open
  // bubble: it is the reply the operator is reading this thread for, not the agent's own
  // delegating chatter (design.md phase 6).
  if (entry.kind === 'outbound_peer') {
    return (
      <OutboundMessageEntry
        entry={entry}
        agentName={agentName}
        colorByName={colorByName}
        time={time}
        wrapperStyle={wrapperStyle}
        queuedTag={queuedTag}
        actions={actions}
      />
    )
  }

  const colors = agentColorVars(colorByName.get(entry.participant || ''))
  const { name } = participantLabel(entry, agentName)

  return (
    <div
      className="timeline-message-row timeline-bubble px-[13px] py-[10px] text-sm"
      style={{
        borderRadius: 'var(--radius-xl, 18px)',
        border: `1px solid ${colors.border}`,
        background: colors.tint,
        ...wrapperStyle,
      }}
    >
      <div className="flex items-center gap-[.4rem] mb-[5px] text-[11.5px] font-semibold" style={{ color: colors.accent }}>
        {name}
        <span className="font-normal" style={{ color: 'var(--text-3)' }}>
          → {agentName}
        </span>
        {timestamp}
        {queuedTag}
        {actions}
      </div>
      <div className="break-words" style={{ color: 'var(--text)' }}>
        <MarkdownMessage content={entry.content} />
      </div>
    </div>
  )
}

/** An outbound peer message, folded — header row plus an inline truncated preview, `useState`
 * for expansion. Same shape as `WorkRow`: a delegation the agent sent is closer to a tool call
 * than to a reply the operator wants to read inline, and unfolded it was most of why a thread
 * with several delegations read as noise rather than conversation.
 *
 * `subject` is the preview when present; `send_message` requires it going forward, but the
 * column is nullable and predates that requirement, so an older row falls back to the first
 * line of its content (task 6.5) rather than showing nothing. */
function OutboundMessageEntry({
  entry,
  agentName,
  colorByName,
  time,
  wrapperStyle,
  queuedTag,
  actions,
}: {
  entry: TimelineEntry
  agentName: string
  colorByName: ColorLookup
  time: string
  wrapperStyle: React.CSSProperties
  queuedTag: React.ReactNode
  actions: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(false)
  const colors = agentColorVars(colorByName.get(entry.participant || ''))
  const { name } = participantLabel(entry, agentName)
  const preview = entry.subject?.trim() || entry.content.split('\n')[0]?.trim() || 'Message'

  return (
    <div
      className="timeline-outbound-row px-[13px] py-[10px] text-sm"
      style={{
        borderRadius: 'var(--radius-xl, 18px)',
        borderLeft: `2px solid ${colors.accent}`,
        background: 'transparent',
        ...wrapperStyle,
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        data-preserve-bottom-on-resize=""
        className="flex items-baseline gap-[.4rem] w-full min-w-0 text-left text-[11.5px] font-semibold"
        style={{ color: colors.accent }}
      >
        <span className="flex-shrink-0">{agentName}</span>
        <span className="font-normal flex-shrink-0" style={{ color: 'var(--text-3)' }}>
          → {name}
        </span>
        {!expanded && (
          <span className="truncate min-w-0 flex-1 font-normal" style={{ color: 'var(--text-3)' }}>
            {preview}
          </span>
        )}
        <span className="ml-auto flex-shrink-0 font-normal" style={{ color: 'var(--text-3)' }}>
          {time}
        </span>
      </button>
      {(queuedTag || actions) && (
        <div className="flex items-center gap-[.4rem] mt-1">
          {queuedTag}
          {actions}
        </div>
      )}
      {expanded && (
        <div className="break-words mt-[6px]" style={{ color: 'var(--text)' }}>
          <MarkdownMessage content={entry.content} />
        </div>
      )}
    </div>
  )
}
