import { useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { StatePill, type Tone } from '@/components/common/StatePill'
import { Expander } from '@/components/common/Expander'
import { useCheckpointNotes, useCheckpoints, type Checkpoint } from '@/api/checkpoints'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { hubDate } from '@/lib/hubTime'
import { ApiError } from '@/api/client'

/**
 * A conversation's checkpoints and checkpoint notes (slice remaining-hidden-data). Only a
 * checkpoint's status ever reached the screen, as a banner; its body, the files it says changed,
 * its open questions and citations, and what the probe found missing or invented were recorded and
 * unread, and the notes agents left for it had no read route at all.
 */

const STATUS_TONE: Record<Checkpoint['status'], Tone> = { ready: 'green', unwritten: 'amber', failed: 'red' }

function when(value: string | null | undefined): string {
  return value ? hubDate(value).toLocaleString() : ''
}

function CheckpointItem({ checkpoint, index }: { checkpoint: Checkpoint; index: number }) {
  const [open, setOpen] = useState(index === 0)
  const findings = checkpoint.probe_findings ?? []
  return (
    <li className="aw-ckpt" data-testid={`checkpoint-${checkpoint.id}`}>
      <button
        type="button"
        className="aw-ckpt-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="chevron_right" size={12} aria-hidden="true" />
        <StatePill tone={STATUS_TONE[checkpoint.status] ?? 'neutral'}>{checkpoint.status}</StatePill>
        <span className="aw-ckpt-title">{checkpoint.trigger.replace(/_/g, ' ')}</span>
        <span className="aw-tl-meta">{when(checkpoint.created_at)}</span>
      </button>
      <Expander open={open}>
        <div className="aw-ckpt-body">
          {checkpoint.generation_error ? (
            <p className="aw-callout tone-red">{checkpoint.generation_error}</p>
          ) : null}
          {checkpoint.probe_status ? (
            <p className="aw-tl-meta">
              Probe: {checkpoint.probe_status.replace(/_/g, ' ')}
              {checkpoint.cut_over_to_conversation_id ? ' · carried into a new conversation' : ''}
            </p>
          ) : null}
          {findings.length ? (
            <ul className="aw-ckpt-findings" data-testid={`checkpoint-findings-${checkpoint.id}`}>
              {findings.map((finding, i) => (
                <li key={i}>
                  <strong>{finding.dimension}</strong>
                  {finding.missing?.length ? <> · missing: {finding.missing.join(', ')}</> : null}
                  {finding.invented?.length ? <> · invented: {finding.invented.join(', ')}</> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {checkpoint.body ? <pre className="aw-ckpt-text">{checkpoint.body}</pre> : null}
          {checkpoint.files_changed?.length ? (
            <section>
              <h4 className="aw-ckpt-label">Files changed</h4>
              <ul className="aw-ckpt-files">
                {checkpoint.files_changed.map((file) => (
                  <li key={file}>
                    <code>{file}</code>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {checkpoint.open_questions?.length ? (
            <section>
              <h4 className="aw-ckpt-label">Open questions</h4>
              <ul className="aw-ckpt-list">
                {checkpoint.open_questions.map((question) => (
                  <li key={question.id}>{question.question}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {checkpoint.citations?.length ? (
            <section>
              <h4 className="aw-ckpt-label">Cited</h4>
              <ul className="aw-ckpt-list">
                {checkpoint.citations.map((citation) => (
                  <li key={citation.id} className="aw-tl-meta">
                    {citation.preview}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </Expander>
    </li>
  )
}

export function CheckpointsPanel({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onClose)
  const checkpoints = useCheckpoints(conversationId)
  const notes = useCheckpointNotes(conversationId)
  const rows = checkpoints.data ?? []
  const noteRows = notes.data?.notes ?? []
  return (
    <div className="aw-sheet-backdrop" onClick={onClose}>
      <aside
        ref={panelRef}
        className="aw-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="Checkpoints"
        data-testid="checkpoints-panel"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="aw-sheet-head">
          <h2>Checkpoints</h2>
          <button type="button" className="aw-link" onClick={onClose} aria-label="Close checkpoints">
            <Icon name="close" size={14} />
          </button>
        </header>
        <div className="aw-sheet-scroll">
          <section className="aw-req-section">
            <h3 className="aw-req-heading">Checkpoints · {rows.length}</h3>
            {checkpoints.isError ? (
              <p className="aw-callout tone-red">This conversation’s checkpoints could not be read.</p>
            ) : rows.length === 0 ? (
              <p className="aw-tl-meta">No checkpoint has been taken in this conversation.</p>
            ) : (
              <ol className="aw-ckpt-list-outer">
                {rows.map((checkpoint, index) => (
                  <CheckpointItem key={checkpoint.id} checkpoint={checkpoint} index={index} />
                ))}
              </ol>
            )}
          </section>
          <section className="aw-req-section">
            <h3 className="aw-req-heading">Notes for the next checkpoint · {noteRows.length}</h3>
            {notes.error instanceof ApiError && notes.error.status === 404 ? (
              <p className="aw-tl-meta">This Hub predates reading checkpoint notes; they appear once it restarts.</p>
            ) : notes.isError ? (
              <p className="aw-callout tone-red">This conversation’s checkpoint notes could not be read.</p>
            ) : noteRows.length === 0 ? (
              <p className="aw-tl-meta">No agent has left a note for a checkpoint here.</p>
            ) : (
              <ol className="aw-ckpt-list-outer">
                {noteRows.map((note) => (
                  <li key={note.id} className="aw-ckpt aw-ckpt-note" data-testid={`checkpoint-note-${note.id}`}>
                    <div className="aw-ckpt-note-head">
                      <strong>{note.agent}</strong>
                      <span className="aw-tl-meta">{when(note.created_at)}</span>
                      <StatePill tone={note.consumed_by_checkpoint_id ? 'green' : 'amber'}>
                        {note.consumed_by_checkpoint_id ? 'carried' : 'waiting'}
                      </StatePill>
                    </div>
                    <p>{note.intent}</p>
                    {note.suspicions.length ? (
                      <p className="aw-tl-meta">Suspects: {note.suspicions.join(' · ')}</p>
                    ) : null}
                    {note.warnings.length ? (
                      <p className="aw-tl-meta">Warns: {note.warnings.join(' · ')}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </aside>
    </div>
  )
}
