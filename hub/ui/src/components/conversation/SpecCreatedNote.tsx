import { Icon } from '@/components/common/Icon'
import '@/styles/conversation.css'

/** A quiet line in the transcript, under the message in which an agent created a specification
 *  document in a thread that has none open: "Architect created <title> · Open here". It is run
 *  metadata, not a question, so it scrolls away with the transcript and asks nothing. The wording
 *  stays true at any later step (it says what happened, never what the document is doing now).
 *  Presentational: the offer's facts in, callbacks out. */
export function SpecCreatedNote({
  title,
  createdBy,
  onOpen,
  onDismiss,
  busy = false,
}: {
  title: string
  /** The agent that created it; left out when the Hub did not record who. */
  createdBy?: string | null
  onOpen: () => void
  onDismiss: () => void
  busy?: boolean
}) {
  return (
    <div className="aw-spec-created-note" data-testid="spec-created-note">
      <Icon name="article" size={13} className="shrink-0" />
      <span className="aw-spec-created-note-text" title={title}>
        {createdBy ? `${createdBy} created ` : 'Created '}
        <span className="aw-spec-created-note-title">{title}</span>
      </span>
      <button
        type="button"
        data-slot="spec-created-open"
        className="aw-spec-created-note-link"
        disabled={busy}
        aria-label={`Open ${title} in this thread`}
        onClick={onOpen}
      >
        Open here
      </button>
      <button
        type="button"
        data-slot="spec-created-dismiss"
        className="aw-spec-created-note-dismiss"
        disabled={busy}
        aria-label={`Do not open ${title} here`}
        title="Not here"
        onClick={onDismiss}
      >
        <Icon name="close" size={12} />
      </button>
    </div>
  )
}
