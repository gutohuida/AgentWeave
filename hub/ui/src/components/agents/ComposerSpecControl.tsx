import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { composerControlClassName } from './ComposerModelControls'

interface ComposerSpecControlProps {
  /** The document open beside this conversation, as a display name. `null` when none is open. */
  documentLabel: string | null
  /** Opens the document picker. The conversation view owns it, because it has to be reachable
   *  whether or not a document is already open. */
  onOpenPicker: () => void
  /** Start an exploration for this conversation — one press, no naming step. */
  onStartExploration: () => void
  /** Detach the open document from this conversation. Never deletes it. */
  onStopExploring: () => void
  /**
   * Declared, but the document does not exist yet — the new-conversation surface, where there is
   * no conversation to attach one to and no title to name it from until the first message. The
   * document is created on send, so this state lasts exactly as long as it takes to write one
   * message. §2.7's objection to a mode pill was that "propose what?" has no answer; that applies
   * to a conversation that *stays* in a mode, not to an intent declared seconds before the
   * document appears.
   */
  armed?: boolean
  busy?: boolean
}

/**
 * The specification, reached from where the operator already is.
 *
 * It replaces the `spec` project tab. Reaching a specification used to mean leaving the
 * conversation, going to the project, and choosing a tab — for the surface the product is most
 * about (operator, 2026-08-10: *"since the spec is something that is going to be one of the main
 * things in agentweave… we could open the spec screen from the composer with a button or a pill
 * somewhere"*).
 *
 * **With no document open it is a toggle**, the way plan mode is: press it and you are exploring.
 * The operator asked for exactly this after watching an agent with no document reach for a
 * workflow of its own — *"Maybe we indeed need a exploration pill. Like you just enable and
 * disable like plan mode"*. It is compatible with the design rather than a departure from it:
 * §2.7 resolved that explore begins by *creating a document*, and said the entry point "can look
 * like a pill and behave like a button". What it ruled out was a pill holding a mode with no
 * document behind it, because then "propose" and "approve" have no subject. Pressing this creates
 * the document, so they do.
 *
 * **It is not symmetrical with plan mode, and must not pretend to be.** Plan mode is ephemeral and
 * per-run; an exploration leaves an artifact. Turning it off therefore detaches the document from
 * this conversation and never deletes it — a toggle that discarded work on the way back would be a
 * trap dressed as a switch.
 *
 * With a document open it states which one this turn is written against, the way the Permissions
 * pill states the posture the run will use, and pressing the label changes that value.
 */
export function ComposerSpecControl({
  documentLabel,
  onOpenPicker,
  onStartExploration,
  onStopExploring,
  armed = false,
  busy = false,
}: ComposerSpecControlProps) {
  if (!documentLabel) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="pill"
        data-testid="composer-start-exploration"
        onClick={armed ? onStopExploring : onStartExploration}
        disabled={busy}
        data-active={armed ? 'true' : 'false'}
        className={`${composerControlClassName} min-w-0 max-w-full`}
        title={
          armed
            ? 'Exploring — the document is created with your first message'
            : 'Start an exploration — creates a specification document for this conversation'
        }
        aria-label={armed ? 'Stop exploring' : 'Start an exploration'}
        aria-pressed={armed}
      >
        <Icon name="article" size={13} />
        <span className="min-w-0 truncate">
          {busy ? 'Starting…' : armed ? 'Exploring' : 'Explore'}
        </span>
      </Button>
    )
  }

  return (
    <span className="flex min-w-0 items-center">
      <Button
        type="button"
        variant="ghost"
        size="pill"
        data-testid="composer-spec-control"
        onClick={onOpenPicker}
        className={`${composerControlClassName} min-w-0 max-w-full`}
        title={`Spec: ${documentLabel}`}
        aria-label={`Spec: ${documentLabel}`}
        aria-pressed
      >
        <span className="shrink-0" style={{ color: 'var(--text-3)' }}>Spec: </span>
        <Icon name="article" size={13} />
        <span className="min-w-0 truncate">{documentLabel}</span>
      </Button>
      {/* Its own control, not a second meaning on the one above: a pill whose press means "open"
          sometimes and "close" other times is two controls wearing one hat. */}
      <Button
        type="button"
        variant="ghost"
        size="pill"
        data-testid="composer-stop-exploring"
        onClick={onStopExploring}
        className="shrink-0 px-1"
        title="Close the document — it is kept, not deleted"
        aria-label="Close the document"
      >
        <Icon name="close" size={12} />
      </Button>
    </span>
  )
}
