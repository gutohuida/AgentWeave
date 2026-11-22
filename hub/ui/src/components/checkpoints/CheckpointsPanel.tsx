import { Icon } from '@/components/common/Icon'
import type { CheckpointNote, ProjectCheckpoint } from '@/api/checkpoints'
import { CheckpointDetail, CheckpointRow } from './CheckpointsPage'
import '@/styles/checkpoints.css'

/**
 * A narrow list of checkpoints with one openable in place: the Checkpoints tab of a thread's side
 * panel and the Checkpoints section of a profile's page (leaner-navigation). Index, then the one
 * checkpoint read in full, never both columns at once: it reuses the page's own row and detail, so
 * the wording, the sections (what the checks found, runs covered, files changed, open questions,
 * what it cites, notes) and their order are the Checkpoints tab's. Presentational.
 */
export function CheckpointsPanel({
  checkpoints,
  openedId,
  onOpen,
  conversationLabel,
  notes = [],
  rawAnswer,
  onShowRaw,
  onOpenConversation,
  emptyText = 'No checkpoint has been taken here yet.',
  now,
}: {
  /** In the order the route returns them (newest first). */
  checkpoints: ProjectCheckpoint[]
  openedId: string | null
  onOpen: (checkpointId: string | null) => void
  conversationLabel: (conversationId: string) => string
  /** The notes the opened checkpoint carries. */
  notes?: CheckpointNote[]
  rawAnswer?: string | null
  onShowRaw?: (checkpointId: string) => void
  onOpenConversation?: (agent: string | null, conversationId: string) => void
  emptyText?: string
  now?: Date
}) {
  const opened = openedId ? (checkpoints.find((c) => c.id === openedId) ?? null) : null
  if (opened) {
    return (
      <div className="aw-ckpts-panel" data-testid="checkpoints-panel" data-view="detail">
        <button type="button" data-slot="checkpoints-back" className="aw-link aw-ckpts-panel-back" onClick={() => onOpen(null)}>
          <Icon name="arrow_left" size={13} />
          All checkpoints
        </button>
        <CheckpointDetail
          checkpoint={opened}
          props={{ conversationLabel, onSelect: onOpen, agents: [], notes, rawAnswer, onShowRaw, onOpenConversation, now }}
        />
      </div>
    )
  }
  return (
    <div className="aw-ckpts-panel" data-testid="checkpoints-panel" data-view="list">
      {checkpoints.length === 0 ? (
        <p className="aw-ckpts-none" data-testid="checkpoints-empty">{emptyText}</p>
      ) : (
        <>
          <p className="aw-ckpts-count" data-testid="checkpoints-count">
            {checkpoints.length === 1 ? '1 checkpoint' : `${checkpoints.length} checkpoints`}
          </p>
          <ol className="aw-ckpts-rows" data-testid="checkpoints-list" aria-label="Checkpoints">
            {checkpoints.map((checkpoint) => (
              <CheckpointRow
                key={checkpoint.id}
                checkpoint={checkpoint}
                conversationLabel={conversationLabel(checkpoint.conversation_id)}
                selected={false}
                onSelect={() => onOpen(checkpoint.id)}
                now={now}
              />
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
