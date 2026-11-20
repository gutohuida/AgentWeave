import { Button } from '@/components/ui/button'
import { stepKeyLabel } from '@/components/settings/stepLabels'
import type { SpecDocumentOffer } from '@/api/conversationSpec'

/** The notice for a change document an agent created in this conversation
 *  (`every-spec-entry-point-leads-into-the-journey`, FR-7): it names the document and offers
 *  Open and Not now. Presentational: offers in, `onAnswer` out. A failed read and a refused answer
 *  are said, never shown as "no offers". */
export function ConversationSpecOffers({
  offers,
  onAnswer,
  busy = false,
  readError,
  answerError,
}: {
  offers: SpecDocumentOffer[]
  onAnswer: (path: string, answer: 'open' | 'not_now') => void
  busy?: boolean
  readError?: string | null
  answerError?: string | null
}) {
  if (readError) {
    return (
      <p className="aw-spec-message" data-tone="warn" data-testid="conversation-spec-offer-error">
        <span className="aw-spec-message-text">Could not read the documents offered here: {readError}</span>
      </p>
    )
  }
  if (offers.length === 0) return null
  return (
    <div className="flex flex-col gap-1" data-testid="conversation-spec-offers">
      {offers.map((offer) => (
        <div key={offer.path} className="aw-spec-message" data-testid="conversation-spec-offer" data-path={offer.path}>
          <span className="aw-spec-message-text">
            {offer.created_by ? `${offer.created_by} started` : 'Started'} <strong>{offer.title}</strong>
            {offer.step ? ` (${stepKeyLabel(offer.step)})` : ''}. Work on it in this thread?
          </span>
          <Button
            variant="primary"
            size="xs"
            disabled={busy}
            aria-label={`Open ${offer.title}`}
            data-testid="conversation-spec-offer-open"
            onClick={() => onAnswer(offer.path, 'open')}
          >
            Open
          </Button>
          <Button
            variant="ghost"
            size="xs"
            disabled={busy}
            aria-label={`Not now: ${offer.title}`}
            data-testid="conversation-spec-offer-dismiss"
            onClick={() => onAnswer(offer.path, 'not_now')}
          >
            Not now
          </Button>
        </div>
      ))}
      {answerError && (
        <span role="alert" className="aw-spec-message-text" style={{ color: 'var(--red)' }} data-testid="conversation-spec-offer-error">
          {answerError}
        </span>
      )}
    </div>
  )
}
