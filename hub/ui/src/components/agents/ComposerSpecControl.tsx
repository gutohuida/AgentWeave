import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { composerControlClassName } from './ComposerModelControls'

interface ComposerSpecControlProps {
  /** The document open beside this conversation, as a display name. `null` when none is open. */
  documentLabel: string | null
  /** Opens the document picker. The conversation view owns it, because it has to be reachable
   *  whether or not a document is already open. */
  onOpenPicker: () => void
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
 * It renders as a control pill rather than an action button because that is what it is: it states
 * which document this turn is being written against, the way the Permissions pill states which
 * posture the run will use. Pressing it changes that value.
 *
 * Closing the document is the panel's own control, not a second state on this one — a pill whose
 * press means "open" sometimes and "close" other times is two controls wearing one hat.
 */
export function ComposerSpecControl({ documentLabel, onOpenPicker }: ComposerSpecControlProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="pill"
      data-testid="composer-spec-control"
      onClick={onOpenPicker}
      className={`${composerControlClassName} min-w-0 max-w-full`}
      title={documentLabel ? `Spec: ${documentLabel}` : 'Spec: open a document'}
      aria-label={documentLabel ? `Spec: ${documentLabel}` : 'Open a specification document'}
    >
      <span className="shrink-0" style={{ color: 'var(--text-3)' }}>Spec: </span>
      <Icon name="article" size={13} />
      <span className="min-w-0 truncate">{documentLabel ?? 'None'}</span>
    </Button>
  )
}
