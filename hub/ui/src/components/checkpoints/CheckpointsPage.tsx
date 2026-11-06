import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill } from '@/components/common/StatePill'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import { MenuSelect } from '@/components/ui/menu'
import { TraceButton } from '@/components/traces/TraceDrawer'
import type { CheckpointNote, ProjectCheckpoint, ProjectCheckpointList } from '@/api/checkpoints'
import { formatDateTime } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'
import {
  checkpointTitle,
  findingWords,
  madeByHub,
  madeByHubWords,
  statusWords,
  triggerWords,
  TRIGGER_FILTER_OPTIONS,
  type CheckpointFilters,
} from './checkpointModel'
import '@/styles/checkpoints.css'

/**
 * The Checkpoints tab: every checkpoint the project holds, what tells one from another, and one
 * opened as readable text. Presentational — the container (or the mock) gives it the route's data,
 * in the order the route returns it (newest first), and takes its callbacks.
 */

const ALL = 'all'

export interface CheckpointsPageProps {
  checkpoints: ProjectCheckpoint[]
  lineage: ProjectCheckpointList['lineage']
  filters: CheckpointFilters
  onFilters: (next: CheckpointFilters) => void
  /** Agents the filter offers. */
  agents: string[]
  /** Conversations the filter offers, newest first. */
  conversations: Array<{ id: string; label: string }>
  /** What a conversation is called; never its identifier. */
  conversationLabel: (conversationId: string) => string
  selectedId: string | null
  /** The opened checkpoint when the narrowing hides it from `checkpoints` (a link to a checkpoint
   *  of another conversation); otherwise it is found in `checkpoints`. */
  opened?: ProjectCheckpoint | null
  onSelect: (checkpointId: string | null) => void
  /** The notes agents asked this checkpoint to carry (already limited to the opened one). */
  notes?: CheckpointNote[]
  /** The raw text of an answer the Hub could not read, once asked for. */
  rawAnswer?: string | null
  onShowRaw?: (checkpointId: string) => void
  onOpenConversation?: (agent: string | null, conversationId: string) => void
  /** Start a conversation of `agent` from the opened checkpoint; the container opens the result. */
  onStart?: (checkpointId: string, agent: string, message: string) => Promise<void>
  /** The project's open agents, which a start may choose from (the filter's `agents` also holds archived ones). */
  startAgents?: string[]
  loading?: boolean
  error?: boolean
  now?: Date
}

function when(value: string | null | undefined, now?: Date): string {
  return value ? formatDateTime(hubDate(value), now) : ''
}

function CheckpointRow({
  checkpoint,
  conversationLabel,
  selected,
  onSelect,
  now,
}: {
  checkpoint: ProjectCheckpoint
  conversationLabel: string
  selected: boolean
  onSelect: () => void
  now?: Date
}) {
  const status = statusWords(checkpoint.status)
  return (
    <li>
      <button
        type="button"
        data-slot="checkpoint-row"
        className="aw-ckpts-row"
        data-selected={selected ? 'true' : 'false'}
        aria-current={selected ? 'true' : undefined}
        data-testid={`checkpoint-row-${checkpoint.id}`}
        onClick={onSelect}
      >
        <span className="aw-ckpts-row-top">
          <span className="aw-ckpts-title" data-testid="checkpoint-row-title">
            {checkpointTitle(checkpoint)}
          </span>
          <StatePill tone={status.tone}>
            <span data-testid="checkpoint-row-status">{status.label}</span>
          </StatePill>
        </span>
        {checkpoint.summary ? (
          <span className="aw-ckpts-summary" data-testid="checkpoint-row-summary">
            {checkpoint.summary}
          </span>
        ) : null}
        <span className="aw-ckpts-meta">
          <span data-testid="checkpoint-row-agent">{checkpoint.agent}</span>
          <span data-testid="checkpoint-row-trigger">{triggerWords(checkpoint.trigger)}</span>
          <span data-testid="checkpoint-row-time">{when(checkpoint.created_at, now)}</span>
          <span className="aw-ckpts-conversation" data-testid="checkpoint-row-conversation">
            {conversationLabel}
          </span>
        </span>
      </button>
    </li>
  )
}

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId?: string }) {
  return (
    <section className="aw-ckpts-section" data-testid={testId}>
      <h4 className="aw-ckpts-label">{title}</h4>
      {children}
    </section>
  )
}

function StartPanel({
  checkpoint,
  agents,
  onStart,
}: {
  checkpoint: ProjectCheckpoint
  agents: string[]
  onStart: (checkpointId: string, agent: string, message: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [chosen, setAgent] = useState(checkpoint.agent)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  // The checkpoint's own agent first (when it is open), then the rest.
  const choices = [...agents.filter((name) => name === checkpoint.agent), ...agents.filter((name) => name !== checkpoint.agent)]
  const agent = choices.includes(chosen) ? chosen : (choices[0] ?? chosen)
  const confirm = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await onStart(checkpoint.id, agent, message)
      setOpen(false)
      setMessage('')
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'The conversation could not be started.')
    } finally {
      setBusy(false)
    }
  }
  if (!open) {
    return (
      <button
        type="button"
        data-slot="checkpoint-start"
        className="aw-link"
        data-testid="checkpoint-start-open"
        onClick={() => setOpen(true)}
      >
        Start a conversation
      </button>
    )
  }
  return (
    <div className="aw-ckpts-start" data-testid="checkpoint-start-form">
      <select
        aria-label="Agent"
        data-testid="checkpoint-start-agent"
        value={agent}
        onChange={(event) => setAgent(event.target.value)}
      >
        {choices.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <textarea
        data-testid="checkpoint-start-message"
        aria-label="Message (optional)"
        placeholder="A message to follow the checkpoint (optional)"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        rows={3}
      />
      {failure ? <p className="aw-callout tone-red" data-testid="checkpoint-start-error">{failure}</p> : null}
      <button type="button" data-slot="checkpoint-start-confirm" data-testid="checkpoint-start-confirm" disabled={busy} onClick={confirm}>
        Start
      </button>
      <button type="button" className="aw-link" disabled={busy} onClick={() => setOpen(false)}>
        Cancel
      </button>
    </div>
  )
}

function CheckpointDetail({
  checkpoint,
  props,
}: {
  checkpoint: ProjectCheckpoint
  props: CheckpointsPageProps
}) {
  const { conversationLabel, notes = [], rawAnswer, onShowRaw, onOpenConversation, onSelect, now } = props
  const status = statusWords(checkpoint.status)
  const findings = checkpoint.probe_findings ?? []
  const runs = checkpoint.covered_runs ?? []
  const hubWords = madeByHubWords(checkpoint)
  const reason = checkpoint.title_reason?.trim() || null
  const generationError = checkpoint.generation_error?.trim() || null
  const carriedFrom = checkpoint.carried_from
  const started = checkpoint.started_conversations ?? []
  const carriedInto = checkpoint.carried_into ?? (
    checkpoint.cut_over_to_conversation_id ? { conversation_id: checkpoint.cut_over_to_conversation_id } : null
  )
  return (
    <article className="aw-ckpts-detail" data-testid="checkpoint-detail" aria-label={checkpointTitle(checkpoint)}>
      <header className="aw-ckpts-detail-head">
        <h3 data-testid="checkpoint-detail-title">{checkpointTitle(checkpoint)}</h3>
        {madeByHub(checkpoint) ? (
          <StatePill tone="amber">
            <span data-testid="checkpoint-made-by-hub">Made by the Hub</span>
          </StatePill>
        ) : null}
        <StatePill tone={status.tone}>{status.label}</StatePill>
        <button
          type="button"
          data-slot="checkpoint-close"
          className="aw-link aw-ckpts-close"
          aria-label="Close this checkpoint"
          onClick={() => onSelect(null)}
        >
          <Icon name="close" size={14} />
        </button>
      </header>
      {checkpoint.summary ? <p className="aw-ckpts-detail-summary">{checkpoint.summary}</p> : null}
      <p className="aw-ckpts-meta" data-testid="checkpoint-detail-meta">
        <span>{checkpoint.agent}</span>
        <span>{triggerWords(checkpoint.trigger)}</span>
        <span>{when(checkpoint.created_at, now)}</span>
        <span>{conversationLabel(checkpoint.conversation_id)}</span>
      </p>

      {props.onStart && checkpoint.status === 'ready' ? (
        <StartPanel key={checkpoint.id} checkpoint={checkpoint} agents={props.startAgents ?? props.agents} onStart={props.onStart} />
      ) : null}

      {carriedFrom || carriedInto || started.length ? (
        <div className="aw-ckpts-lineage" data-testid="checkpoint-detail-lineage">
          {carriedFrom ? (
            <p>
              This conversation started from{' '}
              <button
                type="button"
                data-slot="checkpoint-link"
                className="aw-link aw-link-inline"
                onClick={() => onSelect(carriedFrom.checkpoint_id)}
              >
                {carriedFrom.title?.trim() || 'an earlier checkpoint'}
              </button>
              .
            </p>
          ) : null}
          {carriedInto ? (
            <p>
              Carried over into{' '}
              <button
                type="button"
                data-slot="conversation-link"
                className="aw-link aw-link-inline"
                onClick={() => onOpenConversation?.(null, carriedInto.conversation_id)}
              >
                {conversationLabel(carriedInto.conversation_id)}
              </button>
              .
            </p>
          ) : null}
          {started.length ? (
            <div data-testid="checkpoint-detail-started">
              <p>Conversations started from this checkpoint:</p>
              <ul className="aw-ckpts-list">
                {started.map((item) => (
                  <li key={item.conversation_id} data-testid={`checkpoint-started-${item.conversation_id}`}>
                    <button
                      type="button"
                      data-slot="conversation-link"
                      className="aw-link aw-link-inline"
                      onClick={() => onOpenConversation?.(item.agent, item.conversation_id)}
                    >
                      {item.title?.trim() || 'New conversation'}
                    </button>{' '}
                    · {item.agent} · {when(item.created_at, now)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {hubWords || reason || generationError ? (
        <div className="aw-callout tone-amber aw-ckpts-why" data-testid="checkpoint-why">
          {hubWords ? <p>{hubWords}</p> : null}
          {reason ? <p>{reason}</p> : null}
          {generationError ? <p>{generationError}</p> : null}
        </div>
      ) : null}
      {checkpoint.has_unreadable_answer ? (
        <div className="aw-ckpts-raw">
          {rawAnswer ? (
            <pre className="aw-ckpts-raw-text" data-testid="checkpoint-raw-answer">
              {rawAnswer}
            </pre>
          ) : (
            <button
              type="button"
              data-slot="checkpoint-show-raw"
              className="aw-link aw-link-inline"
              onClick={() => onShowRaw?.(checkpoint.id)}
            >
              Show what the model returned
            </button>
          )}
        </div>
      ) : null}

      {findings.length ? (
        <Section title="What the checks found" testId="checkpoint-findings">
          <ul className="aw-ckpts-list">
            {findings.map((finding, index) => (
              <li key={index}>{findingWords(finding)}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      {checkpoint.body ? (
        <div className="aw-ckpts-body" data-testid="checkpoint-body">
          <MarkdownMessage content={checkpoint.body} />
        </div>
      ) : (
        <p className="aw-ckpts-none">This checkpoint has no written text.</p>
      )}

      <Section title="Runs it covers" testId="checkpoint-runs">
        {runs.length === 0 ? (
          <p className="aw-ckpts-none" data-testid="checkpoint-no-runs">
            This checkpoint covers no recorded run.
          </p>
        ) : (
          <ol className="aw-ckpts-runs">
            {runs.map((run, index) => (
              <li key={run.run_id} data-testid={`checkpoint-run-${run.run_id}`}>
                <span>
                  Run {index + 1} · {run.agent} · {when(run.started_at, now)}
                </span>
                <TraceButton runId={run.run_id} label="Open trace" testId={`checkpoint-run-trace-${run.run_id}`} />
              </li>
            ))}
          </ol>
        )}
      </Section>

      {checkpoint.files_changed?.length ? (
        <Section title="Files changed" testId="checkpoint-files">
          <ul className="aw-ckpts-list">
            {checkpoint.files_changed.map((file) => (
              <li key={file}>
                <code>{file}</code>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {checkpoint.open_questions?.length ? (
        <Section title="Open questions" testId="checkpoint-questions">
          <ul className="aw-ckpts-list">
            {checkpoint.open_questions.map((question) => (
              <li key={question.id}>{question.question}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {checkpoint.citations?.length ? (
        <Section title="Cited" testId="checkpoint-citations">
          <ul className="aw-ckpts-list">
            {checkpoint.citations.map((citation) => (
              <li key={citation.id}>{citation.preview}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {notes.length ? (
        <Section title="Notes the agent left" testId="checkpoint-notes">
          <ul className="aw-ckpts-list">
            {notes.map((note) => (
              <li key={note.id} data-testid={`checkpoint-note-${note.id}`}>
                <strong>{note.agent}</strong> · {note.intent}
                {note.suspicions.length ? <div className="aw-ckpts-none">Suspects: {note.suspicions.join(' · ')}</div> : null}
                {note.warnings.length ? <div className="aw-ckpts-none">Warns: {note.warnings.join(' · ')}</div> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </article>
  )
}

export function CheckpointsPage(props: CheckpointsPageProps) {
  const {
    checkpoints,
    lineage,
    filters,
    onFilters,
    agents,
    conversations,
    conversationLabel,
    selectedId,
    onSelect,
    onOpenConversation,
    loading,
    error,
    now,
  } = props
  const selected = checkpoints.find((checkpoint) => checkpoint.id === selectedId) ?? props.opened ?? null
  const narrowed = Boolean(filters.agent || filters.trigger || filters.conversationId)
  return (
    <div className="aw-ckpts" data-testid="checkpoints-page">
      <div className="aw-ckpts-filters" role="group" aria-label="Narrow the checkpoints">
        <MenuSelect
          label="Agent"
          testId="checkpoints-filter-agent"
          value={filters.agent || ALL}
          onChange={(value) => onFilters({ ...filters, agent: value === ALL ? '' : value })}
          options={[{ value: ALL, label: 'All agents' }, ...agents.map((agent) => ({ value: agent, label: agent }))]}
        />
        <MenuSelect
          label="What triggered it"
          testId="checkpoints-filter-trigger"
          value={filters.trigger || ALL}
          onChange={(value) => onFilters({ ...filters, trigger: value === ALL ? '' : value })}
          options={[{ value: ALL, label: 'Any reason' }, ...TRIGGER_FILTER_OPTIONS]}
        />
        <MenuSelect
          label="Conversation"
          testId="checkpoints-filter-conversation"
          value={filters.conversationId || ALL}
          onChange={(value) => onFilters({ ...filters, conversationId: value === ALL ? '' : value })}
          options={[
            { value: ALL, label: 'All conversations' },
            ...(filters.conversationId && !conversations.some((c) => c.id === filters.conversationId)
              ? [{ value: filters.conversationId, label: conversationLabel(filters.conversationId) }]
              : []),
            ...conversations.map((conversation) => ({ value: conversation.id, label: conversation.label })),
          ]}
          maxWidth={320}
        />
        {narrowed ? (
          <button
            type="button"
            data-slot="checkpoints-clear"
            className="aw-link"
            data-testid="checkpoints-clear-filters"
            onClick={() => onFilters({ agent: '', trigger: '', conversationId: '' })}
          >
            Show all
          </button>
        ) : null}
      </div>

      {lineage && (lineage.started_from || lineage.carried_into) ? (
        <div className="aw-ckpts-lineage" data-testid="checkpoints-lineage">
          {lineage.started_from ? (
            <p data-testid="checkpoints-started-from">
              This conversation started from{' '}
              <button
                type="button"
                data-slot="checkpoint-link"
                className="aw-link aw-link-inline"
                onClick={() => onSelect(lineage.started_from!.checkpoint_id)}
              >
                {lineage.started_from.title?.trim() || 'an earlier checkpoint'}
              </button>
              .
            </p>
          ) : null}
          {lineage.carried_into ? (
            <p data-testid="checkpoints-carried-into">
              This conversation was carried over into{' '}
              <button
                type="button"
                data-slot="conversation-link"
                className="aw-link aw-link-inline"
                onClick={() => onOpenConversation?.(null, lineage.carried_into!.conversation_id)}
              >
                {conversationLabel(lineage.carried_into.conversation_id)}
              </button>
              .
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="aw-ckpts-split" data-open={selected ? 'true' : 'false'}>
        <div className="aw-ckpts-listcol">
          {error ? (
            <p className="aw-callout tone-red">The checkpoints could not be read.</p>
          ) : loading && checkpoints.length === 0 ? (
            <p className="aw-ckpts-none aw-delayed">Reading the checkpoints…</p>
          ) : checkpoints.length === 0 ? (
            <p className="aw-ckpts-none" data-testid="checkpoints-empty">
              {narrowed
                ? 'No checkpoint matches. Show all to see every checkpoint.'
                : 'No checkpoint has been taken in this project yet.'}
            </p>
          ) : (
            <>
              <p className="aw-ckpts-count" data-testid="checkpoints-count">
                {checkpoints.length === 1 ? '1 checkpoint' : `${checkpoints.length} checkpoints`}
              </p>
              <ol className="aw-ckpts-rows" data-testid="checkpoints-list">
                {checkpoints.map((checkpoint) => (
                  <CheckpointRow
                    key={checkpoint.id}
                    checkpoint={checkpoint}
                    conversationLabel={conversationLabel(checkpoint.conversation_id)}
                    selected={checkpoint.id === selectedId}
                    onSelect={() => onSelect(checkpoint.id)}
                    now={now}
                  />
                ))}
              </ol>
            </>
          )}
        </div>
        {selected ? (
          <CheckpointDetail checkpoint={selected} props={props} />
        ) : selectedId && !loading ? (
          <p className="aw-ckpts-none" data-testid="checkpoint-not-found">
            That checkpoint could not be found.
          </p>
        ) : null}
      </div>
    </div>
  )
}
