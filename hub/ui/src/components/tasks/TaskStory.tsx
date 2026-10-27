import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill, type Tone } from '@/components/common/StatePill'
import { Timeline, TimelineItem } from '@/components/common/Timeline'
import { Expander } from '@/components/common/Expander'
import { EvidenceProof as Proof, EvidenceReviews as Reviews } from '@/components/evidence/EvidenceProof'
import { EvidenceLink } from '@/components/evidence/EvidenceLink'
import { ConversationLink } from '@/components/agents/ConversationLink'
import { TraceButton } from '@/components/traces/TraceDrawer'
import { useTaskStory, type StoryEvent, type TaskStory as Story } from '@/api/tasks'
import { hubDate } from '@/lib/hubTime'
import { evidenceTone, statusTone } from '@/lib/storyTones'
import { formatAiCreditAmount, formatAiCredits } from '@/components/accounting/accountingDisplay'
import { LoadingThread } from '@/components/common/LoadingThread'

/**
 * A task's whole story (slice task-story of the visibility roadmap): a summary that answers "is
 * this done?", then everything that happened to the task, oldest first, in the order the Hub's
 * `/story` route returns it. Evidence opens into its proof: the requirement's wording beside what
 * demonstrates it, the command and its output, the diff of the work, and every review of it.
 */

const STATUS_LABEL: Record<string, string> = {
  pending: 'pending',
  assigned: 'assigned',
  in_progress: 'in progress',
  completed: 'completed',
  under_review: 'under review',
  approved: 'approved',
  revision_needed: 'sent back',
  rejected: 'rejected',
  blocked: 'waiting on you',
}

/** How long an arrival glows (`aw-fresh` in styles/story.css runs 1.6s). */
const FRESH_MS = 1700

function money(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value > 0 && value < 0.01) return '<$0.01'
  return `$${value.toFixed(2)}`
}

/** A run row's cost: dollars where its runner priced the work, Copilot's AI credits where it
 * charged them, both if it reported both; null when nothing was reported. Credits are never
 * converted to dollars. */
function spend(usd: number | null, nano: number | null): string | null {
  const credits = formatAiCredits(nano)
  if (usd == null) return credits
  return credits ? `${money(usd)} · ${credits}` : money(usd)
}

/** The summary's Cost cell: the headline on the value line, which never wraps, and its unit and
 * extras on the line under it, so `12.04` / `AI credits · 1 req` fits a narrow cell. */
function costCell(summary: Story['summary']): { value: string; sub: string | null } {
  const credits = formatAiCreditAmount(summary.ai_nano_aiu)
  const sub: string[] = []
  let value = money(summary.cost_usd)
  if (summary.cost_usd != null) {
    if (credits) sub.push(`+ ${credits} AI credits`)
  } else if (credits) {
    value = credits
    sub.push('AI credits')
  }
  if (summary.premium_requests) sub.push(`${summary.premium_requests} req`)
  return { value, sub: sub.length ? sub.join(' · ') : null }
}

function count(value: number | null | undefined): string {
  if (value == null) return ''
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M tokens`
  if (value >= 1_000) return `${Math.round(value / 1_000)}k tokens`
  return `${value} tokens`
}

function duration(seconds: number | null): string | null {
  if (seconds == null) return null
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function when(value: string | null): { label: string; exact: string } | null {
  if (!value) return null
  const date = hubDate(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  let label: string
  if (seconds < 45) label = 'just now'
  else if (seconds < 3600) label = `${Math.round(seconds / 60)}m ago`
  else if (seconds < 86400) label = `${Math.round(seconds / 3600)}h ago`
  else label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return { label, exact: date.toLocaleString() }
}

function Time({ value }: { value: string | null }) {
  const at = when(value)
  return at ? <time title={at.exact}>{at.label}</time> : null
}

function short(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 8) : ''
}

function Summary({ story }: { story: Story }) {
  const { summary, task } = story
  const { accepted, rejected, awaiting } = summary.evidence
  // K: held at its commit by a send-back that did not name it as failing; counted apart from
  // rejected, which it is not.
  const held = summary.evidence.held ?? 0
  const merged = summary.merged[summary.merged.length - 1]
  const cost = costCell(summary)
  return (
    <div className="aw-story-summary" data-testid={`task-story-summary-${task.id}`}>
      <div>
        <span className="aw-story-label">State</span>
        <span>
          <StatePill key={task.status} tone={statusTone(task.status)}>
            {STATUS_LABEL[task.status] ?? task.status}
          </StatePill>
        </span>
      </div>
      <div>
        <span className="aw-story-label">Cost</span>
        <span className="aw-story-value" title={count(summary.tokens) || undefined}>
          {cost.value}
        </span>
        {cost.sub ? (
          <span className="aw-story-sub" title={cost.sub}>
            {cost.sub}
          </span>
        ) : null}
      </div>
      <div>
        <span className="aw-story-label">Runs</span>
        <span className="aw-story-value">{summary.runs}</span>
      </div>
      <div>
        <span className="aw-story-label aw-story-label-row">
          Evidence
          {accepted + awaiting + rejected + held > 0 ? (
            <EvidenceLink focus={task.id} testId={`task-story-evidence-open-${task.id}`}>
              See all
            </EvidenceLink>
          ) : null}
        </span>
        <span className="aw-counts">
          {accepted + awaiting + rejected + held === 0 ? <small className="aw-tl-meta">none yet</small> : null}
          {accepted ? <span className="tone-green">{accepted} accepted</span> : null}
          {awaiting ? <span className="tone-amber">{awaiting} waiting</span> : null}
          {rejected ? <span className="tone-red">{rejected} rejected</span> : null}
          {held ? (
            <span className="tone-neutral" title="Not named as failing when the task was sent back; recorded again at the next commit">
              {held} held
            </span>
          ) : null}
        </span>
      </div>
      <div>
        <span className="aw-story-label">Merged</span>
        <span className="aw-story-value" title={merged ?? undefined}>
          {merged ? short(merged) : <small>not yet</small>}
        </span>
      </div>
    </div>
  )
}

function EvidenceItem({
  event,
  index,
  fresh,
}: {
  event: Extract<StoryEvent, { kind: 'evidence' }>
  index: number
  fresh: boolean
}) {
  const [open, setOpen] = useState(false)
  const piece = event.evidence
  const proofId = `proof-${piece.id}`
  return (
    <TimelineItem
      tone="purple"
      icon="fact_check"
      index={index}
      fresh={fresh}
      testId={`story-event-${event.id}`}
      head={
        <>
          <span>
            Evidence for <code>{piece.requirement?.identifier ?? 'a requirement'}</code>
          </span>
          <StatePill key={piece.review_state} tone={evidenceTone(piece.review_state)}>
            {piece.review_state}
          </StatePill>
          {piece.superseded_by ? <span className="aw-tl-meta">replaced by a later piece</span> : null}
        </>
      }
      meta={
        <>
          {piece.actor_kind === 'operator' ? 'you' : piece.actor} · <Time value={event.at} />
        </>
      }
    >
      {piece.summary ? (
        <p className="text-[12.5px] leading-relaxed" style={{ color: 'var(--text-2)' }}>
          {piece.summary}
        </p>
      ) : null}
      <Reviews reviews={event.reviews} />
      <div>
        <button
          type="button"
          className="aw-link"
          aria-expanded={open}
          aria-controls={proofId}
          onClick={() => setOpen((value) => !value)}
          data-testid={`evidence-proof-toggle-${piece.id}`}
        >
          <Icon name="chevron_right" size={12} aria-hidden="true" />
          {open ? 'Hide the proof' : 'Show the proof'}
        </button>
      </div>
      <Expander open={open} id={proofId}>
        <Proof piece={piece} open={open} />
      </Expander>
    </TimelineItem>
  )
}

/** Where each of the story's runs happened, so a transition a run made can link to it. */
type RunPlaces = Map<string, { agent: string; conversation_id: string }>

function renderEvent(event: StoryEvent, index: number, fresh: boolean, runs: RunPlaces) {
  const common = { index, fresh, testId: `story-event-${event.id}` }
  switch (event.kind) {
    case 'created':
      return (
        <TimelineItem
          key={`created-${event.id}`}
          {...common}
          tone="neutral"
          icon="add"
          head={<span>Created{event.by ? <> by <strong>{event.by}</strong></> : null}</span>}
          meta={<Time value={event.at} />}
        />
      )
    case 'transition': {
      const who =
        event.origin === 'job'
          ? event.job
            ? `${event.job_kind === 'flow' ? 'Flow' : 'Loop'} ${event.job}`
            : 'A scheduled job'
          : event.origin === 'checks'
            ? // The project's checks returned work their run failed (operator's authority, not act).
              'The project’s checks'
            : event.actor_kind === 'operator'
              ? 'You'
              : event.actor ?? 'A run'
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone={statusTone(event.to)}
          icon="arrow_forward"
          head={
            <>
              <span>
                <strong>{who}</strong> {event.origin === 'runtime' ? 'was moved to' : 'moved it to'}
              </span>
              <StatePill tone={statusTone(event.to)}>{STATUS_LABEL[event.to] ?? event.to}</StatePill>
            </>
          }
          meta={
            <>
              from {STATUS_LABEL[event.from] ?? event.from} · <Time value={event.at} />
              {event.run_id && runs.get(event.run_id) ? (
                <>
                  {' · '}
                  <ConversationLink
                    agent={runs.get(event.run_id)!.agent}
                    conversationId={runs.get(event.run_id)!.conversation_id}
                    testId={`story-transition-run-${event.id}`}
                  >
                    in its conversation
                  </ConversationLink>
                </>
              ) : null}
            </>
          }
        >
          {event.override_reason ? (
            event.override_by === 'hub' ? (
              <div className="aw-callout tone-blue" data-testid={`story-override-${event.id}`} data-override-by="hub">
                <strong>Approved by the Hub over failures that were not this task's.</strong> {event.override_reason}
              </div>
            ) : (
              <div className="aw-callout tone-amber" data-testid={`story-override-${event.id}`} data-override-by="operator">
                <strong>Approved over failing checks.</strong> {event.override_reason}
              </div>
            )
          ) : null}
        </TimelineItem>
      )
    }
    case 'run': {
      const running = event.status === 'running'
      const failed = ['failed', 'interrupted', 'stopped'].includes(event.status)
      const parts = [duration(event.duration_seconds), count(event.tokens)].filter(Boolean)
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone={failed ? 'red' : 'blue'}
          icon="smart_toy"
          live={running}
          head={
            <span>
              <strong>{event.agent}</strong> {running ? 'is working' : 'worked'}
              {event.model ? <span className="aw-tl-meta"> · {event.model}</span> : null}
            </span>
          }
          aside={spend(event.cost_usd, event.ai_nano_aiu) ?? undefined}
          meta={
            <>
              {parts.length ? `${parts.join(' · ')} · ` : ''}
              {failed ? `${event.status} · ` : ''}
              <Time value={event.at} />
              {event.conversation_id ? (
                <>
                  {' · '}
                  <ConversationLink
                    agent={event.agent}
                    conversationId={event.conversation_id}
                    testId={`story-run-conversation-${event.id}`}
                  >
                    conversation
                  </ConversationLink>
                </>
              ) : null}
              {/* A run event's id is the run's own id (`task_story.py`), which is what a trace
                  is keyed by. */}
              {' · '}
              <TraceButton runId={event.id} label="trace" testId={`story-run-trace-${event.id}`} />
            </>
          }
        >
          {event.error ? <div className="aw-callout tone-red">{event.error}</div> : null}
        </TimelineItem>
      )
    }
    case 'evidence':
      return <EvidenceItem key={event.id} event={event} index={index} fresh={fresh} />
    case 'check': {
      const tone: Tone =
        event.state === 'passed'
          ? 'green'
          : event.state === 'failed'
            ? 'red'
            : event.state === 'running'
              ? 'blue'
              : 'amber'
      const failing = event.results.filter((r) => !r.skipped && (r.passed === false || (r.exit_code ?? 0) !== 0))
      const skipped = event.results.filter((r) => r.skipped)
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone={tone}
          icon="task_alt"
          live={event.state === 'running'}
          head={<span>Checks {event.state}</span>}
          meta={<Time value={event.at} />}
        >
          {failing.length ? (
            <div className="aw-callout tone-red">
              {failing.map((r) => r.name ?? r.command).filter(Boolean).join(', ')}
            </div>
          ) : null}
          {skipped.length ? (
            <div className="aw-callout">
              {skipped.map((r) => r.name ?? r.command).filter(Boolean).join(', ')} skipped (no matching changes)
            </div>
          ) : null}
          {event.error ? <div className="aw-callout tone-amber">{event.error}</div> : null}
        </TimelineItem>
      )
    }
    case 'integration': {
      const merged = event.outcome === 'merged'
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone={merged ? 'green' : 'amber'}
          icon="call_split"
          head={
            <span>
              {merged ? (
                <>
                  <strong>Merged</strong> into {event.target_branch ?? 'main'}
                </>
              ) : (
                <>
                  <strong>Not merged</strong>
                  {event.outcome !== 'skipped' ? ` (${event.outcome})` : ''}
                </>
              )}
            </span>
          }
          meta={
            <>
              {event.commit_sha ? `${short(event.commit_sha)} · ` : ''}
              {event.source_branch ? `${event.source_branch} · ` : ''}
              <Time value={event.at} />
            </>
          }
        >
          {!merged && event.reason ? <div className="aw-callout tone-amber">{event.reason}</div> : null}
        </TimelineItem>
      )
    }
    case 'divergence':
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone="amber"
          icon="warning"
          head={
            <span>
              <strong>{event.agent}</strong>’s turn ended with the task still{' '}
              {STATUS_LABEL[event.task_status_at_end] ?? event.task_status_at_end}
            </span>
          }
          meta={
            <>
              {event.outcome}
              {event.resolved_at ? ' · resolved' : ''} · <Time value={event.at} />
            </>
          }
        />
      )
    case 'question':
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone="amber"
          icon="help_circle"
          head={
            <span>
              <strong>{event.agent}</strong> asked you
            </span>
          }
          meta={<Time value={event.at} />}
        >
          <div className="aw-callout tone-amber">
            {event.question}
            {event.answered && event.answer ? (
              <>
                <br />
                <strong>You answered:</strong> {event.answer}
              </>
            ) : event.declined ? (
              <>
                <br />
                <strong>You declined.</strong>
              </>
            ) : null}
          </div>
        </TimelineItem>
      )
    case 'turn': {
      const what = event.review ? 'review' : 'turn'
      const head =
        event.state === 'abandoned'
          ? `’s ${what} was given up`
          : event.state === 'withdrawn'
            ? `’s ${what} was withdrawn`
            : event.state === 'delivered'
              ? `’s ${what} was refused before it ran`
              : `’s ${what} is held`
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone="amber"
          icon="warning"
          head={
            <span>
              <strong>{event.agent}</strong>
              {head}
            </span>
          }
          meta={
            <>
              queued <Time value={event.at} />
              {event.attempts > 0 ? ` · ${event.attempts} ${event.attempts === 1 ? 'attempt' : 'attempts'}` : ''}
            </>
          }
        >
          {event.refusal || event.ended_reason ? (
            <div className="aw-callout tone-amber">{event.ended_reason ?? event.refusal}</div>
          ) : null}
        </TimelineItem>
      )
    }
    case 'workspace':
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone="amber"
          icon="warning"
          head={<span>The task’s checkout could not be released</span>}
          meta={<Time value={event.at} />}
        >
          {event.reason ? <div className="aw-callout tone-amber">{event.reason}</div> : null}
        </TimelineItem>
      )
    case 'review_unstaffed':
      return (
        <TimelineItem
          key={event.id}
          {...common}
          tone="amber"
          icon="warning"
          head={<span>Nobody could be found to review this</span>}
          meta={<Time value={event.at} />}
        >
          {event.reason ? <div className="aw-callout tone-amber">{event.reason}</div> : null}
        </TimelineItem>
      )
  }
}

function Loading() {
  return (
    <LoadingThread label="Loading the story" />
  )
}

export function TaskStory({ taskId }: { taskId: string }) {
  const { data, isLoading, isError } = useTaskStory(taskId, true)
  // Events seen on the first render stay quiet; one that arrives later glows once. Its arrival
  // time is kept, so a refetch inside the glow (a run's events come in bursts) does not cut it off.
  const arrived = useRef<Map<string, number> | null>(null)
  useEffect(() => {
    arrived.current = null
  }, [taskId])

  if (isLoading) return <Loading />
  if (isError || !data || !Array.isArray(data.events)) return null

  const now = Date.now()
  const firstRender = arrived.current === null
  const times = arrived.current ?? new Map<string, number>()
  const runs: RunPlaces = new Map()
  for (const event of data.events) {
    if (event.kind === 'run' && event.conversation_id) {
      runs.set(event.id, { agent: event.agent, conversation_id: event.conversation_id })
    }
  }
  const items = data.events.map((event, index) => {
    const key = `${event.kind}-${event.id}`
    if (!times.has(key)) times.set(key, firstRender ? 0 : now)
    const fresh = now - (times.get(key) ?? 0) < FRESH_MS
    return renderEvent(event, fresh ? 0 : index, fresh, runs)
  })
  arrived.current = times

  return (
    <div className="grid gap-4" data-testid={`task-story-${taskId}`}>
      <Summary story={data} />
      <Timeline testId={`task-story-events-${taskId}`}>{items}</Timeline>
    </div>
  )
}
